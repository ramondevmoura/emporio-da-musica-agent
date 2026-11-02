"""Speech-to-text for voice messages (OpenAI transcription API).

Older customers often prefer sending audio over typing. The transcript is shown back to the
customer ("🎤 Você disse: ...") and then follows exactly the same path as a typed message.
"""

from __future__ import annotations

from openai import OpenAI

from emporio import config
from emporio.data import get_store_data


def _vocabulary_hint() -> str:
    """Brand names help the transcriber spell 'Takamine' instead of 'taca mine'."""
    brands = sorted({p.name.split()[0] for p in get_store_data().products.values()})
    return "Empório da Música, violão, guitarra, ukulele, PIX. Marcas: " + ", ".join(brands)


def transcribe(
    audio_bytes: bytes, filename: str = "audio.wav", client: OpenAI | None = None
) -> str:
    client = client or OpenAI(api_key=config.OPENAI_API_KEY or None)
    result = client.audio.transcriptions.create(
        model=config.OPENAI_TRANSCRIBE_MODEL,
        file=(filename, audio_bytes),
        language="pt",
        prompt=_vocabulary_hint(),
    )
    return result.text.strip()
