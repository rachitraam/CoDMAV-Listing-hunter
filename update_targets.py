
import asyncio
import logging
from db_manager import DatabaseManager
from target_finder import TargetFinder
from config import get_logger

logger = get_logger("update_targets")

async def main():
    logger.info("Starting Target Discovery Process...")
    
    # Initialize DB
    db = DatabaseManager()
    await db.init_db()
    
    # Initialize Finder
    finder = TargetFinder()
    
    # Find Candidates
    candidates = await finder.find_candidates()
    
    if not candidates:
        logger.info("No new candidates found.")
        return

    logger.info(f"Found {len(candidates)} tokens with potential treasuries.")
    
    # Update Database
    count = 0
    for item in candidates:
        symbol = item['symbol']
        mint = item['mint']
        potential_treasuries = item['candidates']
        
        logger.info(f"Adding targets for {symbol} ({mint}):")
        for treasury in potential_treasuries:
            # We add them to the DB's target list
            # Note: In a real app, we might want a separate table for 'candidates' 
            # vs 'confirmed targets', but for this MVP we treat them as targets to watch.
            
            # Check if already exists to avoid log noise (add_target handles ignore, but for logging)
            await db.add_target(treasury)
            logger.info(f"  + {treasury}")
            count += 1
            
    logger.info(f"Successfully added/updated {count} treasury addresses to the database.")
    logger.info("Run 'python main.py' to start monitoring these targets.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error in update_targets: {e}")
