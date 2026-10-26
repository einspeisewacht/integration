"""Static checks for the bundled automation blueprints (run locally and in CI)."""

from __future__ import annotations

from pathlib import Path

import pytest
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.util.yaml import load_yaml

BLUEPRINTS = (
    Path(__file__).parent.parent / "blueprints" / "automation" / "einspeisewacht"
)
FILES = sorted(BLUEPRINTS.glob("*.yaml"))


def test_blueprints_exist() -> None:
    assert [f.name for f in FILES] == ["vergutung_aus_an.yaml"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_blueprint_is_valid(path: Path) -> None:
    blueprint = Blueprint(
        load_yaml(path),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    meta = blueprint.metadata
    assert meta["name"].startswith("Einspeisewacht")
    # The import button and HA's "re-import" use this URL.
    assert meta["source_url"] == (
        "https://github.com/einspeisewacht/integration/blob/main/"
        f"blueprints/automation/einspeisewacht/{path.name}"
    )
    assert meta["homeassistant"]["min_version"] == "2026.3.0"
