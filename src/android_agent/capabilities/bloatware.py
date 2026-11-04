"""Heuristics for the optimize mission: spotting likely bloatware.

Pure, data-driven matching over installed package names, so it is unit-testable
without a device. These are *suggestions* — the operator always confirms before
anything is disabled, and disabling is reversible (``pm enable``). We never
uninstall.

The patterns are intentionally conservative and generic (well-known
preinstalled apps and manufacturer/carrier bundles). They are substrings matched
against the package id; extend the table with a clear label when adding one.
"""

from __future__ import annotations

# (substring in package id) -> human reason shown to the operator.
BLOATWARE_PATTERNS: dict[str, str] = {
    # Commonly preinstalled third-party apps
    "com.facebook.appmanager": "Facebook App Manager (preinstalled, often unused)",
    "com.facebook.services": "Facebook background services (preinstalled)",
    "com.facebook.system": "Facebook system stub (preinstalled)",
    "com.facebook.katana": "Facebook app (preinstalled)",
    "com.netflix.partner": "Netflix preinstall stub",
    "com.amazon.appmanager": "Amazon app manager (preinstalled)",
    "com.linkedin.android": "LinkedIn (preinstalled)",
    # Google apps people frequently debloat
    "com.google.android.apps.tachyon": "Google Meet/Duo",
    "com.google.android.googlequicksearchbox": "Google app / Assistant",
    # Manufacturer bundles
    "com.samsung.android.bixby": "Samsung Bixby",
    "com.samsung.android.app.spage": "Samsung Free / news page",
    "com.miui.": "Xiaomi MIUI bundled app",
    "com.mi.": "Xiaomi bundled app",
    "com.heytap.": "OPPO/realme (HeyTap) bundled app",
    "com.coloros.": "OPPO ColorOS bundled app",
    "com.oppo.": "OPPO bundled app",
    "com.vivo.": "vivo bundled app",
    "com.huawei.": "Huawei bundled app",
    "com.oneplus.": "OnePlus bundled app",
    # Carrier bundles
    "com.verizon.": "Verizon carrier app",
    "com.att.": "AT&T carrier app",
    "com.tmobile.": "T-Mobile carrier app",
}

# Never suggest disabling these, even if a pattern would match — they are load-
# bearing and disabling them can soft-brick or lock the user out.
PROTECTED_PREFIXES: tuple[str, ...] = (
    "com.android.",
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.google.android.packageinstaller",
    "com.android.vending",  # Play Store
)


def is_protected(package: str) -> bool:
    return package.startswith(PROTECTED_PREFIXES)


def detect_bloatware(packages: list[str]) -> dict[str, str]:
    """Return ``{package: reason}`` for installed packages that look like
    bloatware and are not on the protected list."""
    found: dict[str, str] = {}
    for pkg in packages:
        if is_protected(pkg):
            continue
        for pattern, reason in BLOATWARE_PATTERNS.items():
            if pattern in pkg:
                found[pkg] = reason
                break
    return found
