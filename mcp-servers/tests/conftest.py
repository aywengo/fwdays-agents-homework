import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME_MCP_STATE_DIR", str(tmp_path / "state"))
    for var in ("HOME_LAT", "HOME_LON", "PV_KWP", "NETATMO_DEVICE_ID"):
        monkeypatch.delenv(var, raising=False)
    yield
