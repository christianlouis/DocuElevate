"""Tests for app/tasks/subscription_tasks.py."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestApplyPendingSubscriptionChangesAll:
    """Tests for the apply_pending_subscription_changes_all Celery task."""

    def _make_mock_db(self, profiles: list) -> MagicMock:
        """Return a mock database session whose query chain returns *profiles*."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = profiles
        return mock_db

    # ------------------------------------------------------------------
    # Happy-path: no pending profiles
    # ------------------------------------------------------------------

    @patch("app.utils.subscription.apply_pending_subscription_changes")
    @patch("app.database.SessionLocal")
    def test_no_pending_profiles_returns_zero_counts(self, mock_session_local, mock_apply_changes):
        """When no profiles have pending changes the task returns zeros."""
        from app.tasks.subscription_tasks import apply_pending_subscription_changes_all

        mock_db = self._make_mock_db([])
        mock_session_local.return_value = mock_db

        result = apply_pending_subscription_changes_all()

        assert result == {"checked": 0, "applied": 0}
        mock_apply_changes.assert_not_called()
        mock_db.close.assert_called_once()

    # ------------------------------------------------------------------
    # Happy-path: all pending changes are applied
    # ------------------------------------------------------------------

    @patch("app.utils.subscription.apply_pending_subscription_changes")
    @patch("app.database.SessionLocal")
    def test_all_profiles_applied(self, mock_session_local, mock_apply_changes):
        """When every pending change succeeds, checked == applied."""
        from app.tasks.subscription_tasks import apply_pending_subscription_changes_all

        profiles = [MagicMock(user_id="user1"), MagicMock(user_id="user2")]
        mock_db = self._make_mock_db(profiles)
        mock_session_local.return_value = mock_db
        mock_apply_changes.return_value = True

        result = apply_pending_subscription_changes_all()

        assert result == {"checked": 2, "applied": 2}
        assert mock_apply_changes.call_count == 2
        mock_db.close.assert_called_once()

    # ------------------------------------------------------------------
    # Partial application (some return False)
    # ------------------------------------------------------------------

    @patch("app.utils.subscription.apply_pending_subscription_changes")
    @patch("app.database.SessionLocal")
    def test_partial_application(self, mock_session_local, mock_apply_changes):
        """When only some pending changes are applied, checked > applied."""
        from app.tasks.subscription_tasks import apply_pending_subscription_changes_all

        profiles = [
            MagicMock(user_id="user1"),
            MagicMock(user_id="user2"),
            MagicMock(user_id="user3"),
        ]
        mock_db = self._make_mock_db(profiles)
        mock_session_local.return_value = mock_db
        # First and third succeed, second does not
        mock_apply_changes.side_effect = [True, False, True]

        result = apply_pending_subscription_changes_all()

        assert result == {"checked": 3, "applied": 2}
        mock_db.close.assert_called_once()

    # ------------------------------------------------------------------
    # apply_pending_subscription_changes is called with correct args
    # ------------------------------------------------------------------

    @patch("app.utils.subscription.apply_pending_subscription_changes")
    @patch("app.database.SessionLocal")
    def test_apply_called_with_db_and_user_id(self, mock_session_local, mock_apply_changes):
        """apply_pending_subscription_changes must receive (db, user_id)."""
        from app.tasks.subscription_tasks import apply_pending_subscription_changes_all

        profile = MagicMock(user_id="alice")
        mock_db = self._make_mock_db([profile])
        mock_session_local.return_value = mock_db
        mock_apply_changes.return_value = True

        apply_pending_subscription_changes_all()

        mock_apply_changes.assert_called_once_with(mock_db, "alice")

    # ------------------------------------------------------------------
    # Exception handling
    # ------------------------------------------------------------------

    @patch("app.tasks.subscription_tasks.logger")
    @patch("app.utils.subscription.apply_pending_subscription_changes")
    @patch("app.database.SessionLocal")
    def test_exception_is_logged(self, mock_session_local, mock_apply_changes, mock_logger):
        """Exceptions raised during DB access must be caught and logged."""
        from app.tasks.subscription_tasks import apply_pending_subscription_changes_all

        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("db exploded")
        mock_session_local.return_value = mock_db

        result = apply_pending_subscription_changes_all()

        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        assert "Error in apply_pending_subscription_changes_all" in error_msg
        # Still returns the (zero) counts
        assert result == {"checked": 0, "applied": 0}

    @patch("app.utils.subscription.apply_pending_subscription_changes")
    @patch("app.database.SessionLocal")
    def test_db_close_called_even_on_exception(self, mock_session_local, mock_apply_changes):
        """db.close() must be called even when an exception is raised."""
        from app.tasks.subscription_tasks import apply_pending_subscription_changes_all

        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("db exploded")
        mock_session_local.return_value = mock_db

        apply_pending_subscription_changes_all()

        mock_db.close.assert_called_once()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    @patch("app.tasks.subscription_tasks.logger")
    @patch("app.utils.subscription.apply_pending_subscription_changes")
    @patch("app.database.SessionLocal")
    def test_info_logged_with_counts(self, mock_session_local, mock_apply_changes, mock_logger):
        """An info-level summary must be logged after the run."""
        from app.tasks.subscription_tasks import apply_pending_subscription_changes_all

        mock_db = self._make_mock_db([MagicMock(user_id="u1")])
        mock_session_local.return_value = mock_db
        mock_apply_changes.return_value = True

        apply_pending_subscription_changes_all()

        mock_logger.info.assert_called_once()
        log_msg = mock_logger.info.call_args[0][0]
        assert "checked" in log_msg
        assert "applied" in log_msg

    # ------------------------------------------------------------------
    # Celery task registration
    # ------------------------------------------------------------------

    def test_task_is_callable(self):
        """apply_pending_subscription_changes_all must be callable."""
        from app.tasks.subscription_tasks import apply_pending_subscription_changes_all

        assert callable(apply_pending_subscription_changes_all)

    def test_task_has_celery_attributes(self):
        """The task must be registered as a Celery task (has apply_async/delay)."""
        from app.tasks.subscription_tasks import apply_pending_subscription_changes_all

        assert hasattr(apply_pending_subscription_changes_all, "apply_async")
        assert hasattr(apply_pending_subscription_changes_all, "delay")

    def test_task_name(self):
        """The Celery task name must match its canonical module path."""
        from app.tasks.subscription_tasks import apply_pending_subscription_changes_all

        assert (
            apply_pending_subscription_changes_all.name
            == "app.tasks.subscription_tasks.apply_pending_subscription_changes_all"
        )
