"""
MIRAGE-X — test configuration.

Every test gets its own throwaway SQLite file (via monkeypatching
db.DB_PATH) so tests never touch the real mirage_x.db used for the demo,
and tests don't leak state into each other.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import db  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix="_mirage_x_test.db")
    os.close(fd)
    os.remove(path)  # db.init_db creates it fresh
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db(reset=True)
    yield
    if os.path.exists(path):
        os.remove(path)
