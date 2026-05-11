"""全市场评分异步任务（内存态），供前端轮询进度。

注意：任务状态保存在进程内存中，仅适合单 worker / 本地开发；
多 worker 部署需改为 Redis 等共享存储。
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

_MAX_JOBS = 100
_lock = threading.Lock()
_jobs: dict[str, "ScoreMarketJob"] = {}


@dataclass
class ScoreMarketJob:
    status: str  # pending | running | completed | failed
    progress: int = 0
    stage: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=lambda: time.time())


def _evict_oldest_unlocked() -> None:
    if len(_jobs) <= _MAX_JOBS:
        return
    overflow = len(_jobs) - _MAX_JOBS + 20
    if overflow <= 0:
        return
    ordered = sorted(_jobs.items(), key=lambda kv: kv[1].created_at)
    for key, _ in ordered[:overflow]:
        _jobs.pop(key, None)


def create_job() -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _evict_oldest_unlocked()
        _jobs[job_id] = ScoreMarketJob(status="pending", progress=0, stage="任务已创建")
    return job_id


def get_job(job_id: str) -> ScoreMarketJob | None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        return ScoreMarketJob(
            status=job.status,
            progress=job.progress,
            stage=job.stage,
            result=job.result,
            error=job.error,
            created_at=job.created_at,
        )


def update_job(job_id: str, *, status: str | None = None, progress: int | None = None, stage: str | None = None) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = max(0, min(100, int(progress)))
        if stage is not None:
            job.stage = stage


def complete_job(job_id: str, result: dict[str, Any]) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "completed"
        job.progress = 100
        job.stage = "完成"
        job.result = result
        job.error = None


def fail_job(job_id: str, message: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "failed"
        job.error = message
        job.result = None
        job.stage = "失败"
