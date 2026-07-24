"""Async gRPC client wrapper. One long-lived channel is reused across requests."""
from __future__ import annotations

from typing import AsyncIterator

import grpc

from app.config import settings
from app.generated import tts_pb2, tts_pb2_grpc


class TtsClient:
    def __init__(self) -> None:
        self._channel: grpc.aio.Channel | None = None
        self._stub: tts_pb2_grpc.TtsServiceStub | None = None

    async def connect(self) -> None:
        max_bytes = settings.max_message_mb * 1024 * 1024
        self._channel = grpc.aio.insecure_channel(
            settings.tts_grpc_target,
            options=[
                ("grpc.max_send_message_length", max_bytes),
                ("grpc.max_receive_message_length", max_bytes),
            ],
        )
        self._stub = tts_pb2_grpc.TtsServiceStub(self._channel)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()

    @property
    def stub(self) -> tts_pb2_grpc.TtsServiceStub:
        if self._stub is None:
            raise RuntimeError("gRPC client not connected")
        return self._stub

    async def synthesize(self, request: tts_pb2.SynthesizeRequest) -> tts_pb2.SynthesizeResponse:
        return await self.stub.Synthesize(request, timeout=settings.request_timeout)

    async def synthesize_stream(
        self, request: tts_pb2.SynthesizeRequest
    ) -> AsyncIterator[tts_pb2.AudioChunk]:
        async for chunk in self.stub.SynthesizeStream(request, timeout=settings.request_timeout):
            yield chunk

    async def list_voices(self) -> tts_pb2.ListVoicesResponse:
        return await self.stub.ListVoices(tts_pb2.ListVoicesRequest(), timeout=10)


client = TtsClient()
