"""Background job queue management for long-running moderation tasks."""

import asyncio
import time
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict


class JobQueueManager:
    """Simple in-memory async job queue for moderation work."""

    def __init__(
        self,
        *,
        worker_count: int,
        process_job: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
    ):
        self.worker_count = worker_count
        self.process_job = process_job
        self.queue: asyncio.Queue = asyncio.Queue()
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.workers = []

    async def start(self) -> None:
        self.workers = [
            asyncio.create_task(self._worker_loop(f"queue-worker-{idx + 1}"))
            for idx in range(self.worker_count)
        ]

    async def stop(self) -> None:
        for worker in self.workers:
            worker.cancel()
        for worker in self.workers:
            with suppress(asyncio.CancelledError):
                await worker

    async def submit(self, payload: Dict[str, Any], request_id: str) -> Dict[str, Any]:
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "request_id": request_id,
            "submitted_at": datetime.utcnow().isoformat(),
            **payload,
        }
        await self.queue.put(job_id)
        return self.jobs[job_id]

    def get(self, job_id: str) -> Dict[str, Any]:
        return self.jobs.get(job_id)

    def size(self) -> int:
        return self.queue.qsize()

    async def _worker_loop(self, worker_name: str) -> None:
        while True:
            job_id = await self.queue.get()
            job = self.jobs.get(job_id)
            if job is None:
                self.queue.task_done()
                continue

            job["status"] = "processing"
            job["started_at"] = datetime.utcnow().isoformat()
            started_at = time.time()

            try:
                result = await self.process_job(job)
                result["inference_time_ms"] = int((time.time() - started_at) * 1000)
                job["status"] = "completed"
                job["result"] = result
                job["completed_at"] = datetime.utcnow().isoformat()
            except Exception as exc:
                status_code = getattr(exc, "status_code", 500)
                detail = getattr(exc, "detail", str(exc))
                job["status"] = "failed"
                job["error"] = {
                    "status_code": status_code,
                    "detail": detail,
                    "worker": worker_name,
                }
                job["completed_at"] = datetime.utcnow().isoformat()
            finally:
                cleanup_path = job.get("cleanup_path")
                if cleanup_path:
                    Path(cleanup_path).unlink(missing_ok=True)
                self.queue.task_done()
