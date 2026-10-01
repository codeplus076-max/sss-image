"""Asynchronous Analysis Job Service.

Provides background queue management for multi-model Side-Scan Sonar
survey analyses, preventing HTTP gateway timeouts (e.g. Render / Cloudflare 100s limits)
and offering real-time progress feedback to the operator.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobService:
    """In-memory thread-safe job tracking service for asynchronous sonar analyses."""

    def __init__(self, max_history: int = 100):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._max_history = max_history

    def create_job(self, job_id: str, original_filename: str) -> Dict[str, Any]:
        """Initialize and register a new queued job."""
        now = _utc_now_iso()
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0.05,
            "current_step": "Survey registered in execution queue",
            "original_filename": original_filename,
            "created_at": now,
            "updated_at": now,
            "poll_url": f"/api/v1/analysis/jobs/{job_id}",
            "error": None,
            "result": None,
        }
        self._jobs[job_id] = job_data

        # Evict oldest entry if maximum history reached
        if len(self._jobs) > self._max_history:
            oldest_key = next(iter(self._jobs))
            self._jobs.pop(oldest_key, None)

        return job_data

    def update_progress(self, job_id: str, progress: float, current_step: str):
        """Update job progress and human-readable workflow step."""
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "processing"
            self._jobs[job_id]["progress"] = round(min(1.0, max(0.0, progress)), 2)
            self._jobs[job_id]["current_step"] = current_step
            self._jobs[job_id]["updated_at"] = _utc_now_iso()

    def complete_job(self, job_id: str, result: Any):
        """Mark job as successfully completed and store analysis result payload."""
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "completed"
            self._jobs[job_id]["progress"] = 1.0
            self._jobs[job_id]["current_step"] = "Analysis completed successfully"
            self._jobs[job_id]["updated_at"] = _utc_now_iso()
            self._jobs[job_id]["result"] = result

    def fail_job(self, job_id: str, error_message: str):
        """Mark job as failed with specific error details."""
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = "failed"
            self._jobs[job_id]["progress"] = 1.0
            self._jobs[job_id]["current_step"] = f"Failed: {error_message}"
            self._jobs[job_id]["updated_at"] = _utc_now_iso()
            self._jobs[job_id]["error"] = error_message

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve current job state by ID."""
        return self._jobs.get(job_id)


job_service = JobService()
