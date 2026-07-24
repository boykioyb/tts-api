"""FastAPI gateway: HTTP/REST facade over the VieNeu gRPC worker."""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager

import grpc
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from app import jobs
from app.config import settings
from app.generated import tts_pb2
from app.grpc_client import client
from app.schemas import SynthesizeBody, TextToSpeechBody, VoicesResponse


@asynccontextmanager
async def lifespan(_: FastAPI):
    os.makedirs(settings.files_dir, exist_ok=True)
    await client.connect()
    yield
    await client.close()


app = FastAPI(title="VieNeu TTS Gateway", version="1.0.0", lifespan=lifespan)


_GRPC_TO_HTTP = {
    grpc.StatusCode.DEADLINE_EXCEEDED: 504,
    grpc.StatusCode.INVALID_ARGUMENT: 400,   # unknown/invalid voice
    grpc.StatusCode.NOT_FOUND: 404,
    grpc.StatusCode.UNAVAILABLE: 503,
}


def _grpc_error(exc: grpc.aio.AioRpcError) -> HTTPException:
    status = _GRPC_TO_HTTP.get(exc.code(), 502)
    return HTTPException(status_code=status, detail=exc.details() or str(exc.code()))


def parse_output_format(fmt: str | None, default: str) -> tuple[int, int, int, str]:
    """Map an ElevenLabs-style output_format string to
    (proto AudioFormat, target_sample_rate, mp3_bitrate_kbps, media_type).

    Supported: `mp3`, `mp3_<sr>_<kbps>` (e.g. mp3_44100_128), `wav`.
    """
    value = (fmt or default).lower()
    if value.startswith("mp3"):
        parts = value.split("_")
        sr = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        br = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 128
        return tts_pb2.AUDIO_FORMAT_MP3, sr, br, "audio/mpeg"
    if value.startswith("wav") or value.startswith("pcm"):
        parts = value.split("_")
        sr = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return tts_pb2.AUDIO_FORMAT_WAV, sr, 0, "audio/wav"
    raise HTTPException(status_code=400, detail=f"unsupported output_format: {fmt}")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/voices", response_model=VoicesResponse)
async def voices() -> VoicesResponse:
    try:
        resp = await client.list_voices()
    except grpc.aio.AioRpcError as exc:
        raise _grpc_error(exc)
    return VoicesResponse(
        voices=[
            {
                "voice_id": v.voice_id,
                "name": v.name,
                "category": v.category or "premade",
                "description": v.description,
                "labels": {"gender": v.gender, "accent": v.region, "style": v.style},
            }
            for v in resp.voices
        ]
    )


@app.post("/v1/tts")
async def tts(
    body: SynthesizeBody,
    output_format: str | None = Query(default=None, description="e.g. wav, mp3_44100_128"),
) -> Response:
    """Synthesize with a preset voice. Defaults to WAV; pass output_format for MP3."""
    fmt, sr, br, media_type = parse_output_format(output_format, default="wav")
    request = tts_pb2.SynthesizeRequest(
        text=body.text,
        voice=body.voice or "",
        style=body.style or "",
        denoise=body.denoise,
        format=fmt,
        target_sample_rate=sr,
        mp3_bitrate_kbps=br,
    )
    try:
        resp = await client.synthesize(request)
    except grpc.aio.AioRpcError as exc:
        raise _grpc_error(exc)
    return Response(
        content=resp.audio,
        media_type=media_type,
        headers={"X-Sample-Rate": str(resp.sample_rate)},
    )


@app.post("/v1/text-to-speech/{voice_id}")
async def text_to_speech(
    voice_id: str,
    body: TextToSpeechBody,
    output_format: str | None = Query(default=None, description="e.g. mp3_44100_128, wav"),
) -> Response:
    """ElevenLabs-compatible: voice id in the path, MP3 out by default."""
    fmt, sr, br, media_type = parse_output_format(output_format, default="mp3_44100_128")
    request = tts_pb2.SynthesizeRequest(
        text=body.text,
        voice=voice_id,
        style=body.style or "",
        denoise=body.denoise,
        format=fmt,
        target_sample_rate=sr,
        mp3_bitrate_kbps=br,
    )
    try:
        resp = await client.synthesize(request)
    except grpc.aio.AioRpcError as exc:
        raise _grpc_error(exc)
    return Response(content=resp.audio, media_type=media_type,
                    headers={"X-Sample-Rate": str(resp.sample_rate)})


@app.post("/v1/tts/clone")
async def tts_clone(
    text: str = Form(...),
    ref_audio: UploadFile = File(...),
    denoise: bool = Form(True),
) -> Response:
    """Voice cloning: synthesize `text` in the voice of the uploaded reference clip."""
    request = tts_pb2.SynthesizeRequest(
        text=text,
        ref_audio=await ref_audio.read(),
        denoise=denoise,
        format=tts_pb2.AUDIO_FORMAT_WAV,
    )
    try:
        resp = await client.synthesize(request)
    except grpc.aio.AioRpcError as exc:
        raise _grpc_error(exc)
    return Response(content=resp.audio, media_type="audio/wav")


@app.post("/v1/tts/stream")
async def tts_stream(body: SynthesizeBody) -> StreamingResponse:
    """Stream raw little-endian float32 PCM chunks as they are generated."""
    request = tts_pb2.SynthesizeRequest(
        text=body.text,
        voice=body.voice or "",
        style=body.style or "",
        format=tts_pb2.AUDIO_FORMAT_PCM_F32,
    )

    async def generate():
        try:
            async for chunk in client.synthesize_stream(request):
                if chunk.audio:
                    yield chunk.audio
        except grpc.aio.AioRpcError as exc:
            raise _grpc_error(exc)

    return StreamingResponse(
        generate(),
        media_type="application/octet-stream",
        headers={"X-Sample-Rate": "48000", "X-Audio-Format": "pcm_f32le"},
    )


# ---------------------------------------------------------------------------
# LucyLab-compatible JSON-RPC layer (async job + polling + hosted file URL).
# One endpoint, dispatched on `method`; audio is served back as a URL.
# ---------------------------------------------------------------------------

def _rpc_ok(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_err(req_id, code: str, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def _m_tts_long_text(inp: dict) -> dict:
    text = inp.get("text")
    if not text:
        raise ValueError("missing 'text'")
    voice = inp.get("userVoiceId") or ""
    job = await jobs.submit(text=text, voice=voice)
    block_count = len([b for b in re.split(r"\n+", text) if b.strip()]) or 1
    return {"projectExportId": job.id, "characterCount": len(text), "blockCount": block_count}


def _m_get_export_status(inp: dict) -> dict:
    job = jobs.get(inp.get("projectExportId", ""))
    if job is None:
        raise ValueError("unknown projectExportId")
    return {"jobId": job.id, "state": job.state, "url": job.url, "srtUrl": None, "error": job.error}


async def _m_get_user_voices(inp: dict) -> dict:
    limit = int(inp.get("limit", 10))
    page = int(inp.get("page", 1))
    resp = await client.list_voices()
    items = [{"id": v.voice_id, "name": v.name, "isActive": True} for v in resp.voices]
    start = max(0, (page - 1) * limit)
    return {"items": items[start:start + limit], "total": len(items)}


@app.post("/json-rpc")
async def json_rpc(payload: dict = Body(...)) -> dict:
    req_id = payload.get("id", "")
    method = payload.get("method")
    inp = payload.get("input") or {}
    handlers = {
        "ttsLongText": _m_tts_long_text,
        "getExportStatus": _m_get_export_status,
        "getUserVoices": _m_get_user_voices,
    }
    handler = handlers.get(method)
    if handler is None:
        return _rpc_err(req_id, "method_not_found", f"unknown method: {method}")
    try:
        result = handler(inp)
        if hasattr(result, "__await__"):
            result = await result
        return _rpc_ok(req_id, result)
    except grpc.aio.AioRpcError as exc:
        return _rpc_err(req_id, "upstream", exc.details() or str(exc.code()))
    except Exception as exc:  # noqa: BLE001
        return _rpc_err(req_id, "internal", str(exc))


@app.get("/files/{file_id}")
async def get_file(file_id: str) -> FileResponse:
    # Guard against path traversal; only serve flat files from files_dir.
    if "/" in file_id or "\\" in file_id or ".." in file_id:
        raise HTTPException(status_code=400, detail="invalid file id")
    path = os.path.join(settings.files_dir, file_id)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="not found")
    media_type = "audio/mpeg" if file_id.endswith(".mp3") else "audio/wav"
    return FileResponse(path, media_type=media_type)
