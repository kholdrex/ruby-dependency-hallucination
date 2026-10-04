"""Coding tasks with parallel English and Ukrainian wording."""

import json
import random
from dataclasses import dataclass
from pathlib import Path

LANGS = ("en", "uk")


@dataclass(frozen=True)
class Task:
    id: str
    category: str
    context: str
    text: dict[str, str]


def load(path: Path) -> list[Task]:
    with path.open() as f:
        rows = [json.loads(line) for line in f]
    return [Task(r["id"], r["category"], r["context"], {lang: r[lang] for lang in LANGS}) for r in rows]


def repeat_subset(tasks: list[Task], per_cell: int, seed: int) -> list[Task]:
    """A fixed number of tasks from every category × context cell, drawn before any reply is seen."""
    rng = random.Random(seed)
    cells: dict[tuple[str, str], list[Task]] = {}
    for t in tasks:
        cells.setdefault((t.category, t.context), []).append(t)
    chosen = [t for key in sorted(cells) for t in rng.sample(cells[key], per_cell)]
    return sorted(chosen, key=lambda t: t.id)
