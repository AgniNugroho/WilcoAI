from __future__ import annotations
import asyncio
import logging
import os
from typing import Optional, AsyncIterator, Any

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

logger = logging.getLogger(__name__)


class GeminiLiveClient:
    """
    Async client managing real-time bidirectional audio & context streaming
    with Google GenAI Multimodal Live API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[Any] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("MODEL_NAME", "gemini-2.0-flash-exp")
        self._client = client
        self._session_ctx: Optional[Any] = None
        self._session: Optional[Any] = None
        self._is_connected = False
        self.sent_contexts: list[str] = []
        self.sent_audio_chunks: list[bytes] = []

    @property
    def is_connected(self) -> bool:
        """Returns True if the Live streaming session is active."""
        return self._is_connected

    async def connect(self, system_instruction: Optional[str] = None) -> None:
        """
        Connect to the Gemini Multimodal Live API session with configured
        modalities, system instructions, and voice output.
        """
        if system_instruction:
            self.sent_contexts.append(system_instruction)

        if self._client is None and genai is not None:
            self._client = genai.Client(api_key=self.api_key)

        if self._client is not None and types is not None:
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=types.Content(
                    parts=[types.Part.from_text(text=system_instruction)]
                )
                if system_instruction
                else None,
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Puck"
                        )
                    )
                ),
            )
            self._session_ctx = self._client.aio.live.connect(
                model=self.model, config=config
            )
            self._session = await self._session_ctx.__aenter__()

        self._is_connected = True

    async def send_text_context(self, text: str) -> None:
        """Send dynamic context or updated ATC instruction frame to Live session."""
        self.sent_contexts.append(text)
        if self._session is not None:
            await self._session.send(input=text, end_of_turn=False)

    async def send_audio_chunk(
        self,
        data: bytes,
        mime_type: str = "audio/pcm;rate=24000",
    ) -> None:
        """Stream an incoming pilot PCM audio chunk to the Live session."""
        self.sent_audio_chunks.append(data)
        if self._session is not None and types is not None:
            await self._session.send_realtime_input(
                audio=types.Blob(data=data, mime_type=mime_type)
            )

    async def receive_stream(self) -> AsyncIterator[dict[str, Any]]:
        """
        Asynchronously yield response chunks (audio PCM and text transcripts)
        emitted by the Live API model.
        """
        if self._session is not None:
            async for response in self._session.receive():
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            yield {
                                "type": "audio",
                                "data": part.inline_data.data,
                                "mime_type": part.inline_data.mime_type or "audio/pcm",
                            }
                        if part.text:
                            yield {
                                "type": "transcript",
                                "role": "atc",
                                "text": part.text,
                            }
                if response.server_content and response.server_content.turn_complete:
                    yield {"type": "turn_complete"}

    async def close(self) -> None:
        """Gracefully terminate the Live API session."""
        self._is_connected = False
        if self._session is not None:
            try:
                await self._session.close()
            except Exception as e:
                logger.debug(f"Error closing session: {e}")
            self._session = None

        if self._session_ctx is not None:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error exiting session context: {e}")
            self._session_ctx = None


class MockGeminiLiveClient(GeminiLiveClient):
    """
    In-memory mock client implementing GeminiLiveClient interface
    for isolated testing and deterministic offline verification.
    """

    def __init__(
        self,
        api_key: Optional[str] = "mock-key",
        model: Optional[str] = "gemini-2.0-flash-exp",
    ):
        super().__init__(api_key=api_key, model=model)
        self.connected_event = asyncio.Event()
        self.receive_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.closed = False

    async def connect(self, system_instruction: Optional[str] = None) -> None:
        self._is_connected = True
        self.closed = False
        if system_instruction:
            self.sent_contexts.append(system_instruction)
        self.connected_event.set()

    async def send_text_context(self, text: str) -> None:
        self.sent_contexts.append(text)

    async def send_audio_chunk(
        self,
        data: bytes,
        mime_type: str = "audio/pcm;rate=24000",
    ) -> None:
        self.sent_audio_chunks.append(data)

    async def receive_stream(self) -> AsyncIterator[dict[str, Any]]:
        while not self.closed:
            try:
                item = await asyncio.wait_for(self.receive_queue.get(), timeout=0.05)
                yield item
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def push_mock_response(
        self,
        text: Optional[str] = None,
        audio: Optional[bytes] = None,
        turn_complete: bool = False,
    ) -> None:
        """Helper to inject simulated model outputs into the receive stream."""
        if text:
            await self.receive_queue.put({"type": "transcript", "role": "atc", "text": text})
        if audio:
            await self.receive_queue.put({"type": "audio", "data": audio})
        if turn_complete:
            await self.receive_queue.put({"type": "turn_complete"})

    async def close(self) -> None:
        self._is_connected = False
        self.closed = True


__all__ = ["GeminiLiveClient", "MockGeminiLiveClient"]
