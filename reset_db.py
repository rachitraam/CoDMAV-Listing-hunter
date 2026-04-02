import os
import sqlite3
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "listing_hunter.db"
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

def reset_all():
    print("🧹 [1/2] Resetting Local SQLite Database...")
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print("   ✅ Deleted listing_hunter.db")
        except Exception as e:
            print(f"   ❌ Error deleting SQLite DB: {e}")
    else:
        print("   ✅ SQLite DB already clear.")

    print("\n🧹 [2/2] Resetting Neo4j Knowledge Graph...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with driver.session() as session:
            # Cypher command to delete literally everything in the graph
            session.run("MATCH (n) DETACH DELETE n")
        print("   ✅ Wiped all nodes and relationships from Neo4j.")
    except Exception as e:
        print(f"   ❌ Neo4j Error: {e}")
        print("   (Make sure Neo4j Desktop is running before you execute this!)")

    print("\n✨ Complete! You have a 100% clean slate for your presentation.")

if __name__ == "__main__":
    confirm = input("Are you sure you want to WIPE all databases? (y/n): ")
    if confirm.lower() == 'y':
        reset_all()
    else:
        print("Cancelled.")
