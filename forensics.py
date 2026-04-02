
import logging
import asyncio
from typing import Dict, Any, Optional, List
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey

from config import (
    TARGET_TREASURY_LIST, 
    CEX_HOT_WALLET_ADDRESSES, 
    MAX_TEST_TX_AMOUNT, 
    get_logger
)
from db_manager import DatabaseManager

from graph_manager import GraphManager

logger = get_logger("forensics")

class ForensicsEngine:
    def __init__(self, db_manager: DatabaseManager, rpc_client: AsyncClient):
        self.db = db_manager
        self.rpc = rpc_client
        self.graph = GraphManager()

    async def check_is_fresh_wallet(self, address: str) -> bool:
        """
        Check if a wallet is 'fresh' (has fewer than 5 transactions).
        """
        try:
            # We request signatures for the address with a limit of 5.
            # If we get fewer than 5, it's considered fresh for this heuristic.
            pubkey = Pubkey.from_string(address)
            response = await self.rpc.get_signatures_for_address(
                pubkey, limit=10, commitment="confirmed"
            )
            # Check the number of signatures found
            if response.value:
                return len(response.value) < 5
            return True # No signatures means fresh
        except Exception as e:
            logger.error(f"Error checking history for {address}: {e}")
            return False # Fail safe: assume not fresh to avoid noise, or handling differently

    async def analyze_transaction(self, tx_data: Dict[str, Any]):
        """
        Analyze a parsed transaction for suspicious patterns (Multi-Hop Capable).
        """
        signature = tx_data.get('signature')
        sender = tx_data.get('sender')
        receiver = tx_data.get('receiver')
        amount = tx_data.get('amount', 0.0)
        timestamp = tx_data.get('timestamp', 0)

        if not (sender and receiver):
            return
            
        # Ignore 0.0 amount transfers (e.g., smart contract pings, mint setups, or non-SPL interactions)
        # Wash-trading tracking inherently requires supply volume to move.
        if amount <= 0.0:
            return

        logger.debug(f"Analyzing {signature}: {sender} -> {receiver} ({amount})")

        # --- Context Gathering ---
        db_targets = await self.db.get_targets()
        is_sender_treasury = (sender in TARGET_TREASURY_LIST) or (sender in db_targets)
        sender_watchlist_entry = await self.db.get_watchlist_entry(sender)
        
        # --- NEO4J GRAPH INGESTION ---
        # 1. Log the transfer
        self.graph.add_transfer(sender, receiver, amount, signature, timestamp)
        
        # 2. Label known nodes
        if is_sender_treasury:
            self.graph.mark_as_treasury(sender)
        
        if receiver in CEX_HOT_WALLET_ADDRESSES:
            self.graph.mark_as_cex(receiver)
            
            # --- GRAPH DETECTION (THE TRAP) ---
            # Check if this CEX deposit is linked to ANY treasury via the graph
            path = self.graph.find_treasury_origin(receiver)
            if path:
                # CRITICAL ALERT FROM GRAPH
                # path is a Neo4j Path object, printing it directly might be messy but informative
                alert_msg = (
                    f"🚨 CRITICAL ALERT: GRAPH DISCOVERED WASH TRADING CHAIN 🚨\n"
                    f"Destination CEX: {receiver}\n"
                    f"Graph Path Found: {path}\n" # Neo4j path string representation
                    f"Signature: {signature}"
                )
                logger.critical(alert_msg)
                print(alert_msg)

        # --- SQL HEURISTICS (Legacy/Fast Path) ---
        
        # --- PATH A: Treasury -> Wallet (Depth 1) ---
        if is_sender_treasury:
            if amount < MAX_TEST_TX_AMOUNT:
                # Bypassing 'is_fresh' for robust historical backtesting (ignores modern spam pollution)
                logger.info(f"🔍 SUSPICIOUS (Depth 1): Treasury {sender} -> Wallet {receiver}")
                # Start the chain
                await self.db.add_to_watchlist(
                    receiver, 
                    origin_treasury=sender, 
                    parent_wallet=sender, 
                    depth=1
                )
            else:
                logger.debug(f"Ignored high value transfer from treasury: {amount}")

        # --- PATH B: Watched Wallet -> ... ---
        elif sender_watchlist_entry:
            current_depth = sender_watchlist_entry['depth']
            origin = sender_watchlist_entry['origin_treasury']
            
            # Case B1: To CEX (THE SMOKING GUN) - Handled by Graph above, but keeping log
            if receiver in CEX_HOT_WALLET_ADDRESSES:
                logger.info(f"Watchlist hit CEX: {sender} -> {receiver}")
                
            # Case B2: To Next Wallet (Extend Chain)
            # Limit genealogy depth to avoid infinite expansion (e.g. max 3 hops)
            elif current_depth < 3:
                if amount < MAX_TEST_TX_AMOUNT:
                    new_depth = current_depth + 1
                    logger.info(f"🔗 EXTENDING CHAIN (Depth {new_depth}): {sender} -> {receiver}")
                    await self.db.add_to_watchlist(
                        receiver,
                        origin_treasury=origin,
                        parent_wallet=sender,
                        depth=new_depth
                    )
