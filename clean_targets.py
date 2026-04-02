
import asyncio
import time
from datetime import datetime
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from db_manager import DatabaseManager
from config import SOLANA_RPC_HTTP_URL

# Thresholds for "Noisy"
# If a wallet has >= 5 transactions in the last 60 minutes, it's too active for a "Treasury".
MAX_RECENT_TXS = 5
TIME_WINDOW_SECONDS = 60 * 60 # 1 Hour

async def clean_db():
    print(f"Connecting to RPC: {SOLANA_RPC_HTTP_URL}")
    db = DatabaseManager()
    await db.init_db()
    
    targets = await db.get_targets()
    total_targets = len(targets)
    print(f"Scanning {total_targets} targets for noise...")
    
    client = AsyncClient(SOLANA_RPC_HTTP_URL)
    removed_count = 0
    
    try:
        # Loop through a copy so we can modify the original set/db if needed (though we delete from DB directly)
        for i, address in enumerate(list(targets)):
            try:
                if i % 10 == 0:
                    print(f"Progress: {i}/{total_targets}...")

                pubkey = Pubkey.from_string(address)
                # fetch last few signatures
                resp = await client.get_signatures_for_address(pubkey, limit=MAX_RECENT_TXS)
                
                if resp.value and len(resp.value) >= MAX_RECENT_TXS:
                    # Check the timestamp of the oldest one in this batch of 5
                    oldest_in_batch = resp.value[-1]
                    
                    if oldest_in_batch.block_time:
                        age = time.time() - oldest_in_batch.block_time
                        
                        if age < TIME_WINDOW_SECONDS:
                            # It has 5 txs in less than 1 hour -> NOISY
                            print(f"❌ REMOVING [Noisy]: {address} ({len(resp.value)} txs in {int(age/60)} mins)")
                            await db.remove_target(address)
                            removed_count += 1
                            continue
                
                # If we get here, it's safe (or safer)
                # print(f"✅ KEEP: {address}")

            except Exception as e:
                print(f"⚠️ Error checking {address}: {e}")
                # Optional: Remove invalid addresses?
                # await db.remove_target(address)
                
    finally:
        await client.close()
    
    print("-" * 30)
    print(f"Cleanup Complete.")
    print(f"Removed: {removed_count}")
    print(f"Remaining: {total_targets - removed_count}")

if __name__ == "__main__":
    asyncio.run(clean_db())
