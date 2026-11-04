"""Bloatware detection drives the debloat plan, so test the heuristics."""

from android_agent.capabilities import bloatware


def test_detects_known_patterns():
    pkgs = [
        "com.facebook.appmanager",
        "com.samsung.android.bixby.agent",
        "com.miui.weather2",
        "com.example.myapp",  # not bloatware
    ]
    found = bloatware.detect_bloatware(pkgs)
    assert "com.facebook.appmanager" in found
    assert "com.samsung.android.bixby.agent" in found
    assert "com.miui.weather2" in found
    assert "com.example.myapp" not in found


def test_protected_packages_never_flagged():
    # Even if a pattern-like string appears, core packages are protected.
    pkgs = ["com.android.vending", "com.google.android.gms", "com.android.settings"]
    assert bloatware.detect_bloatware(pkgs) == {}


def test_is_protected():
    assert bloatware.is_protected("com.android.systemui")
    assert bloatware.is_protected("com.android.vending")
    assert not bloatware.is_protected("com.facebook.katana")


def test_empty_input():
    assert bloatware.detect_bloatware([]) == {}
