import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class JobInfo:
    id: str
    status: str
    manifest_result: dict[str, Any]
    logs: str = ""
    created_at: float = field(default_factory=time.time)


class JobStore:
    """In-memory job store with bounded capacity and TTL eviction (fixes #21).

    Oldest entries are evicted first when *max_jobs* is exceeded.  Entries
    older than *ttl_seconds* are purged lazily on each ``create_job`` call.
    """

    MAX_JOBS = 1000
    TTL_SECONDS = 3600  # 1 hour

    def __init__(
        self,
        max_jobs: int = MAX_JOBS,
        ttl_seconds: int = TTL_SECONDS,
    ) -> None:
        self.max_jobs = max_jobs
        self.ttl_seconds = ttl_seconds
        self.jobs: OrderedDict[str, JobInfo] = OrderedDict()

    def _evict_expired(self) -> None:
        """Remove entries older than *ttl_seconds*."""
        cutoff = time.time() - self.ttl_seconds
        expired = [jid for jid, info in self.jobs.items() if info.created_at < cutoff]
        for jid in expired:
            del self.jobs[jid]

    def _enforce_capacity(self) -> None:
        """Evict oldest entries until we are within *max_jobs*."""
        while len(self.jobs) > self.max_jobs:
            self.jobs.popitem(last=False)

    def create_job(self) -> str:
        self._evict_expired()
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = JobInfo(id=job_id, status="pending", manifest_result={})
        self._enforce_capacity()
        return job_id

    def update_job(
        self, job_id: str, status: str, manifest_result: dict[str, Any], logs: str
    ) -> None:
        if job_id in self.jobs:
            self.jobs[job_id].status = status
            self.jobs[job_id].manifest_result = manifest_result
            self.jobs[job_id].logs = logs

    def get_job(self, job_id: str) -> Optional[JobInfo]:
        return self.jobs.get(job_id)


# Singleton global job store
job_store = JobStore()
