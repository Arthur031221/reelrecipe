# reelrecipe

Turn a cooking video into a recipe card on an Apple Silicon Mac. A synthetic 84-second demo produced four ingredient lines and five steps in a local run.[^sample] Ingredient recall on a licensed video benchmark is pending.

[![CI](https://github.com/Arthur031221/reelrecipe/actions/workflows/ci.yml/badge.svg)](https://github.com/Arthur031221/reelrecipe/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](CHANGELOG.md)

![Terminal demo](demo/demo.gif)

## Why

Cooking videos hide amounts in speech or on screen. Replaying a clip to find one measurement is slow. `reelrecipe` saves the spoken transcript, sampled frame text, an editable recipe, a Markdown card, and a Mealie-shaped JSON file. The models run locally after their weights have been downloaded.

## Install

Requires an Apple Silicon Mac, Python 3.12 or newer, FFmpeg, Ollama, and [uv](https://docs.astral.sh/uv/). Install the tools and models once:

```sh
brew install ffmpeg ollama uv
ollama pull glm-ocr:q8_0
ollama pull qwen3:4b
git clone https://github.com/Arthur031221/reelrecipe.git
cd reelrecipe
uv tool install .
```

Start the Ollama service with the Ollama app or `ollama serve`. The first extraction also downloads `mlx-community/whisper-small-mlx` from Hugging Face. After that download, local file extraction does not need a cloud account.

## Quick start

Render the included sample recipe immediately:

```sh
reelrecipe render demo/sample-recipe.json
```

Run the full local extraction on the included synthetic cooking video:

```sh
reelrecipe extract demo/sample.mp4 --out-dir recipe-output
cat recipe-output/recipe.md
```

The output directory contains `recipe.json`, `recipe.md`, `mealie.json`, and `evidence.json`. Read the evidence file when checking an amount or step. Edit `recipe.json` and rerender it with `reelrecipe render recipe-output/recipe.json` or `reelrecipe render recipe-output/recipe.json --format mealie`.

## How it works

FFmpeg reads the video and extracts audio and sampled frames. MLX Whisper transcribes speech. GLM-OCR reads visible text in the sampled frames through a local Ollama server. Qwen3 merges that evidence into a constrained recipe JSON shape. Only one Ollama model is kept loaded at a time. The recipe card and Mealie payload are deterministic exports of the saved JSON.

The Mealie file uses the recipe fields in [Mealie's recipe type](https://github.com/mealie-recipes/mealie/blob/mealie-next/frontend/app/lib/api/types/recipe.ts), including `recipeIngredient` and `recipeInstructions`. Ingredient text stays in each ingredient's `note` field so the exporter does not guess Mealie food or unit IDs. This is a payload for a Mealie API workflow, not a direct upload command.

## Comparison

| Project | Video extraction | Local use | Recipe manager integration |
| --- | --- | --- | --- |
| [Mealie](https://docs.mealie.io/) | Website recipe import, not video transcription | Self-hosted | Full manager |
| [Pick-a-Recipe](https://github.com/pickeld/pick-a-recipe) | Video URLs, speech, and frames | Supports local Whisper and Ollama | Direct Mealie and Tandoor upload |
| reelrecipe | Local files first, optional URLs | Apple Silicon CLI with local models | Mealie-shaped JSON export |

Pick-a-Recipe is a better fit when you want a web interface and direct upload. Reelrecipe is a small command for extracting and reviewing files without a login or running a recipe manager.

## Commands

```text
reelrecipe extract SOURCE [--out-dir DIR] [--max-frames N] [--no-ocr]
                          [--whisper-model REPO] [--ollama-url URL] [--json]
reelrecipe render RECIPE_JSON [--format markdown|mealie|json] [--json]
reelrecipe --help
reelrecipe extract --help
reelrecipe render --help
```

`SOURCE` is a local video path or an HTTP URL. URL support requires `uv tool install '.[url]'` and uses yt-dlp. Download only when the platform terms and your rights permit it. `--max-frames` accepts 0 to 24, with 8 by default. `--no-ocr` skips frame reading. `--json` on `extract` prints the output file paths. On `render`, it prints the recipe JSON. Videos longer than 120 minutes are rejected.

## Limits and FAQ

- Review the card before cooking. Speech recognition and frame OCR can miss amounts or invent words. The sample run misheard one short step.
- The CLI does not infer unseen ingredients, nutrition, allergens, or food safety. It does not upload directly to Mealie.
- A video with no spoken or readable recipe evidence returns an error. Silent videos can still work when ingredient text is visible.
- OCR samples frames rather than reading every frame. Increase `--max-frames` for videos with brief ingredient overlays.
- Video and model files are kept out of Git. The sample video is synthetic. The recipe quality benchmark on ten licensed cooking videos remains to be measured.

## Related projects

- [receiptwise](https://github.com/Arthur031221/receiptwise): Same local extraction shape, structured output from a real-world photo instead of a video.
- [snipmd](https://github.com/Arthur031221/snipmd): A different OCR use, equations instead of on-screen ingredient text, both run locally.
- [labexplain](https://github.com/Arthur031221/labexplain): Another tool that turns a real document into structured, checkable local output.

## Development

```sh
uv sync --group dev --locked
uv run --no-sync ruff check .
uv run --no-sync pytest -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed. Copyright 2026 Arthur.

[^sample]: One run on 2026-09-30 on an M5 MacBook Air. Input: `demo/sample.mp4`, an 84-second synthetic card with spoken instructions. Command: `reelrecipe extract demo/sample.mp4 --max-frames 1`. Counted entries in the output `ingredients` and `steps` arrays. The sample is a smoke test, not an accuracy benchmark.
