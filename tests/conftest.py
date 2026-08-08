import json
from pathlib import Path

import pytest

from savvy_scout.db.connection import get_connection, init_db
from savvy_scout.db.seed_config import seed_all

SAMPLE_OCDS_PATH = Path(__file__).parent.parent / "066188-2026_ocds.json"


@pytest.fixture
def conn():
    connection = get_connection(":memory:")
    init_db(connection)
    seed_all(connection)
    yield connection
    connection.close()


@pytest.fixture
def sample_ocds_package() -> dict:
    return json.loads(SAMPLE_OCDS_PATH.read_text(encoding="utf-8"))
