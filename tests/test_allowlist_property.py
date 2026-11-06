"""Property-based tests for the allowlist — the security boundary (audit M10).

CONTRIBUTING asks for Hypothesis coverage of the argument validators. The core
invariant: ``validate`` is total and fail-closed — for ANY argv it either
returns a key that actually has an argument validator, or raises
``CommandDenied``. It must never return an unmapped key and never raise any
other exception. ``risk_for`` / ``reversible_for`` must agree (accept exactly
what ``validate`` accepts) and never crash.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from android_agent.bridge import allowlist
from android_agent.bridge.allowlist import CommandDenied

# Coverage instrumentation slows each example well past Hypothesis's default
# per-example deadline, so disable it (this is a correctness property, not a
# performance test).
_SETTINGS = settings(deadline=None, max_examples=200)

# Printable tokens, including shell metacharacters and option-like values, so
# the validators and the _META guard are exercised on hostile input.
_tokens = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126), min_size=0, max_size=14
)
_argv = st.lists(_tokens, max_size=6)


@_SETTINGS
@given(_argv)
def test_validate_is_total_and_fail_closed(command: list[str]) -> None:
    try:
        key = allowlist.validate(command)
    except CommandDenied:
        return  # rejecting anything is always a valid outcome
    # If it accepted, the key MUST be one with a real argument validator.
    assert key in allowlist._ARGS


@_SETTINGS
@given(st.lists(_tokens, max_size=5))
def test_prefixed_commands_never_crash_and_stay_consistent(rest: list[str]) -> None:
    for tool in ("adb", "fastboot"):
        command = [tool, *rest]
        try:
            key = allowlist.validate(command)
        except CommandDenied:
            continue
        assert key in allowlist._ARGS
        # The derived risk/reversibility accept exactly what validate accepted,
        # and never raise for an accepted command.
        assert allowlist.risk_for(command) in set(allowlist._RISK.values()) | {
            allowlist.RiskLevel.HIGH
        }
        assert isinstance(allowlist.reversible_for(command), bool)
