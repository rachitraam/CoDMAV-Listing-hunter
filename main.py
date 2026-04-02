
import asyncio
import logging
import signal
from typing import Set

from solana.rpc.async_api import AsyncClient
# from solders.pubkey import Pubkey # Unused
from solders.signature import Signature

from config import (
    SOLANA_RPC_HTTP_URL, 
    TARGET_TREASURY_LIST, 
    get_logger
)
from db_manager import DatabaseManager
from solana_listener import SolanaWebSocketListener
from forensics import ForensicsEngine

logger = get_logger("main")

class ListingHunter:
    def __init__(self):
        self.db = DatabaseManager()
        self.rpc_client = AsyncClient(SOLANA_RPC_HTTP_URL)
        self.forensics = ForensicsEngine(self.db, self.rpc_client)
        self.listener = None # type: ignore
        self.running = True

    async def fetch_and_parse_transaction(self, signature_str: str):
        """
        Fetches full transaction details and parses them.
        """
        try:
            signature = Signature.from_string(signature_str)
            # Fetch transaction with max supported version to handle Versioned Transactions
            tx_response = await self.rpc_client.get_transaction(
                signature, 
                max_supported_transaction_version=0,
                commitment="confirmed"
            )

            if not tx_response.value:
                logger.warning(f"Transaction not found or null: {signature_str}")
                return

            # Parsing Logic using 'solders' objects
            # This is complex in Solana; for Phase 1 we simplify:
            # We look at pre/post token balances or native SOL transfers.
            # For this MVP, let's assume SOL transfers or simplified SPL parsing.
            
            transaction = tx_response.value.transaction.transaction
            # meta = tx_response.value.meta # Unused currently
            
            # Extract simple details (This needs to be expanded for SPL Token Transfers)
            # For now, we'll try to identify the sender (signer) and simplified receiver
            
            msg = transaction.message
            accounts = msg.account_keys
            
            # The first account is usually the fee payer/signer
            sender = str(accounts[0]) 
            
            # Naive receiver finding (simplified)
            # In real implementations, we parse 'preTokenBalances' and 'postTokenBalances'
            # to see who received tokens.
            
            # --- Improved Parsing Logic ---
            meta = tx_response.value.transaction.meta
            if not meta:
                return

            # Method 1: Check SPL Token Balance Changes
            pre_balances = {str(b.account_index): float(b.ui_token_amount.ui_amount or 0) for b in meta.pre_token_balances}
            post_balances = {str(b.account_index): b for b in meta.post_token_balances}

            timestamp = tx_response.value.block_time or 0
            transfers_detected = False

            # Step A: Mathematically derive the TRUE sender by finding whose balance decreased
            derived_sender = None
            for idx, post_b in post_balances.items():
                post_amt = float(post_b.ui_token_amount.ui_amount or 0)
                pre_amt = float(pre_balances.get(idx, 0.0))
                if pre_amt > post_amt:
                    if hasattr(post_b, 'owner') and post_b.owner:
                        derived_sender = str(post_b.owner)
                        break 
                        
            # Fallback to Fee Payer if the token was literally minted out of thin air
            actual_sender = derived_sender if derived_sender else sender

            # Step B: Log every single destination wallet that increased
            for idx, post_b in post_balances.items():
                post_amt = float(post_b.ui_token_amount.ui_amount or 0)
                pre_amt = float(pre_balances.get(idx, 0.0))
                
                if post_amt > pre_amt:
                    diff = post_amt - pre_amt
                    receiver = None
                    
                    if hasattr(post_b, 'owner') and post_b.owner:
                        receiver = str(post_b.owner)
                    else:
                        try:
                            acc_idx = int(idx)
                            if acc_idx < len(accounts):
                                receiver = str(accounts[acc_idx])
                        except:
                            pass
                            
                    # CRITICAL: Do not log self-loops! 
                    # Initializing a Token Mint creates 1 Billion tokens out of thin air into the Treasury.
                    # This balance 'increase' would map Treasury -> Treasury indefinitely.
                    if receiver and receiver != actual_sender:
                        parsed_data = {
                            'signature': signature_str,
                            'sender': actual_sender,
                            'receiver': receiver,
                            'amount': diff,
                            'timestamp': timestamp
                        }
                        await self.forensics.analyze_transaction(parsed_data)
                        transfers_detected = True
            
            # Method 2: Fallback to System Transfer (SOL)
            # If no token balance change, trigger fallback
            if not transfers_detected:
                 receiver = None
                 amount = 0.0
                 # Fallback: Just use the second account as a dummy receiver for testing if parsing failed
                 if len(accounts) > 1:
                     receiver = str(accounts[1])
                     
                 if receiver:
                     parsed_data = {
                         'signature': signature_str,
                         'sender': sender,
                         'receiver': receiver,
                         'amount': amount,
                         'timestamp': timestamp
                     }
                     await self.forensics.analyze_transaction(parsed_data)

        except Exception as e:
            logger.error(f"Error fetching/parsing {signature_str}: {e}")

    async def start(self):
        logger.info("Starting Listing Hunter...")
        
        # 1. Initialize Database
        await self.db.init_db()

        # 2. Load Targets
        # Start with config list, but also could load from DB
        targets = set(TARGET_TREASURY_LIST)
        db_targets = await self.db.get_targets()
        targets.update(db_targets)
        
        if not targets:
            logger.warning("No targets configured! Please add treasuries to config.py or DB.")
        else:
            logger.info(f"Loaded {len(targets)} targets into active radar:")
            for t in targets:
                logger.debug(f" -> Guarding: {t}") # Keep as debug or info depending on volume, INFO is fine for demo
                logger.info(f" -> Guarding: {t}")

        # 3. Initialize Listener
        self.listener = SolanaWebSocketListener(
            targets=targets,
            on_transaction=self.fetch_and_parse_transaction
        )

        # 4. Start Listening
        # Run listener in a task
        try:
            await self.listener.start()
        except asyncio.CancelledError:
            logger.info("Main loop cancelled")
        finally:
            await self.shutdown()

    async def shutdown(self):
        logger.info("Shutting down...")
        if self.listener:
            self.listener.stop()
        await self.rpc_client.close()

def handle_exit(signum, frame):
    raise KeyboardInterrupt

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    bot = ListingHunter()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        pass # Handle graceful exit via signal
