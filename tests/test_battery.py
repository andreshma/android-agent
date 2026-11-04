"""Battery drain ranking powers the optimize report, so test the parsers."""

from android_agent.capabilities import battery

BATTERYSTATS = """\
Estimated power use (mAh):
  Capacity: 4000, Computed drain: 980, actual drain: 900-1000
  Uid u0a208: 120 ( cpu=90 wifi=30 )
  Uid 1000: 40.5 ( cpu=40 )
  Uid u0a45: 300 ( cpu=200 screen=100 )
"""

LIST_U = """\
package:com.heavy.app uid:10208
package:com.android.systemui uid:10045
package:com.other uid:10999
"""


def test_uid_token_to_int():
    assert battery.uid_token_to_int("u0a208") == 10208
    assert battery.uid_token_to_int("u0a45") == 10045
    assert battery.uid_token_to_int("1000") == 1000
    assert battery.uid_token_to_int("garbage") is None


def test_parse_power_use_sorted_desc():
    rows = battery.parse_power_use(BATTERYSTATS)
    assert rows[0] == ("u0a45", 300.0)
    assert rows[1] == ("u0a208", 120.0)
    assert rows[2] == ("1000", 40.5)


def test_parse_uid_map():
    m = battery.parse_uid_map(LIST_U)
    assert m[10208] == "com.heavy.app"
    assert m[10045] == "com.android.systemui"


def test_top_power_consumers_joins_names():
    uidmap = battery.parse_uid_map(LIST_U)
    top = battery.top_power_consumers(BATTERYSTATS, uidmap, limit=3)
    # Highest drain first; mapped names resolved, unmapped keep their token.
    assert top[0] == {"package": "com.android.systemui", "mah": 300.0}
    assert top[1] == {"package": "com.heavy.app", "mah": 120.0}
    assert top[2] == {"package": "1000", "mah": 40.5}  # uid 1000 not in map


def test_top_power_consumers_limit():
    assert len(battery.top_power_consumers(BATTERYSTATS, {}, limit=1)) == 1
