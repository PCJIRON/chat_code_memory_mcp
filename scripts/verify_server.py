"""Verify the MCP server starts and registers chat tools."""
import subprocess
import sys
import os
import time

# Start the server process
env = os.environ.copy()
env["PYTHONPATH"] = os.path.join(os.path.dirname(__file__), "src")

proc = subprocess.Popen(
    [sys.executable, "-m", "context_memory_mcp"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=os.path.dirname(__file__),
    env=env,
)

# Give it a few seconds to start (model load takes time)
time.sleep(8)

# Check if process is still running (no crash)
if proc.poll() is not None:
    stderr = proc.stderr.read().decode("utf-8", errors="replace")
    print(f"SERVER CRASHED! Exit code: {proc.returncode}")
    print(f"stderr: {stderr[:2000]}")
    sys.exit(1)

print("Server is running (no crash after 8s)")

# Send initialize JSON-RPC request
init_request = b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1.0"}}}\n'
proc.stdin.write(init_request)
proc.stdin.flush()
time.sleep(3)

# Send tools/list request
tools_request = b'{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
proc.stdin.write(tools_request)
proc.stdin.flush()
time.sleep(3)

# Terminate
proc.terminate()
proc.wait(timeout=5)

stdout = proc.stdout.read().decode("utf-8", errors="replace")
stderr = proc.stderr.read().decode("utf-8", errors="replace")

# Check for expected tools in stdout
assert "store_chat" in stdout, f"store_chat not found in tools list. stdout: {stdout[:1000]}"
assert "query_chat" in stdout, f"query_chat not found in tools list. stdout: {stdout[:1000]}"
assert "ping" in stdout, f"ping not found in tools list"

print("All expected tools found: ping, store_chat, query_chat")
print("Server verification PASSED")

# Check data/chromadb exists
assert os.path.exists("./data/chromadb"), "./data/chromadb should exist"
print("./data/chromadb directory exists")
