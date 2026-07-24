from pydantic import BaseModel, ConfigDict, Field


class SynthesizeBody(BaseModel):
    text: str = Field(min_length=1, description="Vietnamese text to synthesize.")
    voice: str | None = Field(
        default=None,
        description="Preset voice id (slug from /v1/voices, e.g. 'pham-tuyen') or its name.",
    )
    style: str | None = Field(default=None, description="tu_nhien | tin_tuc | doc_truyen")
    denoise: bool = False


class TextToSpeechBody(BaseModel):
    """ElevenLabs-compatible body for POST /v1/text-to-speech/{voice_id}.

    Extra fields (model_id, voice_settings, ...) are accepted and ignored so an
    ElevenLabs client can call this endpoint unchanged.
    """
    model_config = ConfigDict(extra="ignore")

    text: str = Field(min_length=1)
    style: str | None = None
    denoise: bool = False


class VoiceLabels(BaseModel):
    gender: str = ""
    accent: str = ""   # mapped from VieNeu "region"
    style: str = ""


class Voice(BaseModel):
    voice_id: str
    name: str
    category: str = "premade"
    description: str = ""
    labels: VoiceLabels


class VoicesResponse(BaseModel):
    voices: list[Voice]
