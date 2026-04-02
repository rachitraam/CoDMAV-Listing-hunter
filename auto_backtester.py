import asyncio
import logging
from typing import List, Dict

from target_finder import TargetFinder
from replay_history import run_replay
from config import get_logger

logger = get_logger("auto_backtester")

# --- BACKTEST CONFIGURATION ---
# Format: "Token Symbol": {"treasury": "Deployer Wallet Address", "anchor_sig": "Signature right after listing announcement"}
# Example uses known successful Binance listings.
TEST_TOKENS: Dict[str, Dict[str, str]] = {
#     "BOME": {
#         "treasury": "E4X8Fihh8RHwwtCPN4XFUFc1F7iygBX3evfLjQnMFak9", # True Creator Treasury
#         # Example anchor: A known signature on the day it listed
#         "anchor_sig": "4qew7Ai5L5BxVm67SXanFbackKcMBp3sRaaajkfjVLo6h1dygqH3UVVssmZDUtYTLQTyPnhAWgCGxwrTfXdrerwE" 
#     },
    "WIF": {
        "treasury": "wifq4CRwpXCK8NYtKNsQAYoDethT1aR7R1DaKCLFgAd", # Replace with WIF Treasury you find on Solscan
        "anchor_sig": "52gdVYQ1muSm1GLoWne79GPNjVHGL3x2gMwMasHNNaD46SsBwD8Lb7iT8uE8vC7bAc2D3hzsVXAtFbhBH1rk11Mt" # Replace with November 2023 WIF signature
    },
#     "BONK": {
#         "treasury": "BonkTreasuryAddressHere", # Replace with BONK Treasury you find on Solscan
#         "anchor_sig": "BonkAnchorSignatureHere" # Replace with December 2022 BONK signature
#     }
}

# How many transactions just before the anchor should we process?
TRANSACTION_LIMIT_PER_TREASURY = 1000

async def run_automated_backtest():
    logger.info("="*50)
    logger.info("  🚀 STARTING FULLY AUTOMATED BACKTESTER 🚀  ")
    logger.info("="*50)
    
    finder = TargetFinder()
    
    scorecard = {
        "tested": 0,
        "treasuries_found": 0,
        "errors": 0
    }
    
    try:
        for symbol, data in TEST_TOKENS.items():
            treasury_address = data.get("treasury")
            anchor = data.get("anchor_sig")
            
            logger.info(f"\n--- [Phase A] Setting Target for {symbol} ---")
            scorecard["tested"] += 1
            
            if not treasury_address:
                logger.warning(f"No treasury address correctly configured for {symbol}. Skipping.")
                scorecard["errors"] += 1
                continue
                
            logger.info(f"✅ Loaded Primary Treasury for {symbol}: {treasury_address}")
            scorecard["treasuries_found"] += 1
            
            # Let the API breathe 
            await asyncio.sleep(1.0)
            
            logger.info(f"\n--- [Phase B] Historical Replay for {symbol} Treasury ---")
            
            # Execute the Replay Engine logic exactly as if the user ran the CLI!
            try:
                 await run_replay(
                     treasury_address=treasury_address, 
                     fetch_limit=TRANSACTION_LIMIT_PER_TREASURY,
                     before_sig=anchor
                 )
            except Exception as e:
                 logger.error(f"Replay failed for {symbol}: {e}")
                 scorecard["errors"] += 1
                 
            # Big pause before moving to the next token to ensure RPC rate limits clear
            logger.info(f"Cooling down for 5 seconds before next token...")
            await asyncio.sleep(5.0)
            
    finally:
        await finder.rpc_client.close()
        
    logger.info("="*50)
    logger.info("          📊 BACKTEST SCORECARD 📊          ")
    logger.info("="*50)
    logger.info(f"Tokens Configured: {len(TEST_TOKENS)}")
    logger.info(f"Tokens Processed:  {scorecard['tested']}")
    logger.info(f"Treasuries Found:  {scorecard['treasuries_found']}")
    logger.info(f"Test Errors:       {scorecard['errors']}")
    logger.info("Check Streamlit 'Threat Graph' or 'visualize_graph.py' to see if Wash Trades were caught!")

if __name__ == "__main__":
    # Ensure logs output to console
    logging.getLogger().setLevel(logging.INFO)
    asyncio.run(run_automated_backtest())
