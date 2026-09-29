"""Core behavior and failure cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reelrecipe import cli, pipeline
from reelrecipe.formats import markdown, mealie, write_outputs
from reelrecipe.recipe import Recipe


@pytest.fixture
def recipe() -> Recipe:
    return Recipe.from_llm_json(
        {
            "title": "Tomato pasta",
            "ingredients": [
                {"name": "tomatoes", "quantity": "2", "unit": "cups", "note": "chopped"},
                {"name": "salt"},
            ],
            "steps": [{"text": "Simmer tomatoes.", "time_minutes": 10}],
            "servings": "2",
            "cook_time_minutes": 10,
        },
        "sample.mp4",
    )


def test_recipe_roundtrip(recipe: Recipe) -> None:
    assert Recipe.from_dict(recipe.to_dict()) == recipe
    assert recipe.ingredients[0].line() == "2 cups tomatoes (chopped)"


def test_model_fields_are_sanitized() -> None:
    recipe = Recipe.from_llm_json(
        {"title": "", "ingredients": "wrong", "steps": [None, {"text": "Mix"}],
         "cook_time_minutes": -2},
        "x",
    )
    assert recipe.title == "Untitled recipe"
    assert recipe.ingredients == []
    assert len(recipe.steps) == 1
    assert recipe.times.cook_minutes is None


def test_markdown_and_mealie(recipe: Recipe) -> None:
    assert "- 2 cups tomatoes (chopped)" in markdown(recipe)
    assert "1. Simmer tomatoes." in markdown(recipe)
    exported = mealie(recipe)
    assert exported["recipeIngredient"][0]["note"] == "2 cups tomatoes (chopped)"
    assert exported["recipeInstructions"][0]["text"] == "Simmer tomatoes."
    assert exported["cookTime"] == "PT10M"


def test_write_outputs(tmp_path: Path, recipe: Recipe) -> None:
    paths = write_outputs(recipe, tmp_path / "out", "spoken", ["visible"])
    assert len(paths) == 4
    assert json.loads(paths[0].read_text())["title"] == "Tomato pasta"
    assert json.loads(paths[3].read_text())["frame_text"] == ["visible"]


@pytest.mark.parametrize("duration,count", [(1, 1), (60, 5), (600, 8)])
def test_sample_times(duration: float, count: int) -> None:
    samples = pipeline.sample_times(duration, 8)
    assert len(samples) == count
    assert all(0 < second < duration for second in samples)


def test_clean_ocr_discards_repetition() -> None:
    assert pipeline.clean_ocr("```markdown\n2 eggs\n2 eggs\nSalt\n```") == "2 eggs\nSalt"


def test_merge_recipe_uses_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_post(base_url: str, endpoint: str, payload: dict) -> dict:
        captured.update(payload)
        return {"message": {"content": json.dumps({
            "title": "Soup", "ingredients": [{"name": "water"}],
            "steps": [{"text": "Boil water."}],
        })}}

    monkeypatch.setattr(pipeline, "ollama_post", fake_post)
    recipe = pipeline.merge_recipe("Boil water", [], "x.mp4", "http://localhost:11434")
    assert recipe.title == "Soup"
    assert captured["format"] == pipeline.RECIPE_SCHEMA
    assert captured["think"] is False


def test_merge_rejects_empty_evidence() -> None:
    with pytest.raises(pipeline.ExtractionError, match="No speech"):
        pipeline.merge_recipe("", [], "x.mp4", "http://localhost:11434")


def test_extract_rejects_missing_file() -> None:
    with pytest.raises(pipeline.ExtractionError, match="does not exist"):
        pipeline.extract("/missing/cooking.mp4", no_ocr=True)


def test_url_download_uses_installed_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline.importlib.util, "find_spec", lambda name: object())

    def fake_run(*args: str) -> None:
        assert args[0:3] == (pipeline.sys.executable, "-m", "yt_dlp")
        (tmp_path / "download.mp4").write_bytes(b"video")

    monkeypatch.setattr(pipeline, "run", fake_run)
    assert pipeline.get_video("https://example.com/cooking", tmp_path).name == "download.mp4"


def test_cli_render(tmp_path: Path, recipe: Recipe, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(recipe.to_dict()))
    assert cli.main(["render", str(path), "--format", "mealie"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "Tomato pasta"


def test_cli_missing_recipe(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["render", "/missing/recipe.json"]) == 1
    assert "does not exist" in capsys.readouterr().err
