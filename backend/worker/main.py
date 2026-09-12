"""Arq worker entrypoint (plan ADR 4, Section D). Run with:
    arq worker.main.WorkerSettings
Requires a real Redis instance (REDIS_URL) - not exercised by the Phase 0
smoke tests, which don't depend on the queue.
"""

from worker.tasks import example_task


class WorkerSettings:
    functions = [example_task]
    # TODO(Phase 1): redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
