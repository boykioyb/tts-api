"""gRPC server hosting the VieNeu TTS engine."""
from __future__ import annotations

import logging
import os
import signal
import tempfile
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

from app import audio as audio_codec
from app import config
from app.engine import TtsEngine
from app.generated import tts_pb2, tts_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("tts.server")


class TtsServicer(tts_pb2_grpc.TtsServiceServicer):
    def __init__(self, engine: TtsEngine) -> None:
        self._engine = engine

    @staticmethod
    def _write_ref(ref_bytes: bytes) -> str:
        fd, path = tempfile.mkstemp(suffix=".wav")
        with os.fdopen(fd, "wb") as fh:
            fh.write(ref_bytes)
        return path

    def Synthesize(self, request, context):
        ref_path = None
        try:
            if request.ref_audio:
                ref_path = self._write_ref(request.ref_audio)
            audio = self._engine.synthesize(
                text=request.text,
                voice=request.voice or None,
                style=request.style or None,
                ref_audio_path=ref_path,
                denoise=request.denoise,
            )
            audio, out_sr = audio_codec.resample(
                audio, config.SAMPLE_RATE, request.target_sample_rate
            )
            if request.format == tts_pb2.AUDIO_FORMAT_MP3:
                data, fmt = audio_codec.encode_mp3(audio, out_sr, request.mp3_bitrate_kbps), \
                    tts_pb2.AUDIO_FORMAT_MP3
            elif request.format == tts_pb2.AUDIO_FORMAT_PCM_F32:
                data, fmt = audio.tobytes(), tts_pb2.AUDIO_FORMAT_PCM_F32
            else:
                data, fmt = audio_codec.encode_wav(audio, out_sr), tts_pb2.AUDIO_FORMAT_WAV
            return tts_pb2.SynthesizeResponse(
                audio=data,
                sample_rate=out_sr,
                format=fmt,
                num_samples=int(audio.shape[0]),
            )
        except ValueError as exc:  # unknown voice id/name
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except Exception as exc:  # noqa: BLE001 - surface as a clean gRPC error
            logger.exception("Synthesize failed")
            context.abort(grpc.StatusCode.INTERNAL, f"synthesis failed: {exc}")
        finally:
            if ref_path and os.path.exists(ref_path):
                os.remove(ref_path)

    def SynthesizeStream(self, request, context):
        try:
            for chunk in self._engine.synthesize_stream(
                text=request.text,
                voice=request.voice or None,
                style=request.style or None,
            ):
                yield tts_pb2.AudioChunk(
                    audio=chunk.tobytes(),
                    sample_rate=config.SAMPLE_RATE,
                    is_final=False,
                )
            yield tts_pb2.AudioChunk(sample_rate=config.SAMPLE_RATE, is_final=True)
        except ValueError as exc:  # unknown voice id/name
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("SynthesizeStream failed")
            context.abort(grpc.StatusCode.INTERNAL, f"stream synthesis failed: {exc}")

    def ListVoices(self, request, context):
        return tts_pb2.ListVoicesResponse(
            voices=[
                tts_pb2.VoiceInfo(
                    voice_id=v["voice_id"],
                    name=v["name"],
                    description=v["description"],
                    gender=v["gender"],
                    region=v["region"],
                    style=v["style"],
                    category=v["category"],
                )
                for v in self._engine.list_voices()
            ]
        )


def serve() -> None:
    max_bytes = config.MAX_MESSAGE_MB * 1024 * 1024
    options = [
        ("grpc.max_send_message_length", max_bytes),
        ("grpc.max_receive_message_length", max_bytes),
    ]

    # Load the model BEFORE marking the service healthy, so readiness == "can serve".
    engine = TtsEngine()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS), options=options)
    tts_pb2_grpc.add_TtsServiceServicer_to_server(TtsServicer(engine), server)

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    service_name = tts_pb2.DESCRIPTOR.services_by_name["TtsService"].full_name
    reflection.enable_server_reflection(
        (service_name, health.SERVICE_NAME, reflection.SERVICE_NAME), server
    )

    server.add_insecure_port(f"[::]:{config.PORT}")
    server.start()
    health_servicer.set(service_name, health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    logger.info("TTS gRPC server listening on :%d", config.PORT)

    def _shutdown(*_):
        logger.info("Shutting down...")
        health_servicer.set(service_name, health_pb2.HealthCheckResponse.NOT_SERVING)
        server.stop(grace=5)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
