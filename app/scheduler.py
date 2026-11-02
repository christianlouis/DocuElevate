"""Stateless Celery Beat scheduler with a process-level freshness marker."""
from celery.beat import Scheduler
from app.utils.upload_health import HEARTBEAT_TTL, SCHEDULER_KEY, mark_fresh

class HeartbeatScheduler(Scheduler):
    """Avoid shelve/dbm state and record liveness from the Beat process."""
    def tick(self, *args, **kwargs):
        mark_fresh(SCHEDULER_KEY)
        # Keep the marker fresh even when Celery has no task due.  This also
        # bounds detection time if a schedule's next due time is far away.
        return min(super().tick(*args, **kwargs), HEARTBEAT_TTL / 2)
