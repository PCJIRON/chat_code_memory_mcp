"""Phase 4 Integration Verification Script — Fixed version."""
import sys
import os
import tempfile
import traceback
import subprocess
import json

os.chdir(r"C:\Users\Hp\OneDrive\Desktop\memory")

results = {}
overall = "PASS"

def mark(key, status, details):
    results[key] = {"status": status, "details": details}

# ─── 1. Module Imports ───────────────────────────────────────────────
print("=" * 60)
print("CHECK 1: Module Imports")
print("=" * 60)
try:
    from context_memory_mcp.chat_store import ChatStore, register as register_chat
    print("  ✅ chat_store: ChatStore, register")

    from context_memory_mcp.context import ContextBuilder, get_minimal_context, format_with_detail, register as register_context
    print("  ✅ context: ContextBuilder, get_minimal_context, format_with_detail, register")

    from context_memory_mcp.file_graph import FileGraph, get_graph, register as register_graph
    print("  ✅ file_graph: FileGraph, get_graph, register")

    from context_memory_mcp.parser import ASTParser, ParsedSymbol
    print("  ✅ parser: ASTParser, ParsedSymbol")

    from context_memory_mcp.mcp_server import register_all
    print("  ✅ mcp_server: register_all")

    from context_memory_mcp.embeddings import EmbeddingModel
    print("  ✅ embeddings: EmbeddingModel")

    mark("imports", "PASS", "All 6 modules imported successfully with expected symbols")
except Exception as e:
    mark("imports", "FAIL", f"Import error: {e}\n{traceback.format_exc()}")
    print(f"  ❌ Import FAILED: {e}")
    traceback.print_exc()

# ─── 2. register_all() ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("CHECK 2: register_all()")
print("=" * 60)
try:
    from context_memory_mcp.mcp_server import register_all
    register_all()
    print("  ✅ register_all() executed without errors")
    mark("register_all", "PASS", "register_all() registered all MCP tools successfully")
except Exception as e:
    mark("register_all", "FAIL", f"register_all() error: {e}\n{traceback.format_exc()}")
    print(f"  ❌ register_all() FAILED: {e}")
    traceback.print_exc()

# ─── 3. Context Pipeline ────────────────────────────────────────────
print("\n" + "=" * 60)
print("CHECK 3: Context Pipeline (compress → format)")
print("=" * 60)
try:
    from context_memory_mcp.context import get_minimal_context, format_with_detail

    messages = [
        {"role": "user", "content": "Hello world, how are you?"},
        {"role": "assistant", "content": "Hi there! I'm doing great. Let me help you with your code."},
        {"role": "user", "content": "Can you explain the file graph module?"},
        {"role": "assistant", "content": "The file graph module tracks file dependencies using NetworkX..."},
    ]

    window = get_minimal_context(messages)
    print(f"  ✅ get_minimal_context: {window.token_count} tokens, content length={len(window.content)}")

    detail_minimal = format_with_detail({"query": "file graph", "results": messages}, "minimal")
    print(f"  ✅ format_with_detail(minimal): {len(detail_minimal)} chars")

    detail_summary = format_with_detail({"query": "file graph", "results": messages}, "summary")
    print(f"  ✅ format_with_detail(summary): {len(detail_summary)} chars")

    detail_full = format_with_detail({"query": "file graph", "results": messages}, "full")
    print(f"  ✅ format_with_detail(full): {len(detail_full)} chars")

    mark("context_pipeline", "PASS",
         f"Context pipeline: {window.token_count} tokens, content={len(window.content)} chars, "
         f"minimal={len(detail_minimal)} chars, summary={len(detail_summary)} chars, full={len(detail_full)} chars")
except Exception as e:
    mark("context_pipeline", "FAIL", f"Context pipeline error: {e}\n{traceback.format_exc()}")
    print(f"  ❌ Context pipeline FAILED: {e}")
    traceback.print_exc()

# ─── 4. Session Lifecycle ───────────────────────────────────────────
print("\n" + "=" * 60)
print("CHECK 4: Session Lifecycle (store → list → prune → delete)")
print("=" * 60)
try:
    from context_memory_mcp.chat_store import ChatStore

    tmp = tempfile.mkdtemp()
    chroma_path = os.path.join(tmp, "chromadb")
    store = ChatStore(chroma_path=chroma_path)

    # Store messages
    store.store_messages([{"role": "user", "content": "test message 1"}], session_id="session-1")
    store.store_messages([{"role": "user", "content": "test message 2"}], session_id="session-2")
    store.store_messages([{"role": "user", "content": "test message 3"}], session_id="session-3")
    print("  ✅ Stored 3 sessions")

    # List sessions
    sessions = store.list_sessions()
    print(f"  ✅ list_sessions: {len(sessions)} sessions")

    # Check session index at project level
    project_index = os.path.join(r"C:\Users\Hp\OneDrive\Desktop\memory", "data", "session_index.json")
    index_exists = os.path.exists(project_index)
    print(f"  ✅ Project session index exists: {index_exists}")
    if index_exists:
        with open(project_index) as f:
            idx = json.load(f)
        print(f"  ✅ Session index entries: {len(idx.get('sessions', {}))}")

    # Prune sessions
    pruned = store.prune_sessions(max_sessions=2)
    print(f"  ✅ prune_sessions(max_sessions=2): pruned={pruned.get('pruned', 'N/A')}")

    sessions_after_prune = store.list_sessions()
    print(f"  ✅ list_sessions after prune: {len(sessions_after_prune)} sessions")

    store.close()
    mark("session_lifecycle", "PASS",
         f"Session lifecycle: stored 3, listed {len(sessions)}, pruned={pruned.get('pruned', 'N/A')}, "
         f"remaining={len(sessions_after_prune)}, index exists={index_exists}")
except Exception as e:
    mark("session_lifecycle", "FAIL", f"Session lifecycle error: {e}\n{traceback.format_exc()}")
    print(f"  ❌ Session lifecycle FAILED: {e}")
    traceback.print_exc()

# ─── 5. Graph Pipeline ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("CHECK 5: Graph Pipeline (build → save → load → query → update)")
print("=" * 60)
try:
    from context_memory_mcp.file_graph import FileGraph

    tmp = tempfile.mkdtemp()

    # Create a simple Python file
    test_file = os.path.join(tmp, "test_module.py")
    with open(test_file, "w") as f:
        f.write("import os\nimport sys\n\ndef helper():\n    pass\n\nclass MyClass:\n    def method(self):\n        pass\n")

    # Build graph
    graph = FileGraph(root_path=tmp)
    build_result = graph.build_graph(tmp)
    n_files = build_result.get('files_processed', 0) if isinstance(build_result, dict) else 1
    print(f"  ✅ build_graph: {n_files} files processed")

    # Save graph
    graph_path = os.path.join(tmp, "graph.json")
    graph.save(graph_path)
    print(f"  ✅ save: {graph_path}")

    # Load graph
    graph2 = FileGraph.load(graph_path)
    print(f"  ✅ load: OK, nodes={graph2.graph.number_of_nodes()}, edges={graph2.graph.number_of_edges()}")

    # Query subgraph
    deps = graph.get_dependencies("test_module.py")
    print(f"  ✅ get_dependencies: {len(deps)} dependencies")

    # Incremental update
    with open(test_file, "a") as f:
        f.write("\ndef new_function():\n    pass\n")

    update_result = graph.update_graph(tmp)
    print(f"  ✅ update_graph: OK")

    mark("graph_pipeline", "PASS",
         f"Graph pipeline: build={n_files} files, save/load OK, deps={len(deps)}, update OK")
except Exception as e:
    mark("graph_pipeline", "FAIL", f"Graph pipeline error: {e}\n{traceback.format_exc()}")
    print(f"  ❌ Graph pipeline FAILED: {e}")
    traceback.print_exc()

# ─── 6. Test Suite ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("CHECK 6: Test Suite (pytest)")
print("=" * 60)
try:
    result = subprocess.run(
        ["py", "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
        capture_output=True, text=True, timeout=180,
        cwd=r"C:\Users\Hp\OneDrive\Desktop\memory"
    )
    output = result.stdout
    errors = result.stderr

    lines = output.strip().split("\n")
    summary_lines = [l for l in lines if "passed" in l.lower() or "failed" in l.lower() or "error" in l.lower()]
    last_summary = summary_lines[-1] if summary_lines else "No summary found"

    # Count by test file
    file_counts = {}
    for line in lines:
        if ".py" in line and ("passed" in line.lower() or "pass" in line.lower()):
            parts = line.strip().split()
            for p in parts:
                if p.endswith("]") or (p.replace(" ","").isdigit() and "passed" in line.lower()):
                    pass

    print(f"\n{output[-800:] if len(output) > 800 else output}")
    if errors.strip():
        print(f"\nSTDERR (last 300 chars):\n{errors[-300:]}")

    if result.returncode == 0:
        mark("test_suite", "PASS", f"Test suite: {last_summary}")
    else:
        mark("test_suite", "FAIL", f"Test suite returned non-zero exit code: {result.returncode}\n{last_summary}")
except subprocess.TimeoutExpired:
    mark("test_suite", "FAIL", "Test suite timed out after 180s")
    print("  ❌ Test suite TIMED OUT")
except Exception as e:
    mark("test_suite", "FAIL", f"Test suite error: {e}")
    print(f"  ❌ Test suite FAILED: {e}")

# ─── Summary ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("INTEGRATION VERIFICATION SUMMARY")
print("=" * 60)

for key, val in results.items():
    icon = "✅" if val["status"] == "PASS" else "❌" if val["status"] == "FAIL" else "⏭️"
    print(f"  {icon} {key}: {val['status']}")
    if val["details"]:
        detail_preview = val["details"][:120]
        print(f"     {detail_preview}")

failures = [k for k, v in results.items() if v["status"] == "FAIL"]
if failures:
    overall = "FAIL"
    print(f"\n❌ OVERALL: FAIL — {len(failures)} check(s) failed: {', '.join(failures)}")
else:
    skips = [k for k, v in results.items() if v["status"] == "SKIP"]
    if skips:
        overall = "PASS_WITH_NOTES"
        print(f"\n⚠️  OVERALL: PASS_WITH_NOTES — {len(skips)} check(s) skipped")
    else:
        overall = "PASS"
        print(f"\n✅ OVERALL: PASS — All checks passed")

# Save results
with open(r"C:\Users\Hp\OneDrive\Desktop\memory\scripts\verify_phase4_results.json", "w") as f:
    json.dump({"overall": overall, "results": results}, f, indent=2)

print(f"\nResults saved to scripts/verify_phase4_results.json")
print(f"\nOVERALL: {overall}")
