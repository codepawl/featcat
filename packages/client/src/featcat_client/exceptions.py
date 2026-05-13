"""Exceptions raised by the featcat client.

Hierarchy (inherits from a single ``FeatCatError`` base so callers can catch
one type for any client-side failure):

- ``FeatCatError`` — base
  - ``ConnectionError`` — couldn't reach the server (network / DNS / refused)
  - ``ServerError`` — non-2xx response that isn't a known not-found
  - ``FeatureNotFound`` — 404 on a feature lookup
  - ``GroupNotFound`` — 404 on a group lookup
"""

from __future__ import annotations


class FeatCatError(Exception):
    """Base exception for the featcat client."""


class ConnectionError(FeatCatError):  # noqa: A001 — intentional shadow of builtin; module-scoped
    """Raised when the server is unreachable after retries."""


class ServerError(FeatCatError):
    """Raised on a non-2xx response that doesn't map to a more specific error.

    Carries ``status_code`` and the server's response body (if JSON-decodable).
    """

    def __init__(self, message: str, status_code: int, body: object = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class FeatureNotFound(FeatCatError):  # noqa: N818 — naming reads better at callsite than FeatureNotFoundError
    """Raised on a 404 from a feature lookup. Carries the missing name."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Feature not found: {name}")
        self.name = name


class GroupNotFound(FeatCatError):  # noqa: N818 — naming reads better at callsite than GroupNotFoundError
    """Raised on a 404 from a group lookup. Carries the missing name."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Group not found: {name}")
        self.name = name
