from unittest.mock import MagicMock

import pytest

from app.utils import upload_concurrency


class FakeRedis:
    def __init__(self):
        self.tokens = {}
        self.calls = []

    def ping(self):
        return True

    def eval(self, script, _numkeys, key, *args):
        self.calls.append((script, key, args))
        if script == upload_concurrency._ACQUIRE_SCRIPT:
            limit, _ttl, token = args
            tokens = self.tokens.setdefault(key, set())
            if len(tokens) >= int(limit):
                return 0
            tokens.add(token)
            return 1
        self.tokens.setdefault(key, set()).discard(args[0])
        return 1


def test_three_slots_block_fourth_and_other_destination_is_independent(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(upload_concurrency, "_redis_client", fake)
    monkeypatch.setattr(upload_concurrency.settings, "upload_destination_concurrency", 3)

    leases = [upload_concurrency.acquire("user-integration:7") for _ in range(3)]
    with pytest.raises(upload_concurrency.UploadDestinationCapacityError):
        upload_concurrency.acquire("user-integration:7")
    other = upload_concurrency.acquire("user-integration:8")

    assert all(leases)
    assert other is not None


def test_release_allows_next_upload_and_release_failure_is_nonfatal(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(upload_concurrency, "_redis_client", fake)
    monkeypatch.setattr(upload_concurrency.settings, "upload_destination_concurrency", 1)
    lease = upload_concurrency.acquire("task:dropbox")
    upload_concurrency.release(lease)
    assert upload_concurrency.acquire("task:dropbox") is not None

    broken = MagicMock()
    broken.eval.side_effect = RuntimeError("redis down")
    monkeypatch.setattr(upload_concurrency, "_redis_client", broken)
    upload_concurrency.release(lease)


def test_redis_failure_fails_closed(monkeypatch):
    broken = MagicMock()
    broken.ping.side_effect = RuntimeError("redis down")
    monkeypatch.setattr(upload_concurrency, "_redis_client", broken)
    monkeypatch.setattr(upload_concurrency.settings, "upload_destination_concurrency", 3)

    with pytest.raises(upload_concurrency.UploadDestinationCapacityError):
        upload_concurrency.acquire("task:s3")


def test_lease_expiry_is_atomic_and_longer_than_upload_deadline(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(upload_concurrency, "_redis_client", fake)
    monkeypatch.setattr(upload_concurrency.settings, "upload_destination_concurrency", 3)
    monkeypatch.setattr(upload_concurrency.settings, "upload_destination_lease_seconds", 1200)

    lease = upload_concurrency.acquire("task:s3")
    script, _key, args = fake.calls[0]
    assert "ZREMRANGEBYSCORE" in script
    assert int(args[1]) >= 1200
    assert lease is not None


def test_upload_retry_keeps_request_retries_for_capacity_wait(monkeypatch):
    from celery.app.task import Context
    from celery.utils.threads import LocalStack

    from app.tasks.retry_config import UploadTaskWithRetry

    task = UploadTaskWithRetry()
    signature = MagicMock()
    task.signature_from_request = MagicMock(return_value=signature)
    signature.apply_async.return_value = None

    task.request_stack = LocalStack()
    task.request_stack.push(Context(retries=2, called_directly=False, is_eager=False))
    with pytest.raises(Exception) as raised:
        task.retry(
            args=("file.pdf", 7, 9),
            kwargs={},
            exc=upload_concurrency.UploadDestinationCapacityError(),
            queue="upload_delivery",
            priority=7,
        )

    assert raised.value.__class__.__name__ == "Retry"
    assert task.signature_from_request.call_args.kwargs["retries"] == 2
    assert task.signature_from_request.call_args.kwargs["queue"] == "upload_delivery"
    assert task.signature_from_request.call_args.kwargs["priority"] == 7
    signature.apply_async.assert_called_once_with()


def test_capacity_retry_publish_failure_requeues_source(monkeypatch):
    from celery.app.task import Context
    from celery.exceptions import Reject
    from celery.utils.threads import LocalStack

    from app.tasks.retry_config import UploadTaskWithRetry

    task = UploadTaskWithRetry()
    signature = MagicMock()
    signature.apply_async.side_effect = RuntimeError("broker unavailable")
    task.signature_from_request = MagicMock(return_value=signature)

    task.request_stack = LocalStack()
    task.request_stack.push(Context(retries=2, called_directly=False, is_eager=False))
    with pytest.raises(Reject) as raised:
        task.retry(
            args=("file.pdf", 7, 9),
            kwargs={},
            exc=upload_concurrency.UploadDestinationCapacityError(),
        )

    assert raised.value.requeue is True


def test_capacity_retry_in_eager_mode_does_not_publish(monkeypatch):
    from celery.app.task import Context
    from celery.utils.threads import LocalStack

    from app.tasks.retry_config import UploadTaskWithRetry

    task = UploadTaskWithRetry()
    signature = MagicMock()
    task.signature_from_request = MagicMock(return_value=signature)
    task.request_stack = LocalStack()
    task.request_stack.push(Context(retries=0, called_directly=False, is_eager=True))
    with pytest.raises(Exception) as raised:
        task.retry(args=(), kwargs={}, exc=upload_concurrency.UploadDestinationCapacityError())

    assert raised.value.__class__.__name__ == "Retry"
    signature.apply_async.assert_not_called()
