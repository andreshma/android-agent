"""Sensitive-permission analysis for the audit mission.

Pure parsing of ``adb shell dumpsys package <pkg>`` output, so it is fully
unit-testable without a device. We surface which apps hold *granted* permissions
that touch privacy-sensitive hardware or data (microphone, camera, location,
contacts, SMS, call log, etc.), which is the core of a human-readable "what can
spy on me?" audit.
"""

from __future__ import annotations

import re

# android.permission.X  ->  short human label shown to the operator.
SENSITIVE_PERMISSIONS: dict[str, str] = {
    "android.permission.RECORD_AUDIO": "microphone",
    "android.permission.CAMERA": "camera",
    "android.permission.ACCESS_FINE_LOCATION": "precise location",
    "android.permission.ACCESS_COARSE_LOCATION": "approximate location",
    "android.permission.ACCESS_BACKGROUND_LOCATION": "location in background",
    "android.permission.READ_CONTACTS": "contacts",
    "android.permission.READ_SMS": "SMS messages",
    "android.permission.RECEIVE_SMS": "incoming SMS",
    "android.permission.READ_CALL_LOG": "call log",
    "android.permission.READ_PHONE_STATE": "phone state",
    "android.permission.READ_CALENDAR": "calendar",
    "android.permission.BODY_SENSORS": "body sensors",
    "android.permission.READ_EXTERNAL_STORAGE": "device storage",
    "android.permission.READ_MEDIA_IMAGES": "photos",
    "android.permission.READ_MEDIA_AUDIO": "audio files",
    "android.permission.READ_MEDIA_VIDEO": "videos",
}

# Matches lines like:
#   android.permission.CAMERA: granted=true
#   android.permission.CAMERA: granted=true, flags=[ ... ]
_GRANT_RE = re.compile(r"(?P<perm>android\.permission\.[A-Z_]+):\s*granted=(?P<granted>true|false)")


def parse_package_list(stdout: str) -> list[str]:
    """Parse ``pm list packages`` output (lines like ``package:com.x``)."""
    packages: list[str] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if line.startswith("package:"):
            packages.append(line.split(":", 1)[1].strip())
    return packages


def parse_granted_permissions(dumpsys_text: str) -> set[str]:
    """Return the set of permissions reported as ``granted=true``."""
    granted: set[str] = set()
    for m in _GRANT_RE.finditer(dumpsys_text):
        if m.group("granted") == "true":
            granted.add(m.group("perm"))
    return granted


def sensitive_grants(dumpsys_text: str) -> list[str]:
    """Human labels for the granted, privacy-sensitive permissions of one app.

    Sorted and de-duplicated so the report is stable.
    """
    granted = parse_granted_permissions(dumpsys_text)
    labels = {SENSITIVE_PERMISSIONS[p] for p in granted if p in SENSITIVE_PERMISSIONS}
    return sorted(labels)
