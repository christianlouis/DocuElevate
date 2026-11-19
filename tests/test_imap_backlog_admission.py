from unittest.mock import MagicMock, patch

import pytest


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def limit(self, *args):
        return self

    def all(self):
        return self.rows


@pytest.mark.unit
def test_saturated_intake_admission_blocks_without_broker_read():
    from app.tasks import imap_tasks

    db = MagicMock()
    db.query.return_value = _Query([object()] * (imap_tasks.MAX_UNFINISHED_IMAP_INTAKES + 1))
    with (
        patch.object(imap_tasks, "_get_db_session", return_value=db),
        patch.object(imap_tasks.redis, "StrictRedis") as redis_cls,
    ):
        assert not imap_tasks._historical_payload_admission_available()
        redis_cls.from_url.assert_not_called()


@pytest.mark.unit
def test_queue_and_disk_bounds_are_enforced():
    from app.tasks import imap_tasks

    db = MagicMock()
    db.query.side_effect = [_Query([]), _Query([])]
    broker = MagicMock()
    broker.llen.side_effect = [imap_tasks.MAX_DOCUMENT_QUEUE_DEPTH + 1]
    with (
        patch.object(imap_tasks, "_get_db_session", return_value=db),
        patch.object(imap_tasks.redis.StrictRedis, "from_url", return_value=broker),
        patch.object(imap_tasks.shutil, "disk_usage", return_value=(0, 0, 10 * 1024**3)),
    ):
        assert not imap_tasks._historical_payload_admission_available()

    broker.llen.side_effect = [0] * 9
    with (
        patch.object(imap_tasks, "_get_db_session", return_value=db),
        patch.object(imap_tasks.redis.StrictRedis, "from_url", return_value=broker),
        patch.object(imap_tasks.shutil, "disk_usage", side_effect=OSError("unknown")),
    ):
        assert not imap_tasks._historical_payload_admission_available()


@pytest.mark.unit
def test_healthy_admission_allows_payload():
    from app.tasks import imap_tasks

    db = MagicMock()
    db.query.side_effect = [_Query([]), _Query([])]
    broker = MagicMock()
    broker.llen.return_value = 0
    with (
        patch.object(imap_tasks, "_get_db_session", return_value=db),
        patch.object(imap_tasks.redis.StrictRedis, "from_url", return_value=broker),
        patch.object(imap_tasks.shutil, "disk_usage", return_value=(0, 0, 10 * 1024**3)),
    ):
        assert imap_tasks._historical_payload_admission_available()
