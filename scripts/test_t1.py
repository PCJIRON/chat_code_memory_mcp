"""Quick smoke test for T1 - ChatStore init and close."""
import sys
import os

# Ensure we import from the local src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from context_memory_mcp.chat_store import ChatStore

print("Creating ChatStore...")
store = ChatStore()
print(f"Chroma path: {store._chroma_path}")
print(f"Collection: {store._collection.name}")
print(f"Collection metadata: {store._collection.metadata}")

# Check that data directory was created
assert os.path.exists("./data/chromadb"), "data/chromadb directory should exist"
print(f"data/chromadb exists: {os.path.exists('./data/chromadb')}")

print("Closing ChatStore...")
store.close()
print("Close succeeded.")
print("T1 PASSED")
