"""The recipe data model shared by extraction, rendering and export."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Ingredient:
    name: str
    quantity: str | None = None
    unit: str | None = None
    note: str | None = None

    def line(self) -> str:
        parts = [p for p in (self.quantity, self.unit) if p]
        prefix = " ".join(parts)
        unit = (self.unit or "").casefold()
        name = self.name.casefold()
        repeated_name = unit in {name, name + "s", name + "es"}
        text = (prefix if repeated_name else f"{prefix} {self.name}").strip()
        if self.note:
            text = f"{text} ({self.note})"
        return text


@dataclass
class Step:
    text: str
    time_minutes: float | None = None


@dataclass
class Times:
    prep_minutes: float | None = None
    cook_minutes: float | None = None
    total_minutes: float | None = None


@dataclass
class Recipe:
    title: str
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    servings: str | None = None
    times: Times = field(default_factory=Times)
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_llm_json(cls, data: dict, source: str) -> Recipe:
        """Build a Recipe from the JSON object returned by the merge model.

        Tolerant of missing or oddly typed fields since the model output is
        never fully trusted, even with a JSON schema in play.
        """
        title = str(data.get("title") or "Untitled recipe").strip()
        raw_ingredients = data.get("ingredients")
        raw_steps = data.get("steps")
        ingredients = [
            Ingredient(
                name=str(item.get("name", "")).strip() or "unknown ingredient",
                quantity=_clean_str(item.get("quantity")),
                unit=_clean_str(item.get("unit")),
                note=_clean_str(item.get("note")),
            )
            for item in (raw_ingredients if isinstance(raw_ingredients, list) else [])
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        steps = [
            Step(
                text=str(item.get("text", "")).strip(),
                time_minutes=_clean_float(item.get("time_minutes")),
            )
            for item in (raw_steps if isinstance(raw_steps, list) else [])
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        times = Times(
            prep_minutes=_clean_float(data.get("prep_time_minutes")),
            cook_minutes=_clean_float(data.get("cook_time_minutes")),
            total_minutes=_clean_float(data.get("total_time_minutes")),
        )
        return cls(
            title=title,
            ingredients=ingredients,
            steps=steps,
            servings=_clean_str(data.get("servings")),
            times=times,
            source=source,
        )

    @classmethod
    def from_dict(cls, data: dict) -> Recipe:
        if not isinstance(data, dict):
            raise ValueError("Recipe JSON must be an object")
        times = data.get("times") or {}
        if not isinstance(times, dict):
            times = {}
        flattened = {
            **data,
            "prep_time_minutes": times.get("prep_minutes"),
            "cook_time_minutes": times.get("cook_minutes"),
            "total_time_minutes": times.get("total_minutes"),
        }
        return cls.from_llm_json(flattened, str(data.get("source") or ""))


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
        return number if 0 <= number < 100000 else None
    except (TypeError, ValueError):
        return None
