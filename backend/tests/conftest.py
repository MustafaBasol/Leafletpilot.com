import socket

import pytest
from sqlalchemy.engine import make_url

from app.core.config import settings


def pytest_collection_modifyitems(config, items):
    if _test_database_reachable():
        return

    skip_db = pytest.mark.skip(reason="TEST_DATABASE_URL is not configured or reachable.")
    for item in items:
        if "when_test_database_url_is_configured" in item.name:
            item.add_marker(skip_db)


def _test_database_reachable() -> bool:
    if not settings.test_database_url:
        return False
    url = make_url(settings.test_database_url)
    host = url.host or "localhost"
    port = url.port or 5432
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False
