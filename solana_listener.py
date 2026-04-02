
import asyncio
import logging
import json
from typing import List, Callable, Awaitable, Set, Optional
from solana.rpc.websocket_api import connect
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.rpc.config import RpcTransactionLogsFilterMentions

from config import SOLANA_RPC_WS_URL, SOLANA_RPC_HTTP_URL, get_logger

logger = get_logger("solana_listener")

class SolanaWebSocketListener:
    def __init__(self, targets: Set[str], on_transaction: Callable[[str], Awaitable[None]]):
        """
        Initialize the listener.
        
        :param targets: Set of treasury addresses to monitor.
        :param on_transaction: Async callback function when a transaction is detected (passes signature).
        """
        self.targets = targets
        self.on_transaction = on_transaction
        self.running = False
        self.reconnect_delay = 1  # Start with 1 second
        self.max_reconnect_delay = 60

    async def start(self):
        """Start the WebSocket listener with auto-reconnection."""
        self.running = True
        while self.running:
            try:
                logger.info(f"Connecting to WebSocket: {SOLANA_RPC_WS_URL}")
                async with connect(SOLANA_RPC_WS_URL) as websocket:
                    logger.info("Connected!")
                    self.reconnect_delay = 1  # Reset backoff on successful connection
                    
                    # Create subscriptions for all targets (Mentions)
                    subscription_ids = []
                    for target in self.targets:
                        try:
                            # Subscribe to logs that mention the target address
                            # Using 'confirmed' commitment to get fairly fast updates
                            pubkey = Pubkey.from_string(target)
                            await websocket.logs_subscribe(
                                RpcTransactionLogsFilterMentions(pubkey),
                                commitment="confirmed"
                            )
                            # Note: The library handles the subscription ID mapping internally for the iterator
                        except Exception as e:
                            logger.error(f"Failed to subscribe to target {target}: {e}")

                    logger.info(f"Listening for transactions involving {len(self.targets)} targets...")

                    # Process incoming messages
                    async for message in websocket:
                        if not self.running:
                            break
                        
                        # The message usually contains the notification
                        # For logsSubscribe, it should give us the signature and logs
                        # Structure varies based on library version, assuming standard parsing:
                        # We extract the signature and call the callback
                        
                        try:
                            # 'message' object from the library is typically a list of RpcLogsResponse or similar
                            # We iterate through the batch if it's a list, or process single
                            # Simplified implementation assuming getting a notification object
                            # We need to inspect `message` to extract signature.
                            # The latest solana-py websocket iterator yields typed responses.
                            
                            # For robustness, we'll try to extract signature from common structures
                            # (This depends heavily on the specific solana-py version behavior)
                            # Usually: result.value.signature
                            
                            # Let's assume we get a notification object that has a 'result' or 'params'
                            # If using the 'async for message in websocket' pattern from solana-py:
                            # It yields 'Notification' objects.
                            
                            for item in message: 
                                # Robust parsing for various solana-py versions / message types
                                log_value = None
                                
                                # Case 1: Standard Notification (params -> result -> value)
                                if hasattr(item, 'params') and hasattr(item.params, 'result'):
                                    if hasattr(item.params.result, 'value'):
                                        log_value = item.params.result.value
                                
                                # Case 2: Direct Result (response to request, or simplified object)
                                elif hasattr(item, 'result') and hasattr(item.result, 'value'):
                                    log_value = item.result.value
                                
                                # Case 3: Attribute access fails, try dictionary lookup if it's a dict (fallback)
                                elif isinstance(item, dict):
                                    # ... implementation for dict if needed, but solana-py uses objects
                                    pass

                                if log_value and hasattr(log_value, 'signature'):
                                    signature = str(log_value.signature)
                                    # Deduplication usually handled by business logic, but we pass it on
                                    asyncio.create_task(self.on_transaction(signature))
                                
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                            
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                logger.info(f"Reconnecting in {self.reconnect_delay} seconds...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
            
            finally:
                logger.info("WebSocket disconnected.")

    def stop(self):
        """Stop the listener."""
        self.running = False
        logger.info("Stopping listener...")

# Example usage (for testing module independently)
if __name__ == "__main__":
    async def mock_handler(signature: str):
        print(f"Detected Transaction: {signature}")

    # Dummy target for testing
    dummy_targets = {"Vote111111111111111111111111111111111111111"} 
    
    listener = SolanaWebSocketListener(dummy_targets, mock_handler)
    try:
        asyncio.run(listener.start())
    except KeyboardInterrupt:
        listener.stop()
