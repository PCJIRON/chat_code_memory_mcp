"""Test script to verify MCP ping tool over stdio (JSON-RPC).

Spawns the server as a subprocess, performs MCP initialization handshake,
then sends a tools/call request for 'ping' over stdin, reads the response
from stdout, and validates it.

Usage: python scripts/test_ping_stdio.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

# MCP initialization handshake (required before any tool calls)
INIT_REQUEST = {
    "jsonrpc": "2.0",
    "id": 0,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "0.1.0"},
    },
}

# JSON-RPC 2.0 request to call the 'ping' tool
PING_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "ping",
        "arguments": {},
    },
}


def _read_response(proc: subprocess.Popen) -> dict:
    """Read a single JSON-RPC response line from stdout."""
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError(f"No response from server. stderr: {proc.stderr.read()[:500] if proc.stderr else 'N/A'}")
    return json.loads(line)


def test_stdio_ping() -> bool:
    """Test that the MCP server responds to ping over stdio.

    Returns:
        True if ping returns expected response, False otherwise.
    """
    # Start server subprocess with stdio pipes
    proc = subprocess.Popen(
        [sys.executable, "-m", "context_memory_mcp", "start"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdin is not None

        # Step 1: Send initialization request
        proc.stdin.write(json.dumps(INIT_REQUEST) + "\n")
        proc.stdin.flush()
        time.sleep(0.5)

        # Step 2: Read initialization response
        init_response = _read_response(proc)
        if "error" in init_response:
            print(f"⚠️  Init response had error: {init_response['error']}")
            # Some servers still work despite init errors

        # Step 3: Send initialized notification (required by MCP spec)
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        proc.stdin.write(json.dumps(initialized_notification) + "\n")
        proc.stdin.flush()
        time.sleep(0.5)

        # Step 4: Send tools/call request for ping
        proc.stdin.write(json.dumps(PING_REQUEST) + "\n")
        proc.stdin.flush()
        time.sleep(1)

        # Step 5: Read ping response
        response = _read_response(proc)

        # Validate response structure
        if "error" in response:
            print(f"❌ Ping test FAILED: {response['error']}")
            return False

        assert response.get("id") == 1, f"Unexpected id: {response.get('id')}"
        assert "result" in response, f"No result in response: {response}"

        # Parse the ping result (FastMCP returns content as array of text blocks)
        result = response["result"]
        content = result.get("content", [])
        assert len(content) > 0, f"Empty content in response: {result}"

        # Content should be a text block with JSON string
        text_block = content[0]
        assert text_block.get("type") == "text", f"Unexpected content type: {text_block}"

        ping_data = json.loads(text_block["text"])
        assert ping_data.get("status") == "ok", f"Unexpected status: {ping_data.get('status')}"
        assert "version" in ping_data, f"No version in response: {ping_data}"
        assert ping_data.get("storage") == "chromadb-ready", f"Unexpected storage: {ping_data.get('storage')}"

        print("✅ Ping test PASSED — stdio JSON-RPC communication works!")
        print(f"   Response: {ping_data}")
        return True

    except (subprocess.TimeoutExpired, json.JSONDecodeError, AssertionError, KeyError, RuntimeError) as e:
        print(f"❌ Ping test FAILED: {e}")
        return False
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    success = test_stdio_ping()
    sys.exit(0 if success else 1)
