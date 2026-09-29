"""Command line interface for local recipe extraction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reelrecipe.formats import markdown, mealie, write_outputs
from reelrecipe.pipeline import ExtractionError, extract
from reelrecipe.recipe import Recipe


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="reelrecipe", description="Turn a cooking video into a local recipe card."
    )
    sub = root.add_subparsers(dest="command", required=True)
    video = sub.add_parser("extract", help="Extract a recipe from a video")
    video.add_argument("source", help="Local video path or URL with yt-dlp installed")
    video.add_argument("--out-dir", type=Path, default=Path("recipe-output"))
    video.add_argument("--max-frames", type=int, default=8)
    video.add_argument("--no-ocr", action="store_true", help="Skip frame text extraction")
    video.add_argument("--whisper-model", default="mlx-community/whisper-small-mlx")
    video.add_argument("--ollama-url", default="http://localhost:11434")
    video.add_argument("--json", action="store_true", help="Print machine-readable result")
    render = sub.add_parser("render", help="Render an existing recipe JSON")
    render.add_argument("recipe", type=Path)
    render.add_argument("--format", choices=["markdown", "mealie", "json"], default="markdown")
    render.add_argument("--json", action="store_true", help="Print machine-readable result")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "extract":
            recipe, transcript, notes = extract(
                args.source, base_url=args.ollama_url,
                max_frames=args.max_frames, no_ocr=args.no_ocr,
                whisper_model=args.whisper_model,
            )
            paths = write_outputs(recipe, args.out_dir, transcript, notes)
            if args.json:
                print(json.dumps({"title": recipe.title, "files": [str(p) for p in paths]}))
            else:
                print(f"Extracted: {recipe.title}\nFiles: {args.out_dir}")
        else:
            if not args.recipe.is_file():
                raise ExtractionError(f"Recipe file does not exist: {args.recipe}")
            recipe = Recipe.from_dict(json.loads(args.recipe.read_text(encoding="utf-8")))
            if args.format == "mealie":
                result = mealie(recipe)
            elif args.format == "json" or args.json:
                result = recipe.to_dict()
            else:
                result = markdown(recipe)
            print(json.dumps(result, indent=2) if isinstance(result, dict) else result, end="\n")
        return 0
    except (ExtractionError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"reelrecipe: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
