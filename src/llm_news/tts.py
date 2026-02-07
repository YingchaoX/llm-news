"""Text-to-Speech via Edge TTS.

Edge TTS 微软免费 TTS 引擎，无需 API Key，无速率限制。
"""

import asyncio
import logging
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)


async def _generate(text: str, voice: str, rate: str, output_path: Path) -> None:
    """Generate MP3 audio from text using Edge TTS."""
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(output_path))


def generate_audio(
    text: str,
    output_path: str | Path,
    voice: str = "en-US-AriaNeural",
    rate: str = "+10%",
) -> Path:
    """Generate MP3 audio from text.

    Args:
        text: The broadcast script to convert to speech.
        output_path: Path to save the MP3 file.
        voice: Edge TTS voice name.
        rate: Speech rate adjustment (e.g. "+10%", "-5%").

    Returns:
        Path to the generated MP3 file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Generating audio: voice=%s, rate=%s, output=%s",
        voice,
        rate,
        output_path,
    )
    logger.info("Script length: %d chars", len(text))

    asyncio.run(_generate(text, voice, rate, output_path))

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Audio generated: %.1f MB → %s", size_mb, output_path)
    return output_path
