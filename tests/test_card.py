"""The card: windows per German day for the websocket command, and the
names the card repeats from the Python side.

The card finds its entities by translation key and names the repair
issues; a renamed key would leave it wrong without an error.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from custom_components.einspeisewacht.cards import card_days
from custom_components.einspeisewacht.runtime import ISSUES

ROOT = Path(__file__).parent.parent / "custom_components" / "einspeisewacht"
CARD = (ROOT / "frontend" / "einspeisewacht-card.js").read_text(encoding="utf-8")
STRINGS = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def runtime(prices: dict[datetime, float]) -> SimpleNamespace:
    rule = SimpleNamespace(is_paid=lambda slot, price: False)
    return SimpleNamespace(
        engine=SimpleNamespace(prices=SimpleNamespace(prices=prices), rule=rule)
    )


def test_days_are_german_days() -> None:
    """25 October 2026 ends summer time: the day has 100 quarter hours, and
    a window over midnight shows on both days."""
    prices = {
        utc(2026, 10, 24, 22, 0): 0.05,  # 00:00 on the 25th (CEST)
        utc(2026, 10, 25, 10, 0): -0.01,
        utc(2026, 10, 25, 10, 15): -0.02,
        utc(2026, 10, 25, 12, 0): 0.0,  # exactly 0 is not negative
        utc(2026, 10, 25, 22, 45): -0.01,  # 23:45 (CET)
        utc(2026, 10, 25, 23, 0): -0.01,  # 00:00 on the 26th
    }
    today, tomorrow = card_days(runtime(prices), utc(2026, 10, 25, 6, 0))
    assert today["day"] == "2026-10-25"
    assert tomorrow["day"] == "2026-10-26"
    assert today["known"] and tomorrow["known"]
    assert [(w["start"], w["end"]) for w in today["windows"]] == [
        ("2026-10-25T10:00:00+00:00", "2026-10-25T10:30:00+00:00"),
        ("2026-10-25T22:45:00+00:00", "2026-10-25T23:15:00+00:00"),
    ]
    assert tomorrow["windows"] == [today["windows"][1]]
    assert today["windows"][0]["paid"] is False


def test_tomorrow_unknown_before_the_auction() -> None:
    prices = {utc(2026, 10, 25, 10, 0): 0.05}
    today, tomorrow = card_days(runtime(prices), utc(2026, 10, 25, 11, 0))
    assert today["known"] and not tomorrow["known"]
    assert today["windows"] == tomorrow["windows"] == []


def _list(name: str) -> list[str]:
    match = re.search(rf"const {name} = \[([^\]]*)\];", CARD)
    assert match, f"{name} not found in the card"
    return re.findall(r'"([a-z_]+)"', match.group(1))


def test_issues_match() -> None:
    assert _list("ISSUES") == list(ISSUES)
    for language in ("de", "en"):
        block = CARD.split(f"  {language}: {{\n", 1)[1]
        texts = re.search(r"issues: \{(.*?)\n    \},", block, re.S)
        assert texts, "issue texts not found"
        for key in ISSUES:
            assert f"{key}:" in texts.group(1), (language, key)


def test_entities_the_card_reads_exist() -> None:
    """Translation keys the card looks up are entities of the integration."""
    keys = set(re.findall(r'_state\("([a-z_]+)"\)', CARD))
    keys |= set(re.findall(r'_tile\("([a-z_]+)"', CARD))
    keys |= set(re.findall(r'link\("([a-z_]+)"', CARD))
    keys |= set(re.findall(r"_entities\.([a-z_]+)", CARD))
    keys |= set(
        re.findall(
            r'"([a-z_]+)"', CARD.split("const TOTALS = [", 1)[1].split("]", 1)[0]
        )
    )
    assert keys >= {
        "remunerated",
        "unpaid_windows",
        "revenue_lost",
        "catch_up",
        "active_rule",
    }
    known = (
        set(STRINGS["entity"]["sensor"])
        | set(STRINGS["entity"]["binary_sensor"])
        | set(STRINGS["entity"]["calendar"])
    )
    assert keys <= known, keys - known
