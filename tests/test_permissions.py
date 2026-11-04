"""Permission parsing drives the flagship audit feature, so it gets real tests."""

from android_agent.capabilities import permissions

# Trimmed but realistic `dumpsys package <pkg>` excerpt.
DUMPSYS = """\
Packages:
  Package [com.example.app] (abc123):
    userId=10234
    requested permissions:
      android.permission.INTERNET
      android.permission.CAMERA
      android.permission.RECORD_AUDIO
      android.permission.ACCESS_FINE_LOCATION
    install permissions:
      android.permission.INTERNET: granted=true
    runtime permissions:
      android.permission.CAMERA: granted=true, flags=[ USER_SENSITIVE_WHEN_GRANTED ]
      android.permission.RECORD_AUDIO: granted=false
      android.permission.ACCESS_FINE_LOCATION: granted=true, flags=[ ... ]
"""


def test_parse_package_list():
    out = "package:com.a\npackage:com.b\n\npackage:com.c\n"
    assert permissions.parse_package_list(out) == ["com.a", "com.b", "com.c"]


def test_parse_granted_only_true():
    granted = permissions.parse_granted_permissions(DUMPSYS)
    assert "android.permission.CAMERA" in granted
    assert "android.permission.ACCESS_FINE_LOCATION" in granted
    assert "android.permission.INTERNET" in granted
    # granted=false must be excluded
    assert "android.permission.RECORD_AUDIO" not in granted


def test_sensitive_grants_labels():
    labels = permissions.sensitive_grants(DUMPSYS)
    # camera + precise location are granted & sensitive; mic was denied;
    # INTERNET is granted but not privacy-sensitive in our set.
    assert labels == ["camera", "precise location"]


def test_sensitive_grants_empty_when_none():
    assert permissions.sensitive_grants("no permissions here") == []
