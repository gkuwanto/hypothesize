"""Typed exceptions raised by ``AnthropicBackend``.

The SDK's native exceptions carry response bodies and request metadata
that we do not want leaking into caller logs by default. These wrappers
categorise each SDK failure into one of four semantic buckets so that
callers can react (retry, alert, abort) without pattern-matching on
provider-specific error types.
"""

from __future__ import annotations


class AnthropicBackendError(Exception):
    """Base class for all errors raised by ``AnthropicBackend``."""


class AnthropicAuthError(AnthropicBackendError):
    """401 / invalid API key. Never retried."""


class AnthropicRateLimited(AnthropicBackendError):  # noqa: N818 — spec-named
    """429 after the configured retry budget was exhausted."""


class AnthropicTransientError(AnthropicBackendError):
    """Connection error or 5xx after the configured retry budget was exhausted."""


class AnthropicClientError(AnthropicBackendError):
    """Non-retryable 4xx client error (bad request, not found, etc.)."""
