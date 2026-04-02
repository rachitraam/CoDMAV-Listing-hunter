
from neo4j import GraphDatabase
import logging
from typing import List, Dict, Any, Optional
from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, get_logger

logger = get_logger("graph_manager")

class GraphManager:
    def __init__(self):
        self.driver = None
        try:
            self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            self.verify_connection()
            logger.info("Connected to Neo4j successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")

    def close(self):
        if self.driver:
            self.driver.close()

    def verify_connection(self):
        # Check if we can run a simple query
        with self.driver.session() as session:
            session.run("RETURN 1")

    def add_transfer(self, sender: str, receiver: str, amount: float, signature: str, timestamp: int, sender_type: str = "Unknown", receiver_type: str = "Unknown"):
        """
        Add a transfer relationship to the graph.
        Also merges (creates if not exists) the wallet nodes.
        """
        if not self.driver:
            return

        query = """
        MERGE (s:Wallet {address: $sender})
        MERGE (r:Wallet {address: $receiver})
        
        // Update types if known
        SET s.type = CASE WHEN $sender_type <> 'Unknown' THEN $sender_type ELSE s.type END
        SET r.type = CASE WHEN $receiver_type <> 'Unknown' THEN $receiver_type ELSE r.type END

        // Create transaction payload
        MERGE (s)-[t:TRANSFERRED {signature: $signature}]->(r)
        SET t.amount = $amount, t.timestamp = $timestamp
        """
        
        try:
            with self.driver.session() as session:
                session.run(query, sender=sender, receiver=receiver, amount=amount, signature=signature, timestamp=timestamp, sender_type=sender_type, receiver_type=receiver_type)
                logger.debug(f"Graph: Logged transfer {sender} -> {receiver}")
        except Exception as e:
            logger.error(f"Error adding transfer to graph: {e}")

    def find_path_to_cex(self, start_address: str, max_depth: int = 4) -> List[Any]:
        """
        Find any path from the start_address to a CEX node.
        """
        if not self.driver:
            return []

        # Assuming we label CEX wallets with type='CEX' manually or via config
        query = f"""
        MATCH p=(s:Wallet {{address: $start_address}})-[:TRANSFERRED*1..{max_depth}]->(c:Wallet {{type: 'CEX'}})
        RETURN p LIMIT 1
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(query, start_address=start_address)
                record = result.single()
                if record:
                    return record["p"]
                return []
        except Exception as e:
            logger.error(f"Error checking path to CEX: {e}")
            return []

    def find_treasury_origin(self, cex_address: str, max_depth: int = 4) -> List[Any]:
        """
        Find if a specific CEX deposit originated from a known Treasury.
        """
        if not self.driver:
            return []

        query = f"""
        MATCH p=(t:Wallet {{type: 'Treasury'}})-[:TRANSFERRED*1..{max_depth}]->(c:Wallet {{address: $cex_address}})
        RETURN p LIMIT 1
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(query, cex_address=cex_address)
                record = result.single()
                if record:
                    return record["p"]
                return []
        except Exception as e:
            logger.error(f"Error checking treasury origin: {e}")
            return []

    def mark_as_treasury(self, address: str):
        self._set_node_type(address, "Treasury")

    def mark_as_cex(self, address: str):
        self._set_node_type(address, "CEX")

    def _set_node_type(self, address: str, node_type: str):
        if not self.driver:
            return
        query = """
        MERGE (w:Wallet {address: $address})
        SET w.type = $type
        """
        try:
            with self.driver.session() as session:
                session.run(query, address=address, type=node_type)
        except Exception as e:
            logger.error(f"Error setting node type for {address}: {e}")
