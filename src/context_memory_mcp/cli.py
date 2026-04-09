"""CLI interface for Context Memory MCP Server.

Provides subcommands: start, stop, status, config.
"""

from __future__ import annotations

import argparse
import sys

from context_memory_mcp import __version__


def _cmd_start(_args: argparse.Namespace) -> int:
    """Start the MCP server on stdio transport."""
    try:
        from context_memory_mcp.mcp_server import run_server
    except ImportError as exc:
        print(f"Error: failed to import MCP server: {exc}", file=sys.stderr)
        return 1
    run_server()
    return 0


def _cmd_stop(_args: argparse.Namespace) -> int:
    """Stop the MCP server (not supported in stdio mode)."""
    print("stop: not supported in stdio mode (server runs in foreground)")
    return 0


def _cmd_status(_args: argparse.Namespace) -> int:
    """Print server version and status."""
    print(f"Context Memory MCP Server v{__version__}")
    print("Status: ready")
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    """Print default configuration."""
    show = getattr(args, "show", False)
    print("Default configuration:")
    print(f"  version:       {__version__}")
    print("  transport:     stdio")
    print("  storage:       chromadb (local)")
    print("  embeddings:    sentence-transformers (local)")
    print("  parser:        tree-sitter (local)")
    if show:
        print("  chromadb_path: ./data/chromadb")
        print("  graph_path:    ./data/file_graph.json")
        print("  max_context_tokens: 4000")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 = success).
    """
    parser = argparse.ArgumentParser(
        prog="context-memory-mcp",
        description="MCP server for persistent chat memory and file relationship tracking",
    )
    subparsers = parser.add_subparsers(dest="command")

    # start
    subparsers.add_parser("start", help="Start the MCP server on stdio")

    # stop
    subparsers.add_parser("stop", help="Stop the MCP server")

    # status
    subparsers.add_parser("status", help="Print server version and status")

    # config
    config_parser = subparsers.add_parser("config", help="Print default configuration")
    config_parser.add_argument(
        "--show", action="store_true", help="Show full configuration details"
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    dispatch = {
        "start": _cmd_start,
        "stop": _cmd_stop,
        "status": _cmd_status,
        "config": _cmd_config,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)
