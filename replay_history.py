import asyncio
import argparse
import logging
from solders.pubkey import Pubkey
from solders.signature import Signature

from main import ListingHunter
from config import get_logger

logger = get_logger("replay_history")

async def run_replay(treasury_address: str, fetch_limit: int, before_sig: str = None):
    logger.info(f"--- Starting Historical Replay for Treasury: {treasury_address} ---")
    if before_sig:
        logger.info(f"Jumping back in time. Fetching signatures immediately BEFORE: {before_sig}")
    logger.info(f"Setting fetch limit to: {fetch_limit} transactions.")

    # 1. Initialize the Core Engine (without starting the listener)
    hunter = ListingHunter()
    await hunter.db.init_db()
    
    # We must explicitly add this treasury to our tracking SQLite DB so the Forensics engine triggers 'is_sender_treasury'
    await hunter.db.add_target(treasury_address)
    
    # Also explicitly mark it in Neo4j
    hunter.forensics.graph.mark_as_treasury(treasury_address)

    try:
        pubkey = Pubkey.from_string(treasury_address)
        
        logger.info(f"Fetching up to {fetch_limit} signatures (Pagination enabled)...")
        
        signatures_data = []
        fetched_count = 0
        current_before_sig = before_sig
        
        while fetched_count < fetch_limit:
            # Solana RPC has a hard cap of 1000 per request
            batch_limit = min(150, fetch_limit - fetched_count)
            kwargs = {"limit": batch_limit}
            
            if current_before_sig:
                kwargs["before"] = Signature.from_string(current_before_sig)
                
            response = await hunter.rpc_client.get_signatures_for_address(pubkey, **kwargs)
            batch_sigs = response.value
            
            if not batch_sigs:
                logger.info("Reached the end of the wallet's history.")
                break
                
            signatures_data.extend(batch_sigs)
            fetched_count += len(batch_sigs)
            
            # Update the 'before' pointer to the last (oldest) signature in this chunk
            current_before_sig = str(batch_sigs[-1].signature)
            
            # Pause to respect Helius/RPC rate limits during heavy pagination
            await asyncio.sleep(0.5)
            
        if not signatures_data:
            logger.warning("No signatures found for this address.")
            return

        logger.info(f"Successfully fetched {len(signatures_data)} raw signatures total.")

        # --- SIGNATURE PRE-FILTERING ---
        valid_signatures = []
        for s in signatures_data:
            # 1. Discard Failed Transactions
            if s.err is not None:
                continue
            
            # (Optional) Time-bounding logic could be added here based on s.block_time
            # For simplicity, we rely on the `fetch_limit` for now.

            valid_signatures.append(str(s.signature))

        # We want to play them in chronological order (oldest first)
        valid_signatures.reverse()

        num_valid = len(valid_signatures)
        logger.info(f"After filtering failed transactions, {num_valid} valid signatures remain to process.")

        # --- PHASE 1: PROCESS TREASURY ---
        for i, sig_str in enumerate(valid_signatures, start=1):
            logger.info(f"[{i}/{num_valid}] Processing Transaction: {sig_str}")
            
            # Fetch the full transaction and run through Forensics & Graph
            await hunter.fetch_and_parse_transaction(sig_str)
            
            # RATE LIMIT PROTECTION: Sleep between requests
            # 1.5 seconds is usually safe for free-tier Helius/Mainnet endpoints
            await asyncio.sleep(1.5)

        # --- PHASE 2: CRAWL MULES ---
        logger.info("\n--- Phase 2: Crawling Discovered Mules ---")
        mules = await hunter.db.get_all_watchlist_addresses()
        
        if not mules:
            logger.info("No mules discovered during Treasury replay.")
        else:
            logger.info(f"Discovered {len(mules)} mules. Fetching their history...")
            
            for mule_address in mules:
                logger.info(f"Crawling Mule: {mule_address} (Anchored to {before_sig or 'Latest'})")
                try:
                    mule_pubkey = Pubkey.from_string(mule_address)
                    
                    mule_kwargs = {"limit": 1000}
                    if before_sig:
                        mule_kwargs["before"] = Signature.from_string(before_sig)
                        
                    mule_resp = await hunter.rpc_client.get_signatures_for_address(
                        mule_pubkey,
                        **mule_kwargs
                    )
                    
                    if not mule_resp.value:
                        continue
                        
                    mule_sigs = [str(s.signature) for s in mule_resp.value if s.err is None]
                    mule_sigs.reverse()
                    
                    for sig_str in mule_sigs:
                        await hunter.fetch_and_parse_transaction(sig_str)
                        await asyncio.sleep(1.5)
                        
                except Exception as e:
                    logger.error(f"Error crawling mule {mule_address}: {e}")
                    continue

        logger.info("--- Historical Replay Complete ---")
        logger.info("Check Streamlit dashboard or run visualize_graph.py to view detected paths!")

    except Exception as e:
        logger.error(f"Replay Error: {e}")
    finally:
        await hunter.rpc_client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay historical transactions into the Listing Hunter engine.")
    parser.add_argument("treasury", type=str, help="The Solana Treasury Wallet address.")
    parser.add_argument("--limit", type=int, default=50, help="Max number of signatures to fetch (default: 50).")
    parser.add_argument("--before", type=str, default=None, help="Signature to start searching backward from (e.g., the CEX listing announcement TX).")
    
    args = parser.parse_args()
    
    # Ensure logging is at least INFO to see output
    logging.getLogger().setLevel(logging.INFO)
    
    asyncio.run(run_replay(args.treasury, args.limit, args.before))
