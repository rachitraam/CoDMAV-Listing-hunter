
import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional, Set, Callable, Any
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TokenAccountOpts

from config import (
    COINGECKO_API_URL, 
    EXCLUDED_EXCHANGES, 
    SOLANA_RPC_HTTP_URL,
    get_logger
)

logger = get_logger("target_finder")

class TargetFinder:
    def __init__(self):
        self.rpc_client = AsyncClient(SOLANA_RPC_HTTP_URL)

    async def _rpc_call_with_retry(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Helper to execute RPC calls with retries on 429 errors.
        """
        max_retries = 5
        base_delay = 3.0
        
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                is_rate_limit = False
                error_msg = str(e).lower()
                
                # Check 1: Direct String Match
                if "429" in error_msg or "too many requests" in error_msg:
                    is_rate_limit = True
                
                # Check 2: Response Status Code (direct)
                elif hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                     if e.response.status_code == 429:
                         is_rate_limit = True

                # Check 3: Nested Cause (Wrapper Exceptions)
                elif e.__cause__:
                    cause = e.__cause__
                    cause_msg = str(cause).lower()
                    if "429" in cause_msg or "too many requests" in cause_msg:
                        is_rate_limit = True
                    elif hasattr(cause, 'response') and hasattr(cause.response, 'status_code'):
                        if cause.response.status_code == 429:
                            is_rate_limit = True

                # Check 4: Blind Retry for SolanaRpcException
                # If we see this specific wrapper and we know we are hitting rate limits, assume it's a 429 to be safe
                if not is_rate_limit and type(e).__name__ == "SolanaRpcException":
                    logger.warning(f"Encoutered generic SolanaRpcException. Assuming 429. Debug: {repr(e)}")
                    is_rate_limit = True

                if is_rate_limit:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"RPC Rate Limit (429) on attempt {attempt+1}/{max_retries}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    # Log unexpected error to help debugging
                    logger.error(f"RPC Error (Non-Retriable): {repr(e)} | Type: {type(e)}")
                    try:
                        if e.__cause__:
                            logger.error(f"Cause: {repr(e.__cause__)}")
                    except:
                        pass
                    raise e 
        
        logger.error("Max retries exceeded for RPC call.")
        return None

    async def get_top_solana_tokens(self, limit: int = 250) -> List[Dict]:
        """
        Fetch top Solana ecosystem tokens from CoinGecko.
        """
        url = f"{COINGECKO_API_URL}/coins/markets"
        params = {
            "vs_currency": "usd",
            "category": "solana-ecosystem",
            "order": "market_cap_desc",
            "per_page": limit,
            "page": 1,
            "sparkline": "false"
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                # Rate limit safety
                await asyncio.sleep(1.0)
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        logger.warning("CoinGecko 429 (Top Tokens). Sleeping 30s...")
                        await asyncio.sleep(30)
                        return []
                    else:
                        logger.error(f"CoinGecko API Error (Top Tokens): {response.status}")
                        return []
            except Exception as e:
                logger.error(f"Failed to fetch tokens from CG: {e}")
                return []

    async def get_exchange_tickers(self, exchange_id: str, pages: int = 2) -> Set[str]:
        """
        Fetch listed token IDs from an exchange.
        limiting to 'pages' pages of tickers (usually sorted by volume).
        """
        url = f"{COINGECKO_API_URL}/exchanges/{exchange_id}/tickers"
        listed_ids = set()
        
        async with aiohttp.ClientSession() as session:
            for page in range(1, pages + 1):
                params = {"page": page, "depth": "false"} 
                
                try:
                    # Rate limit pause between pages/exchanges
                    await asyncio.sleep(1.5) 
                    
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            tickers = data.get('tickers', [])
                            for ticker in tickers:
                                # The 'coin_id' is the unique CG ID (e.g., 'solana')
                                coin_id = ticker.get('coin_id')
                                if coin_id:
                                    listed_ids.add(coin_id)
                        elif response.status == 404:
                            logger.warning(f"Exchange {exchange_id} not found on CG.")
                            break
                        elif response.status == 429:
                            logger.warning(f"Exchange {exchange_id} 429. Sleeping 30s...")
                            await asyncio.sleep(30)
                            # Retry current page logic skipped for simplicity, just break
                            break
                        else:
                            logger.warning(f"Error fetching {exchange_id} page {page}: {response.status}")
                            break
                except Exception as e:
                    logger.error(f"Failed to fetch tickers for {exchange_id}: {e}")
                    
        return listed_ids

    async def build_blacklist(self) -> Set[str]:
        """
        Aggregates listed token IDs from all excluded exchanges.
        This runs once at the start.
        """
        logger.info("Building Exchange Blacklist (Pre-fetching)...")
        blacklist = set()
        
        # Add basic coins that are definitely listed everywhere to save calls
        defaults = {"solana", "usd-coin", "tether", "wrapped-solana"}
        blacklist.update(defaults)

        for exchange in EXCLUDED_EXCHANGES:
            logger.info(f"Fetching listings from {exchange}...")
            # Fetch generic listings
            ids = await self.get_exchange_tickers(exchange)
            blacklist.update(ids)
            logger.info(f"-> Added {len(ids)} tokens from {exchange}")
            
        logger.info(f"Blacklist complete. Total listed tokens to ignore: {len(blacklist)}")
        return blacklist

    async def get_details_and_mint(self, token_id: str) -> Optional[str]:
        """
        Fetch token details to get the mint address (contract address).
        """
        url = f"{COINGECKO_API_URL}/coins/{token_id}"
        max_retries = 3
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(max_retries):
                try:
                    # Rate limit
                    await asyncio.sleep(2.0) # Increased base sleep
                    
                    params = {
                        "localization": "false", 
                        "tickers": "false", 
                        "community_data": "false", 
                        "developer_data": "false"
                    }
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            platforms = data.get('platforms', {})
                            # Also check 'detail_platforms' just in case
                            if not platforms:
                                platforms = data.get('detail_platforms', {})
                            
                            # Log warning if no platforms found, might be a different structure
                            if not platforms:
                                logger.debug(f"No platform data for {token_id}")
                                
                            return platforms.get('solana') or platforms.get('solana-ecosystem')
                        
                        elif response.status == 429:
                            delay = 15 * (attempt + 1)
                            logger.warning(f"Rate limit hit fetching details for {token_id}. Sleeping {delay}s...")
                            await asyncio.sleep(delay)
                            continue # RETRY!
                        
                        elif response.status == 404:
                            logger.warning(f"Token {token_id} not found on CoinGecko details.")
                            return None
                        
                        else:
                            logger.warning(f"Error fetching details {token_id}: {response.status}")
                            return None
                            
                except Exception as e:
                    logger.error(f"Exception fetching details {token_id}: {e}")
                    return None
            
            logger.error(f"Max retries for details {token_id}")
            return None

    async def get_top_holders(self, mint_address: str, limit: int = 5) -> List[str]:
        """
        Get top token holders (potential Treasury/Team wallets).
        Uses retry logic for RPC.
        """
        try:
            pubkey = Pubkey.from_string(mint_address)
            
            # Use retry wrapper for the main RPC call
            resp = await self._rpc_call_with_retry(
                self.rpc_client.get_token_largest_accounts, 
                pubkey, 
                commitment="confirmed"
            )
            
            candidates = []
            if resp and resp.value:
                for account in resp.value[:limit]:
                    # Handle both String and Pubkey types for address
                    if isinstance(account.address, Pubkey):
                        token_acc_pubkey = account.address
                    else:
                        token_acc_pubkey = Pubkey.from_string(str(account.address))
                    
                    # Fetch account info to get owner (also with retry)
                    acc_info = await self._rpc_call_with_retry(
                        self.rpc_client.get_account_info,
                        token_acc_pubkey
                    )
                    
                    if acc_info and acc_info.value:
                        # Simple parsing: Owner is at offset 32 for SPL Token Layout
                        data = acc_info.value.data
                        if isinstance(data, bytes) and len(data) >= 64:
                            owner_bytes = data[32:64]
                            owner = str(Pubkey.from_bytes(owner_bytes))
                            candidates.append(owner)
            
            return candidates
        except Exception as e:
            # Enhanced error logging
            logger.error(f"Error getting top holders for {mint_address}: {repr(e)}")
            return []

    async def find_candidates(self) -> List[Dict]:
        """
        Main orchestration method.
        """
        # 1. Build Blacklist (The "Inverted" Strategy)
        blacklist = await self.build_blacklist()
        
        logger.info("Fetching top Solana tokens...")
        tokens = await self.get_top_solana_tokens(limit=100)
        
        results = []
        
        for token in tokens:
            symbol = token.get('symbol')
            token_id = token.get('id')
            
            # 2. Filter using Blacklist (Local Check)
            if token_id in blacklist:
                # logger.debug(f"Skipping {symbol} (Listed)")
                continue
                
            logger.info(f"Analyzing potential candidate: {symbol} ({token_id})")
            
            # 3. Get Mint Address
            mint = await self.get_details_and_mint(token_id)
            if mint:
                # 4. Find Treasury Candidates
                holders = await self.get_top_holders(mint)
                if holders:
                    results.append({
                        'symbol': symbol,
                        'mint': mint,
                        'candidates': holders
                    })
                    logger.info(f"-> Found {len(holders)} treasury candidates for {symbol}")
                
                # Crucial: Add delay between processing tokens to avoid hitting RPC rate limits
                # Increased safety delay
                await asyncio.sleep(2.5) 
            else:
                 logger.warning(f"Could not find Solana Mint for {symbol}")
                 
        await self.rpc_client.close()
        return results

if __name__ == "__main__":
    from db_manager import DatabaseManager
    
    async def run_and_save():
        logger.info("Initializing Target Finder and Database...")
        finder = TargetFinder()
        db = DatabaseManager()
        await db.init_db()
        
        try:
            results = await finder.find_candidates()
            added = 0
            for r in results:
                for candidate in r.get('candidates', []):
                    await db.add_target(candidate)
                    added += 1
                    
            logger.info(f"====== DISCOVERY COMPLETE ======")
            logger.info(f"Discovered {len(results)} unlisted tokens.")
            logger.info(f"Successfully injected {added} Treasury Candidates into the live database!")
        except Exception as e:
            logger.error(f"Execution Error: {e}")

    asyncio.run(run_and_save())
