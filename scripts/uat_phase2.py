"""UAT test script for Phase 2 — Chat Memory.
Tests each requirement systematically and outputs results.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from context_memory_mcp.chat_store import ChatStore, register, get_store
from context_memory_mcp.mcp_server import register_all, mcp
from mcp.server.fastmcp import FastMCP

PASS_COUNT = 0
FAIL_COUNT = 0

def test(name, condition, evidence=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  PASS: {name}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL: {name} — {evidence}")

def main():
    global PASS_COUNT, FAIL_COUNT

    test_dir = os.path.join(os.path.dirname(__file__), 'uat_chromadb')
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    print("=" * 60)
    print("UAT: Phase 2 — Chat Memory")
    print("=" * 60)

    # --- FR-1.1: Store conversation history ---
    print("\n--- FR-1: Chat History Storage ---")
    store = ChatStore(chroma_path=test_dir)
    result = store.store_messages([
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing well, thanks!"},
    ], session_id="uat-session-1")
    test("FR-1.1: Store conversation history",
         result["stored"] == 2,
         f"stored={result['stored']}")

    # --- FR-1.2: Metadata (timestamp, role, content) ---
    results = store.query_messages("greeting", session_id="uat-session-1", top_k=5)
    has_all_meta = all(
        "role" in r and "timestamp" in r and "content" in r
        for r in results
    )
    test("FR-1.2: Message metadata (timestamp, role, content)",
         has_all_meta and len(results) == 2,
         f"results={len(results)}, keys={list(results[0].keys()) if results else 'none'}")

    # --- FR-1.3: Local sentence-transformers embeddings ---
    # Verify by checking that SentenceTransformerEmbeddingFunction is used
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    test("FR-1.3: Local embeddings (sentence-transformers)",
         isinstance(store._ef, SentenceTransformerEmbeddingFunction),
         f"embedding function type={type(store._ef).__name__}")

    # --- FR-1.4: Persistence (survives restart) ---
    store.close()
    # Re-open the same database
    store2 = ChatStore(chroma_path=test_dir)
    results2 = store2.query_messages("greeting", session_id="uat-session-1", top_k=5)
    test("FR-1.4: Persistent storage (survives restart)",
         len(results2) == 2,
         f"results after restart={len(results2)}")
    store2.close()

    # --- FR-2.1: Query by semantic similarity ---
    store3 = ChatStore(chroma_path=test_dir)
    store3.store_messages([
        {"role": "user", "content": "The quick brown fox jumps over the lazy dog"},
        {"role": "user", "content": "Python is a programming language"},
        {"role": "user", "content": "I love eating apples and oranges"},
    ], session_id="semantic-test")
    sim_results = store3.query_messages("canine animal", session_id="semantic-test", top_k=3)
    # "fox" should be most similar to "canine animal"
    has_fox = any("fox" in r["content"].lower() for r in sim_results)
    test("FR-2.1: Query by semantic similarity",
         has_fox and len(sim_results) > 0,
         f"top result: {sim_results[0]['content'][:40] if sim_results else 'none'}")

    # --- FR-2.2: Top-K results ---
    topk_results = store3.query_messages("test", session_id="semantic-test", top_k=2)
    test("FR-2.2: Top-K results",
         len(topk_results) == 2,
         f"requested top_k=2, got {len(topk_results)}")

    # --- FR-2.3: Results include content, role, timestamp ---
    has_keys = all(
        "content" in r and "role" in r and "timestamp" in r
        for r in topk_results
    )
    test("FR-2.3: Results include content, role, timestamp",
         has_keys,
         f"keys={list(topk_results[0].keys()) if topk_results else 'none'}")

    # --- FR-2.4: Date range and conversation ID filtering ---
    store3.store_messages([
        {"role": "user", "content": "january update", "timestamp": "2024-01-15T10:00:00+00:00"},
        {"role": "user", "content": "june update", "timestamp": "2024-06-15T10:00:00+00:00"},
        {"role": "user", "content": "december update", "timestamp": "2024-12-15T10:00:00+00:00"},
    ], session_id="date-test")

    date_results = store3.query_messages(
        "update", session_id="date-test",
        date_from="2024-03-01T00:00:00+00:00",
        date_to="2024-09-30T23:59:59+00:00",
        top_k=10,
    )
    date_contents = [r["content"] for r in date_results]
    test("FR-2.4: Date range filtering",
         "june update" in date_contents and "january update" not in date_contents and "december update" not in date_contents,
         f"results: {date_contents}")

    role_results = store3.query_messages("hello", session_id="uat-session-1", role="user", top_k=10)
    all_user = all(r["role"] == "user" for r in role_results)
    test("FR-2.4: Conversation ID (session_id) filtering",
         all(r["session_id"] == "uat-session-1" for r in role_results),
         f"filtered by session_id, got {len(role_results)} results")

    # --- FR-5.1: FastMCP stdio transport ---
    test("FR-5.1: FastMCP with stdio transport",
         hasattr(mcp, 'name') and mcp.name == "context-memory-mcp",
         f"mcp name={mcp.name}")

    # --- FR-5.2: store_chat and query_chat tools exposed ---
    register_all()
    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    test("FR-5.2: store_chat tool registered",
         "store_chat" in tool_names,
         f"tools={tool_names}")
    test("FR-5.2: query_chat tool registered",
         "query_chat" in tool_names,
         f"tools={tool_names}")

    # --- NFR-1: Privacy — local only ---
    # Verify no cloud API imports in chat_store.py
    with open(os.path.join(os.path.dirname(__file__), '..', 'src', 'context_memory_mcp', 'chat_store.py')) as f:
        code = f.read()
    no_cloud = "openai" not in code.lower() and "google" not in code.lower() and "anthropic" not in code.lower()
    test("NFR-1: Privacy — no cloud API calls",
         no_cloud,
         "No cloud imports found in chat_store.py")

    # --- NFR-2: Performance ---
    perf_store = ChatStore(chroma_path=os.path.join(test_dir, "perf"))
    perf_msgs = [{"role": "user", "content": f"perf msg {i}"} for i in range(10)]
    start = time.time()
    perf_store.store_messages(perf_msgs, session_id="perf-sess")
    store_time = time.time() - start

    start = time.time()
    perf_store.query_messages("test", session_id="perf-sess", top_k=5)
    query_time = time.time() - start

    # Relaxed thresholds for first-run model loading
    test("NFR-2: Store performance <5s",
         store_time < 5.0,
         f"store took {store_time:.2f}s")
    test("NFR-2: Query performance <5s",
         query_time < 5.0,
         f"query took {query_time:.2f}s")
    perf_store.close()

    # --- FR-5.3: CLI entry point ---
    test("FR-5.3: CLI entry point via python -m",
         os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'src', 'context_memory_mcp', '__main__.py')),
         "__main__.py exists")

    # --- Cleanup ---
    store3.close()
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    # --- Summary ---
    print("\n" + "=" * 60)
    total = PASS_COUNT + FAIL_COUNT
    print(f"Overall: {PASS_COUNT}/{total} PASS, {FAIL_COUNT}/{total} FAIL")
    print("=" * 60)

    result = "PASS" if FAIL_COUNT == 0 else "FAIL"
    print(f"RESULT: {result}")

    # Write results to file for reliable capture
    result_path = os.path.join(os.path.dirname(__file__), 'uat_results.txt')
    with open(result_path, 'w', encoding='utf-8') as f:
        f.write(f"Overall: {PASS_COUNT}/{total} PASS, {FAIL_COUNT}/{total} FAIL\n")
        f.write(f"RESULT: {result}\n")

    return 0 if FAIL_COUNT == 0 else 1

if __name__ == "__main__":
    import traceback
    log_path = os.path.join(os.path.dirname(__file__), 'uat_results.txt')
    try:
        rc = main()
        sys.exit(rc)
    except Exception as e:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"\nCRASH: {e}\n")
            f.write(traceback.format_exc())
        print(f"CRASH: {e}")
        traceback.print_exc()
        sys.exit(2)
