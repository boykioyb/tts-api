"""In-memory async TTS job store backing the LucyLab-compatible JSON-RPC layer.

`ttsLongText` submits a job and returns immediately; a background task drives it
through pending → processing → completed/failed while the client polls
`getExportStatus`. Single-process only: jobs live in a dict, so a multi-worker
deployment would need a shared store (e.g. Redis). Out of scope here.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass

import grpc

from app.config import settings
from app.generated import tts_pb2
from app.grpc_client import client

logger = logging.getLogger("gateway.jobs")


@dataclass
class Job:
    id: str
    state: str = "pending"   # pending | processing | completed | failed
    url: str | None = None
    error: str | None = None


_STORE: dict[str, Job] = {}


def _new_id() -> str:
    return uuid.uuid4().hex[:22]


def get(job_id: str) -> Job | None:
    return _STORE.get(job_id)


async def submit(text: str, voice: str) -> Job:
    job = Job(id=_new_id())
    _STORE[job.id] = job
    asyncio.create_task(_run(job, text, voice))
    return job


async def _synthesize(text: str, voice: str) -> bytes:
    # MP3 so the downloaded bytes match the client's .mp3 destination filename.
    req = tts_pb2.SynthesizeRequest(text=text, voice=voice, format=tts_pb2.AUDIO_FORMAT_MP3)
    try:
        resp = await client.synthesize(req)
    except grpc.aio.AioRpcError as exc:
        # Drop-in forgiving: an unknown voice id falls back to the worker default
        # rather than failing the whole job.
        if exc.code() == grpc.StatusCode.INVALID_ARGUMENT and voice:
            logger.warning("unknown voice %r, falling back to default", voice)
            req = tts_pb2.SynthesizeRequest(text=text, voice="", format=tts_pb2.AUDIO_FORMAT_MP3)
            resp = await client.synthesize(req)
        else:
            raise
    return resp.audio


async def _run(job: Job, text: str, voice: str) -> None:
    job.state = "processing"
    try:
        audio = await _synthesize(text, voice)
        path = os.path.join(settings.files_dir, f"{job.id}.mp3")
        with open(path, "wb") as fh:
            fh.write(audio)
        job.url = f"{settings.public_base_url.rstrip('/')}/files/{job.id}.mp3"
        job.state = "completed"
    except Exception as exc:  # noqa: BLE001
        logger.exception("job %s failed", job.id)
        job.state = "failed"
        job.error = str(exc)
