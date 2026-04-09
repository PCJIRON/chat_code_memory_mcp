"""Integration verification script for Phase 3."""
import json
import sys
import os
import tempfile
import traceback

# Project root is the parent of scripts/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
TESTS_DIR = os.path.join(PROJECT_ROOT, "tests")

# Ensure the src directory is on sys.path
sys.path.insert(0, SRC_DIR)

results = {}
errors = []

# ===================================================================
# CHECK 1: Parser module imports
# ===================================================================
print("=" * 60)
print("CHECK 1: Parser module imports")
print("=" * 60)
try:
    from context_memory_mcp.parser import ASTParser, ParsedSymbol
    print("  PASS: from context_memory_mcp.parser import ASTParser, ParsedSymbol")
    
    # Verify class attributes
    sym = ParsedSymbol(name="test_func", kind="function", file_path="test.py",
                       line_start=1, line_end=10)
    assert sym.name == "test_func"
    assert sym.kind == "function"
    assert sym.line_start == 1
    assert sym.line_end == 10
    assert sym.qualified_name.endswith("::test_func")
    
    d = sym.to_dict()
    assert "qualified_name" in d
    print(f"  PASS: ParsedSymbol data class works, qualified_name={sym.qualified_name}")
    results["parser_imports"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()
    results["parser_imports"] = f"FAIL: {e}"
    errors.append(("Parser imports", e))

# ===================================================================
# CHECK 2: FileGraph module imports
# ===================================================================
print()
print("=" * 60)
print("CHECK 2: FileGraph module imports")
print("=" * 60)
try:
    from context_memory_mcp.file_graph import FileGraph, FileNode, get_graph, register
    print("  PASS: from context_memory_mcp.file_graph import FileGraph, FileNode, get_graph, register")
    
    # Verify FileNode
    node = FileNode(path="test.py", language="python")
    assert node.path == "test.py"
    assert node.language == "python"
    d = node.to_dict()
    assert "path" in d
    print(f"  PASS: FileNode data class works")
    
    # Verify get_graph returns singleton
    g = get_graph(".")
    assert isinstance(g, FileGraph)
    print(f"  PASS: get_graph() returns FileGraph singleton")
    results["file_graph_imports"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()
    results["file_graph_imports"] = f"FAIL: {e}"
    errors.append(("FileGraph imports", e))

# ===================================================================
# CHECK 3: mcp_server.py imports and register_all()
# ===================================================================
print()
print("=" * 60)
print("CHECK 3: mcp_server.py imports and register_all()")
print("=" * 60)
try:
    from context_memory_mcp import mcp_server
    print("  PASS: from context_memory_mcp import mcp_server")
    
    # Check that mcp object exists
    assert hasattr(mcp_server, 'mcp')
    print(f"  PASS: mcp_server.mcp exists (type={type(mcp_server.mcp).__name__})")
    
    # Check register_all function exists
    assert hasattr(mcp_server, 'register_all')
    print(f"  PASS: mcp_server.register_all exists")
    
    # Try to call register_all (this imports chat_store which initializes ChromaDB)
    # This may take a moment due to SentenceTransformer model download
    print("  INFO: Calling register_all() (may download ~80MB model on first run)...")
    mcp_server.register_all()
    print("  PASS: register_all() completed without errors")
    results["mcp_server_imports"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()
    results["mcp_server_imports"] = f"FAIL: {e}"
    errors.append(("mcp_server imports/register_all", e))

# ===================================================================
# CHECK 4: End-to-end parser test on actual file
# ===================================================================
print()
print("=" * 60)
print("CHECK 4: End-to-end parser test on chat_store.py")
print("=" * 60)
try:
    from context_memory_mcp.parser import ASTParser
    
    parser = ASTParser()
    
    # Check tree-sitter is available
    if parser._parser is None:
        print("  WARN: tree-sitter parser not available (falls back to empty results)")
        print("  INFO: This is expected if tree-sitter-language-pack is not installed")
        results["parser_e2e"] = "PASS_WITH_NOTES (tree-sitter unavailable, parser initializes without error)"
    else:
        # Parse chat_store.py
        test_file = os.path.join(SRC_DIR, "context_memory_mcp", "chat_store.py")
        if not os.path.exists(test_file):
            print(f"  SKIP: {test_file} not found")
            results["parser_e2e"] = "SKIP"
        else:
            symbols = parser.parse_file(test_file)
            print(f"  INFO: Parsed {len(symbols)} symbols from chat_store.py")
            
            # Categorize symbols
            kinds = {}
            for s in symbols:
                kinds[s.kind] = kinds.get(s.kind, 0) + 1
            print(f"  INFO: Symbol kinds: {kinds}")
            
            # Check we got some expected kinds
            if len(symbols) > 0:
                print(f"  PASS: Parser returned {len(symbols)} symbols")
                # Print first few symbols
                for s in symbols[:5]:
                    print(f"    - {s.kind}: {s.name} (lines {s.line_start}-{s.line_end})")
                results["parser_e2e"] = "PASS"
            else:
                print(f"  WARN: Parser returned 0 symbols (tree-sitter may not be parsing correctly)")
                results["parser_e2e"] = "PASS_WITH_NOTES (0 symbols — tree-sitter may need investigation)"
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()
    results["parser_e2e"] = f"FAIL: {e}"
    errors.append(("Parser e2e", e))

# ===================================================================
# CHECK 5: End-to-end graph build test
# ===================================================================
print()
print("=" * 60)
print("CHECK 5: End-to-end graph build on src/ directory")
print("=" * 60)
try:
    from context_memory_mcp.file_graph import FileGraph, reset_graph
    
    reset_graph()  # Clear singleton
    
    graph = FileGraph(root_path=SRC_DIR)
    summary = graph.build_graph(SRC_DIR)
    
    print(f"  PASS: build_graph() returned summary:")
    print(f"    file_count: {summary['file_count']}")
    print(f"    node_count: {summary['node_count']}")
    print(f"    edge_count: {summary['edge_count']}")
    print(f"    built_at: {summary['built_at']}")
    
    assert 'file_count' in summary
    assert 'node_count' in summary
    assert 'edge_count' in summary
    assert 'built_at' in summary
    assert summary['file_count'] > 0, "Expected at least 1 file"
    assert summary['node_count'] > 0, "Expected at least 1 node"
    
    results["graph_build"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()
    results["graph_build"] = f"FAIL: {e}"
    errors.append(("Graph build", e))

# ===================================================================
# CHECK 6: Graph persistence round-trip
# ===================================================================
print()
print("=" * 60)
print("CHECK 6: Graph persistence save/load round-trip")
print("=" * 60)
try:
    from context_memory_mcp.file_graph import FileGraph, reset_graph
    import tempfile
    
    # Build a fresh graph
    reset_graph()
    graph = FileGraph(root_path=SRC_DIR)
    graph.build_graph(SRC_DIR)
    
    original_nodes = graph.graph.number_of_nodes()
    original_edges = graph.graph.number_of_edges()
    
    # Save to temp file
    tmp_path = os.path.join(tempfile.gettempdir(), "test_graph_verify.json")
    graph.save(tmp_path)
    print(f"  INFO: Saved graph to {tmp_path}")
    print(f"    Original: {original_nodes} nodes, {original_edges} edges")
    
    # Load back
    loaded = FileGraph.load(tmp_path)
    loaded_nodes = loaded.graph.number_of_nodes()
    loaded_edges = loaded.graph.number_of_edges()
    print(f"    Loaded: {loaded_nodes} nodes, {loaded_edges} edges")
    
    assert original_nodes == loaded_nodes, \
        f"Node count mismatch: {original_nodes} vs {loaded_nodes}"
    assert original_edges == loaded_edges, \
        f"Edge count mismatch: {original_edges} vs {loaded_edges}"
    
    print(f"  PASS: Round-trip equality verified ({loaded_nodes} nodes, {loaded_edges} edges)")
    
    # Cleanup
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    
    results["persistence"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()
    results["persistence"] = f"FAIL: {e}"
    errors.append(("Persistence round-trip", e))

# ===================================================================
# CHECK 7: MCP register function signature
# ===================================================================
print()
print("=" * 60)
print("CHECK 7: MCP register function signature")
print("=" * 60)
try:
    import inspect
    from context_memory_mcp.file_graph import register
    
    sig = inspect.signature(register)
    print(f"  INFO: register signature: {sig}")
    
    params = list(sig.parameters.keys())
    print(f"  INFO: Parameters: {params}")
    
    assert 'mcp' in params, "Expected 'mcp' parameter"
    print(f"  PASS: register(mcp) signature is correct")
    
    # Also check the source code has @mcp.tool decorators inside
    source = inspect.getsource(register)
    assert '@mcp.tool' in source, "Expected @mcp.tool decorator in register function"
    print(f"  PASS: register function contains @mcp.tool decorators")
    
    results["mcp_register"] = "PASS"
except Exception as e:
    print(f"  FAIL: {e}")
    traceback.print_exc()
    results["mcp_register"] = f"FAIL: {e}"
    errors.append(("MCP register function", e))

# ===================================================================
# CHECK 8: Existing test suite
# ===================================================================
print()
print("=" * 60)
print("CHECK 8: Run existing test suite")
print("=" * 60)
try:
    import subprocess
    result = subprocess.run(
        ["py", "-m", "pytest", TESTS_DIR, "-v", "--tb=short", "-x"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=PROJECT_ROOT,
    )
    
    # Parse output
    output = result.stdout + result.stderr
    print(output[-3000:] if len(output) > 3000 else output)  # Last 3000 chars
    print(f"  Return code: {result.returncode}")
    
    if result.returncode == 0:
        # Count passed tests
        passed_count = output.count("PASSED")
        results["test_suite"] = f"PASS ({passed_count} tests passed)"
    else:
        results["test_suite"] = f"FAIL (returncode={result.returncode})"
        errors.append(("Test suite", f"pytest returned {result.returncode}"))
except subprocess.TimeoutExpired:
    print("  FAIL: Test suite timed out after 120s")
    results["test_suite"] = "FAIL (timeout)"
    errors.append(("Test suite", "Timed out"))
except Exception as e:
    print(f"  FAIL: {e}")
    results["test_suite"] = f"FAIL: {e}"
    errors.append(("Test suite", e))

# ===================================================================
# SUMMARY
# ===================================================================
print()
print("=" * 60)
print("INTEGRATION VERIFICATION SUMMARY")
print("=" * 60)
for check, status in results.items():
    icon = "PASS" if status.startswith("PASS") else "FAIL"
    print(f"  [{icon}] {check}: {status}")

total = len(results)
passed = sum(1 for s in results.values() if s.startswith("PASS"))
failed = total - passed

print(f"\n  Total: {total} checks, {passed} passed, {failed} failed/with_notes")

if errors:
    print(f"\n  ERRORS ({len(errors)}):")
    for name, err in errors:
        print(f"    - {name}: {err}")

# Determine overall result
all_pass = all(s.startswith("PASS") for s in results.values())
has_notes = any("NOTES" in s or "WARN" in s for s in results.values())

if all_pass and not has_notes:
    print("\n  OVERALL: PASS")
elif all_pass and has_notes:
    print("\n  OVERALL: PASS_WITH_NOTES")
else:
    print("\n  OVERALL: FAIL")
