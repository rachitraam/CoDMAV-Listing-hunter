
import aiosqlite
import logging
import time
from typing import List, Optional, Set
from config import DB_PATH, WATCHLIST_EXPIRY_SECONDS, get_logger

logger = get_logger("db_manager")

class DatabaseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Initialize the database tables."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS target_treasuries (
                        address TEXT PRIMARY KEY
                    )
                """)
                # Updated Schema for Multi-Hop
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS watchlist (
                        address TEXT PRIMARY KEY,
                        expiry_timestamp INTEGER,
                        origin_treasury TEXT,
                        parent_wallet TEXT,
                        depth INTEGER DEFAULT 0
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS transactions (
                        signature TEXT PRIMARY KEY,
                        sender TEXT,
                        receiver TEXT,
                        amount REAL,
                        timestamp INTEGER
                    )
                """)
                # Migration: Try to add columns if they don't exist (for existing DBs)
                columns_to_add = [
                    ("origin_treasury", "TEXT"),
                    ("parent_wallet", "TEXT"),
                    ("depth", "INTEGER DEFAULT 0")
                ]
                for col_name, col_type in columns_to_add:
                    try:
                        await db.execute(f"ALTER TABLE watchlist ADD COLUMN {col_name} {col_type}")
                    except Exception:
                        pass # Column likely exists

                await db.commit()
                logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def add_target(self, address: str):
        """Add a treasury address to the target list."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO target_treasuries (address) VALUES (?)",
                    (address,)
                )
                await db.commit()
                logger.info(f"Added target: {address}")
        except Exception as e:
            logger.error(f"Error adding target {address}: {e}")

    async def remove_target(self, address: str):
        """Remove a treasury address from the target list."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM target_treasuries WHERE address = ?",
                    (address,)
                )
                await db.commit()
                logger.info(f"Removed target: {address}")
        except Exception as e:
            logger.error(f"Error removing target {address}: {e}")

    async def get_targets(self) -> Set[str]:
        """Retrieve all target treasury addresses."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT address FROM target_treasuries") as cursor:
                    rows = await cursor.fetchall()
                    return {row[0] for row in rows}
        except Exception as e:
            logger.error(f"Error retrieving targets: {e}")
            return set()


    async def add_to_watchlist(self, address: str, origin_treasury: Optional[str] = None, parent_wallet: Optional[str] = None, depth: int = 0, expiry_seconds: int = WATCHLIST_EXPIRY_SECONDS):
        """Add a wallet to the watchlist with genealogy info."""
        expiry_timestamp = int(time.time()) + expiry_seconds
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO watchlist 
                    (address, expiry_timestamp, origin_treasury, parent_wallet, depth) 
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (address, expiry_timestamp, origin_treasury, parent_wallet, depth)
                )
                await db.commit()
                logger.info(f"Watchlist: {address} (Depth: {depth}, Origin: {origin_treasury})")
        except Exception as e:
            logger.error(f"Error adding to watchlist {address}: {e}")

    async def get_watchlist_entry(self, address: str) -> Optional[dict]:
        """Retrieve full details for a watched wallet."""
        current_time = int(time.time())
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM watchlist WHERE address = ? AND expiry_timestamp > ?",
                    (address, current_time)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return dict(row)
                    return None
        except Exception as e:
            logger.error(f"Error getting watchlist entry {address}: {e}")
            return None

    async def is_in_watchlist(self, address: str) -> bool:
        """Check if an address is currently in the watchlist and not expired."""
        return (await self.get_watchlist_entry(address)) is not None

    async def get_all_watchlist_addresses(self) -> List[str]:
        """Retrieve all currently watched wallets."""
        current_time = int(time.time())
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT address FROM watchlist WHERE expiry_timestamp > ?",
                    (current_time,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error getting all watchlist entries: {e}")
            return []

    async def cleanup_watchlist(self):
        """Remove expired entries from the watchlist."""
        current_time = int(time.time())
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM watchlist WHERE expiry_timestamp <= ?",
                    (current_time,)
                )
                await db.commit()
                logger.info("Cleaned up expired watchlist entries.")
        except Exception as e:
            logger.error(f"Error cleaning up watchlist: {e}")

    async def log_transaction(self, signature: str, sender: str, receiver: str, amount: float):
        """Log a relevant transaction."""
        timestamp = int(time.time())
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO transactions (signature, sender, receiver, amount, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (signature, sender, receiver, amount, timestamp)
                )
                await db.commit()
                logger.info(f"Logged transaction: {signature}")
        except Exception as e:
            logger.error(f"Error logging transaction {signature}: {e}")
