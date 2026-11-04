"""Battery drain analysis for the optimize mission.

Pure parsing of ``dumpsys batterystats`` (estimated power use) joined with a
uid->package map from ``cmd package list packages -U``, so the "which apps drain
my battery?" ranking is unit-testable without a device.

This is read-only reporting: it names the top power consumers so the operator
(or the LLM) can decide what to disable. It never acts on its own.
"""

from __future__ import annotations

import re

# "Uid u0a208: 123" or "Uid 1000: 45.6 ( cpu=... )"
_POWER_RE = re.compile(r"Uid\s+(?P<uid>u\d+a\d+|\d+):\s*(?P<mah>\d+(?:\.\d+)?)")
# "package:com.foo uid:10208"
_UIDMAP_RE = re.compile(r"package:(?P<pkg>\S+)\s+uid:(?P<uid>\d+)")

# Android user/app id layout.
_PER_USER_RANGE = 100_000
_APP_ID_BASE = 10_000


def uid_token_to_int(token: str) -> int | None:
    """Convert a batterystats uid token to a numeric uid.

    ``u0a208`` -> 10208 (user 0, app id 208); a plain ``1000`` -> 1000.
    """
    if token.isdigit():
        return int(token)
    m = re.fullmatch(r"u(\d+)a(\d+)", token)
    if not m:
        return None
    user, app = int(m.group(1)), int(m.group(2))
    return user * _PER_USER_RANGE + _APP_ID_BASE + app


def parse_power_use(batterystats_text: str) -> list[tuple[str, float]]:
    """Return ``[(uid_token, mAh), ...]`` as found, highest drain first."""
    rows = [(m.group("uid"), float(m.group("mah"))) for m in _POWER_RE.finditer(batterystats_text)]
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def parse_uid_map(list_packages_u_text: str) -> dict[int, str]:
    """Parse ``cmd package list packages -U`` into ``{uid: package}``."""
    return {int(m.group("uid")): m.group("pkg") for m in _UIDMAP_RE.finditer(list_packages_u_text)}


def top_power_consumers(
    batterystats_text: str,
    uid_map: dict[int, str],
    limit: int = 10,
) -> list[dict]:
    """Join power use with package names and return the top ``limit`` drainers.

    Each item: ``{"package": <name or uid token>, "mah": <float>}``. Unmapped
    uids (system aggregates) keep their token so nothing is silently dropped.
    """
    out: list[dict] = []
    for token, mah in parse_power_use(batterystats_text)[:limit]:
        uid = uid_token_to_int(token)
        name = uid_map.get(uid) if uid is not None else None
        out.append({"package": name or token, "mah": mah})
    return out
