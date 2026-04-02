
import os
import logging
from typing import List, Set

from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# --- RPC Configuration ---
# Replace with your actual Helius RPC URL (or other provider)
# Best practice: Load from environment variables
SOLANA_RPC_HTTP_URL = os.getenv("SOLANA_RPC_HTTP_URL", "https://api.mainnet-beta.solana.com")
SOLANA_RPC_WS_URL = os.getenv("SOLANA_RPC_WS_URL", "wss://api.mainnet-beta.solana.com")
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"

# --- Neo4j Configuration (Knowledge Graph) ---
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# --- Constants & Thresholds ---
MAX_TEST_TX_AMOUNT = 999_999_999_999.0  # Increased massively to account for Meme coin token amounts
WATCHLIST_EXPIRY_SECONDS = 24 * 60 * 60  # 24 hours

# --- Excluded Exchanges (for Target Discovery) ---
EXCLUDED_EXCHANGES = {
    "binance",
    "coinbase",
    "bybit",
    "kraken",
    "kucoin",
    "okx"
}

# --- Target Treasuries (Initial List) ---
# Add known treasury addresses here.
# In production, this might be loaded from a DB or external API.
TARGET_TREASURY_LIST: Set[str] = {
}

# --- CEX Hot Wallets (Known) ---
# Add known CEX hot wallet addresses here.
# Source: Public Explorers (Solscan/SolanaFM)
CEX_HOT_WALLET_ADDRESSES: Set[str] = {
    # Binance # Hot Wallet 2
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", # Hot Wallet 3
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",
    "3gd3dqgtJ4jWfBfLYTX67DALFetjc5iS72sCgRhCkW2u",
    "GBrURzmtWujJRTA3Bkvo7ZgWuZYLMMwPCwre7BejJXnK",
    "6QJzieMYfp7yr3EdrePaQoG3Ghxs2wM98xSLRu8Xh56U",
    "38xCLm9kSExfGU1GdyVuX4vop7SZns9kU2mQyTmmMdUP",
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
     # Linked Hot Wallet
    
    # Kraken
    "6LY1JzAFVZsP2a2xKrtU6znQMQ5h4i7tocWdgrkZzkzF", # Kraken Main Hot Wallet
    
    # Coinbase
    # Coinbase uses diverse deposit addresses; hard to track single hot wallet.
    # Recommended: Use Graph Analysis to cluster deposit addresses.
}

# --- Database Configuration ---
DB_PATH = "listing_hunter.db"

# --- Logging Configuration ---
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("listing_hunter.log")
    ]
)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
