import uuid
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class JobInfo:
    id: str
    status: str
    manifest_result: dict
    logs: str = ""


class JobStore:
    def __init__(self):
        self.jobs: Dict[str, JobInfo] = {}

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = JobInfo(id=job_id, status="pending", manifest_result={})
        return job_id

    def update_job(self, job_id: str, status: str, manifest_result: dict, logs: str):
        if job_id in self.jobs:
            self.jobs[job_id].status = status
            self.jobs[job_id].manifest_result = manifest_result
            self.jobs[job_id].logs = logs

    def get_job(self, job_id: str) -> Optional[JobInfo]:
        return self.jobs.get(job_id)


# Singleton global job store
job_store = JobStore()
job_store = JobStore()
