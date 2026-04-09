"""Test ping tool over stdio JSON-RPC with proper MCP handshake."""
import json
import subprocess
import sys
import os
import time

def send_recv(proc, request):
    """Send a JSON-RPC request and read the response."""
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    start = time.time()
    while time.time() - start < 15:
        line = proc.stdout.readline()
        if line and line.strip():
            try:
                return json.loads(line.strip())
            except json.JSONDecodeError:
                continue
    return None

# Start the server
env = os.environ.copy()
cwd = os.path.join(os.path.dirname(__file__), '..')
proc = subprocess.Popen(
    [sys.executable, "-m", "context_memory_mcp", "start"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd=cwd,
    env=env,
)

try:
    # Step 1: Initialize handshake
    init_req = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "uat-tester", "version": "0.1.0"}
        }
    }
    init_resp = send_recv(proc, init_req)
    print(f"INIT RESPONSE: {json.dumps(init_resp, indent=2)}")

    # Step 2: Send initialized notification (required by MCP spec)
    initialized_notify = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {}
    }
    proc.stdin.write(json.dumps(initialized_notify) + "\n")
    proc.stdin.flush()
    time.sleep(0.5)

    # Step 3: Call ping tool
    ping_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "ping",
            "arguments": {}
        }
    }
    ping_resp = send_recv(proc, ping_req)
    print(f"PING RESPONSE: {json.dumps(ping_resp, indent=2)}")

    # Parse the result
    if ping_resp and "result" in ping_resp:
        content = ping_resp["result"].get("content", [])
        if content:
            ping_data = json.loads(content[0].get("text", "{}"))
            print(f"PING DATA: {ping_data}")
            status_ok = ping_data.get("status") == "ok"
            version_ok = ping_data.get("version") == "0.1.0"
            storage_ok = ping_data.get("storage") == "chromadb-ready"
            all_ok = status_ok and version_ok and storage_ok
            print(f"PING TOOL: {'PASS' if all_ok else 'FAIL'}")
        else:
            print("PING TOOL: FAIL - no content in result")
    else:
        error = ping_resp.get("error", {}) if ping_resp else "no response"
        print(f"PING TOOL: FAIL - {error}")

finally:
    proc.kill()
    proc.wait()
