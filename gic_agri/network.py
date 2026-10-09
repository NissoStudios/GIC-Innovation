"""Minimal stdlib-only HTTP client for the optional online features.

The desktop application works fully offline for parcels, campaigns, tasks,
stocks, finances, plants and observations. Only three features need
Internet access: the agricultural news page, the weather forecast, and the
refresh of the advisory assistant's weather-based rules. This module never
raises raw network exceptions to the rest of the application: every failure
is translated into a :class:`NetworkError` with a short French message that
the interface can show directly to the user.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = (
    "GIC-Innovation-GestionAgricole/1.0 "
    "(application de gestion agricole hors connexion ; Haute-Sanaga, Cameroun)"
)
DEFAULT_TIMEOUT_SECONDS = 12.0


class NetworkError(RuntimeError):
    """Raised when an optional online request cannot be completed."""


def fetch_bytes(url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> bytes:
    """Fetch raw bytes from *url*, raising :class:`NetworkError` on failure."""

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise NetworkError(
            f"Le serveur a répondu avec une erreur ({exc.code})."
        ) from exc
    except urllib.error.URLError as exc:
        raise NetworkError(
            "Connexion Internet indisponible ou site injoignable."
        ) from exc
    except TimeoutError as exc:
        raise NetworkError("Le serveur n'a pas répondu à temps.") from exc


def fetch_text(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    encoding: str = "utf-8",
) -> str:
    """Fetch *url* and decode it as text."""

    raw = fetch_bytes(url, timeout=timeout)
    return raw.decode(encoding, errors="replace")


def fetch_json(url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Any:
    """Fetch *url* and parse it as JSON."""

    raw = fetch_bytes(url, timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NetworkError(
            "Réponse du serveur illisible (format inattendu)."
        ) from exc
