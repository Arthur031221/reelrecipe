"""Recipe card and Mealie export formats."""

from __future__ import annotations

import json
from pathlib import Path

from reelrecipe.recipe import Recipe


def markdown(recipe: Recipe) -> str:
    lines = [f"# {recipe.title}", ""]
    if recipe.source:
        lines.extend([f"Source: {recipe.source}", ""])
    if recipe.servings:
        lines.append(f"Servings: {recipe.servings}")
    for label, number in (
        ("Prep", recipe.times.prep_minutes),
        ("Cook", recipe.times.cook_minutes),
        ("Total", recipe.times.total_minutes),
    ):
        if number is not None:
            lines.append(f"{label}: {number:g} minutes")
    lines.extend(["", "## Ingredients", ""])
    lines.extend(f"- {ingredient.line()}" for ingredient in recipe.ingredients)
    if not recipe.ingredients:
        lines.append("No ingredients found.")
    lines.extend(["", "## Steps", ""])
    lines.extend(f"{index}. {step.text}" for index, step in enumerate(recipe.steps, 1))
    if not recipe.steps:
        lines.append("No steps found.")
    return "\n".join(lines) + "\n"


def mealie(recipe: Recipe) -> dict:
    """Return fields accepted by Mealie's recipe API and JSON import."""
    return {
        "name": recipe.title,
        "description": "Extracted from a cooking video. Review before cooking.",
        "recipeYield": recipe.servings or "",
        "prepTime": _duration(recipe.times.prep_minutes),
        "cookTime": _duration(recipe.times.cook_minutes),
        "totalTime": _duration(recipe.times.total_minutes),
        "recipeIngredient": [{"note": item.line()} for item in recipe.ingredients],
        "recipeInstructions": [{"text": step.text} for step in recipe.steps],
        "orgURL": recipe.source if recipe.source.startswith(("http://", "https://")) else "",
    }


def _duration(minutes: float | None) -> str | None:
    return f"PT{minutes:g}M" if minutes is not None else None


def write_outputs(recipe: Recipe, out_dir: Path, transcript: str, notes: list[str]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    content = {
        "recipe.json": json.dumps(recipe.to_dict(), indent=2, ensure_ascii=False) + "\n",
        "recipe.md": markdown(recipe),
        "mealie.json": json.dumps(mealie(recipe), indent=2, ensure_ascii=False) + "\n",
        "evidence.json": json.dumps(
            {"transcript": transcript, "frame_text": notes}, indent=2, ensure_ascii=False
        ) + "\n",
    }
    for name, body in content.items():
        (out_dir / name).write_text(body, encoding="utf-8")
    return [out_dir / name for name in content]
