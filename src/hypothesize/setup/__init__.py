"""Interactive ``hypothesize setup`` wizard and supporting helpers.

The setup command is split into focused submodules:

- :mod:`detect` — detect Claude Code and Claude Desktop on this machine.
- :mod:`env` — write the API key to a ``.env`` file under a config dir.
- :mod:`install_skill` — copy bundled skill assets into the user's
  Claude Code skill directory.
- :mod:`install_mcp` — atomically merge the hypothesize entry into the
  user's Claude Desktop ``mcpServers`` config.
- :mod:`wizard` — orchestrates the interactive flow and the
  non-interactive flag-driven flow.

Nothing in this package makes LLM calls at import time. The optional
verification step in :mod:`wizard` is the only path that talks to an
LLM, and only when explicitly opted in.
"""
