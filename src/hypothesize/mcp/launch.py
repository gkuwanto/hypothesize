"""Launcher for the hypothesize MCP server.

Claude Desktop spawns this module instead of ``hypothesize.mcp.server``
directly. The launcher loads ``~/.config/hypothesize/.env`` (and any
project ``.env`` discovered by walking up from cwd) before importing
the server so the Anthropic SDK picks up the key at startup.

The server module itself stays import-clean and free of I/O — it sees
``ANTHROPIC_API_KEY`` already set in ``os.environ`` by the time its
tools run.
"""

from __future__ import annotations


def main() -> None:
    """Load API-key dotenvs and start the FastMCP server."""
    from hypothesize.setup.env import load_dotenv_chain

    load_dotenv_chain()

    # Lazy import so the dotenv chain runs before tools.py imports the
    # Anthropic SDK indirectly via load on first tool call.
    from hypothesize.mcp.server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
