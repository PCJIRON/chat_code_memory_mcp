"""Verify Phase 1 imports and dependencies."""
import sys

results = []

# Module imports
modules = [
    'context_memory_mcp.chat_store',
    'context_memory_mcp.file_graph',
    'context_memory_mcp.parser',
    'context_memory_mcp.embeddings',
    'context_memory_mcp.context',
]
for m in modules:
    try:
        __import__(m)
        results.append(f"OK: {m}")
    except Exception as e:
        results.append(f"FAIL: {m} - {e}")

results.append("---")

# Dependencies
deps = [('mcp', 'mcp'), ('chromadb', 'chromadb'), ('sentence_transformers', 'sentence-transformers'), ('networkx', 'networkx')]
for import_name, display_name in deps:
    try:
        mod = __import__(import_name)
        v = getattr(mod, '__version__', 'unknown')
        results.append(f"DEP OK: {display_name} ({v})")
    except Exception as e:
        results.append(f"DEP FAIL: {display_name} - {e}")

# Verify ping tool exists
try:
    from context_memory_mcp.mcp_server import mcp, register_all
    register_all()
    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    results.append(f"TOOLS: {tool_names}")
    has_ping = "ping" in tool_names
    results.append(f"PING TOOL: {'OK' if has_ping else 'MISSING'}")
except Exception as e:
    results.append(f"TOOLS FAIL: {e}")

# Verify pyproject.toml
import os
pyproject = os.path.join(os.path.dirname(__file__), '..', 'pyproject.toml')
if os.path.exists(pyproject):
    with open(pyproject) as f:
        content = f.read()
    has_name = 'context-memory-mcp' in content
    has_version = 'version = "0.1.0"' in content
    results.append(f"PYPROJECT: name={'OK' if has_name else 'MISS'}, ver={'OK' if has_version else 'MISS'}")
else:
    results.append("PYPROJECT: MISSING")

# Verify __version__
try:
    from context_memory_mcp import __version__
    results.append(f"VERSION: {__version__}")
except Exception as e:
    results.append(f"VERSION FAIL: {e}")

out_path = os.path.join(os.path.dirname(__file__), 'uat_phase1_results.txt')
with open(out_path, 'w') as f:
    f.write('\n'.join(results))
    f.write('\n')

for r in results:
    print(r)
