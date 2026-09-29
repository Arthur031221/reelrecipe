"""Local video transcription, frame OCR, and recipe extraction."""

from __future__ import annotations

import base64
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from reelrecipe.recipe import Recipe

WHISPER_MODEL = "mlx-community/whisper-small-mlx"
OCR_MODEL = "glm-ocr:q8_0"
RECIPE_MODEL = "qwen3:4b"
RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "servings": {"type": ["string", "null"]},
        "prep_time_minutes": {"type": ["number", "null"]},
        "cook_time_minutes": {"type": ["number", "null"]},
        "total_time_minutes": {"type": ["number", "null"]},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": ["string", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "note": {"type": ["string", "null"]},
                },
                "required": ["name", "quantity", "unit", "note"],
            },
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "time_minutes": {"type": ["number", "null"]},
                },
                "required": ["text", "time_minutes"],
            },
        },
    },
    "required": [
        "title", "servings", "prep_time_minutes", "cook_time_minutes",
        "total_time_minutes", "ingredients", "steps",
    ],
}


class ExtractionError(Exception):
    """An expected input or local service failure."""


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ExtractionError(f"{name} is required. Install it and retry.")
    return path


def run(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ExtractionError(result.stderr.strip()[-1000:] or f"{args[0]} failed")
    return result


def video_info(path: Path) -> tuple[float, bool]:
    result = run(
        require_tool("ffprobe"), "-v", "error", "-show_entries",
        "format=duration:stream=codec_type", "-of", "json", str(path),
    )
    info = json.loads(result.stdout)
    try:
        duration = float(info["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ExtractionError("Could not read the video duration") from exc
    if not 0 < duration <= 7200:
        raise ExtractionError("Video must be between 0 and 120 minutes")
    return duration, any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def sample_times(duration: float, max_frames: int) -> list[float]:
    count = min(max_frames, max(1, int(duration // 15) + 1))
    return [duration * (index + 0.5) / count for index in range(count)]


def ollama_post(base_url: str, endpoint: str, payload: dict) -> dict:
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}{endpoint}", json=payload, timeout=(5, 600)
        )
        if response.status_code == 404:
            model = payload.get("model", "requested model")
            raise ExtractionError(f"Ollama model {model} is missing. Run ollama pull {model}")
        response.raise_for_status()
        return response.json()
    except requests.ConnectionError as exc:
        raise ExtractionError(f"Could not reach Ollama at {base_url}. Start ollama serve") from exc
    except (requests.RequestException, ValueError) as exc:
        raise ExtractionError(f"Ollama request failed: {exc}") from exc


def get_video(source: str, work: Path) -> Path:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        if importlib.util.find_spec("yt_dlp") is None:
            raise ExtractionError(
                "URL input requires the url extra. Install with uv tool install '.[url]'"
            )
        template = str(work / "download.%(ext)s")
        run(sys.executable, "-m", "yt_dlp", "--no-playlist", "--max-filesize",
            "500M", "-o", template, source)
        files = list(work.glob("download.*"))
        if len(files) != 1:
            raise ExtractionError("yt-dlp did not produce one video file")
        return files[0]
    if parsed.scheme:
        raise ExtractionError("Use a local file or an http(s) URL")
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise ExtractionError(f"Video file does not exist: {path}")
    return path


def transcribe(path: Path, work: Path, has_audio: bool, model: str) -> str:
    if not has_audio:
        return ""
    audio = work / "audio.wav"
    run(require_tool("ffmpeg"), "-v", "error", "-y", "-i", str(path), "-vn",
        "-ac", "1", "-ar", "16000", str(audio))
    try:
        import mlx_whisper
    except ImportError as exc:
        raise ExtractionError(
            "mlx-whisper requires an Apple Silicon Mac and the macOS install"
        ) from exc
    try:
        result = mlx_whisper.transcribe(str(audio), path_or_hf_repo=model, verbose=False)
    except Exception as exc:
        raise ExtractionError(f"Transcription failed: {exc}") from exc
    return str(result.get("text") or "").strip()


def read_frames(
    path: Path, work: Path, duration: float, max_frames: int, base_url: str
) -> list[str]:
    notes = []
    for index, second in enumerate(sample_times(duration, max_frames)):
        frame = work / f"frame-{index:02d}.jpg"
        run(require_tool("ffmpeg"), "-v", "error", "-y", "-ss", str(second),
            "-i", str(path), "-frames:v", "1", "-vf", "scale=1024:-2", str(frame))
        encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
        answer = ollama_post(base_url, "/api/generate", {
            "model": OCR_MODEL,
            "prompt": (
                "Read only visible cooking text, ingredients, and quantities. "
                "Return plain text. If none, return empty text."
            ),
            "images": [encoded], "stream": False,
        })
        note = clean_ocr(str(answer.get("response") or ""))
        if note:
            notes.append(f"At {second:.1f} seconds: {note[:1000]}")
    ollama_post(base_url, "/api/generate", {
        "model": OCR_MODEL, "prompt": "", "keep_alive": 0, "stream": False,
    })
    return notes


def clean_ocr(raw: str) -> str:
    """Discard repeated OCR lines and formatting echoed by small vision models."""
    lines = []
    seen = set()
    for raw_line in raw.splitlines():
        line = raw_line.strip().strip("`# ")
        if not line or line.lower() in {"markdown", "text"}:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
        if len(lines) == 30:
            break
    return "\n".join(lines)[:1000]


def merge_recipe(transcript: str, notes: list[str], source: str, base_url: str) -> Recipe:
    if not transcript and not notes:
        raise ExtractionError("No speech or readable frame text was found")
    prompt = (
        "Extract a cooking recipe from the evidence below. Use only explicit evidence. "
        "Do not invent ingredients, quantities, times, or steps. Leave unsupported fields null "
        "or empty. For ingredients, put only the food in name, the amount in quantity, "
        "and a measurement unit in unit. Do not repeat the food name across fields. "
        "Ignore speech that is unrelated to cooking. Return the JSON schema exactly.\n\n"
        f"Transcript:\n{transcript[:16000]}\n\nFrame text:\n{chr(10).join(notes)[:10000]}"
    )
    answer = ollama_post(base_url, "/api/chat", {
        "model": RECIPE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "format": RECIPE_SCHEMA, "stream": False, "think": False, "keep_alive": 0,
        "options": {"temperature": 0},
    })
    try:
        data = json.loads(answer["message"]["content"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ExtractionError("Recipe model returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ExtractionError("Recipe model returned a non-object recipe")
    recipe = Recipe.from_llm_json(data, source)
    if not recipe.ingredients and not recipe.steps:
        raise ExtractionError("No recipe ingredients or steps could be extracted")
    return recipe


def extract(
    source: str, *, base_url: str = "http://localhost:11434",
    max_frames: int = 8, no_ocr: bool = False, whisper_model: str = WHISPER_MODEL,
) -> tuple[Recipe, str, list[str]]:
    if not 0 <= max_frames <= 24:
        raise ExtractionError("--max-frames must be between 0 and 24")
    with tempfile.TemporaryDirectory(prefix="reelrecipe-") as directory:
        work = Path(directory)
        path = get_video(source, work)
        require_tool("ffmpeg")
        duration, has_audio = video_info(path)
        transcript = transcribe(path, work, has_audio, whisper_model)
        notes = [] if no_ocr or max_frames == 0 else read_frames(
            path, work, duration, max_frames, base_url
        )
        return merge_recipe(transcript, notes, source, base_url), transcript, notes
