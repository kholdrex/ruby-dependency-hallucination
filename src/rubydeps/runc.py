"""Run C (protocol of 19 October 2026): the script experiment, in which the Ukrainian wording of the name-switch
tasks names the service in Cyrillic (as in the task set) or in Latin script, and the main run of two current models."""

import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import prompts
from .client import OpenRouter
from .experiment import MODELS, load_rows
from .tasks import LANGS, Task

MAX_TOKENS = 16384
WORKERS = 8
TEMPERATURE = 0.7
ARMS = ("cyrillic", "latin")
SCRIPT_SAMPLES = (10, 11)
PILOT_SAMPLE = 99
SCHEDULE_SEED = 2026
BUDGET_STOP = 17.0
ADDED = {
    "anthropic/claude-sonnet-5.5": {"provider": "anthropic", "temperature": None, "seed": False},
    "deepseek/deepseek-v4-pro": {"provider": "gmicloud/fp8", "temperature": TEMPERATURE, "seed": True},
}


class BudgetExceeded(RuntimeError):
    pass


def settings(model: str) -> dict:
    if model in ADDED:
        return ADDED[model]
    return {"provider": MODELS[model], "temperature": TEMPERATURE, "seed": True}


def script_tasks(tasks: list[Task], path: Path) -> dict[str, dict[str, Task]]:
    """For every name-switch task, the Ukrainian wording with the name in Cyrillic (task set) and in Latin script."""
    by_id = {t.id: t for t in tasks}
    out = {}
    with path.open() as f:
        for line in f:
            r = json.loads(line)
            t = by_id[r["id"]]
            out[t.id] = {
                "cyrillic": t,
                "latin": Task(t.id, t.category, t.context, {"en": t.text["en"], "uk": r["uk_latin"]}),
            }
    return out


def jobs_script(models: list[str], variants: dict, pilot: bool = False) -> list[tuple]:
    out = []
    for m in models:
        samples = (PILOT_SAMPLE,) if pilot else ((10,) if m in ADDED else SCRIPT_SAMPLES)
        for arms in variants.values():
            for arm in ARMS:
                for s in samples:
                    out.append(("script", m, arms[arm], "uk", arm, s))
    return out


def jobs_main(models: list[str], tasks: list[Task], pilot: bool = False) -> list[tuple]:
    sample = PILOT_SAMPLE if pilot else 0
    return [("main", m, t, lang, "original", sample) for m in models if m in ADDED for t in tasks for lang in LANGS]


def schedule(jobs: list[tuple]) -> list[tuple]:
    """Reproducible random order, so that time and provider drift do not line up with arms or models."""
    out = sorted(jobs, key=lambda j: (j[0], j[1], j[2].id, j[3], j[4], j[5]))
    random.Random(SCHEDULE_SEED).shuffle(out)
    return out


def key(row: dict) -> tuple:
    return row["part"], row["model"], row["task"], row["lang"], row["arm"], row["sample"]


def spent(paths: list[Path]) -> float:
    return sum(r.get("cost", 0.0) for p in paths for r in load_rows(p))


def run(jobs: list[tuple], path: Path, ledger: list[Path]) -> None:
    """Send the jobs not yet stored; a stored reply must have the same prompt. Stops when the recorded cost of all
    run C files reaches BUDGET_STOP."""
    stored = {key(r): r["prompt"] for r in load_rows(path)}
    todo = []
    for j in schedule(jobs):
        prompt = prompts.messages(j[2], j[3])[0]["content"]
        k = (j[0], j[1], j[2].id, j[3], j[4], j[5])
        if k in stored:
            if stored[k] != prompt:
                raise ValueError(f"stored reply for {k} has a different prompt")
            continue
        todo.append(j)
    client = OpenRouter()
    lock = threading.Lock()
    total = [spent(ledger)]

    def call(job):
        part, model, task, lang, arm, sample = job
        with lock:
            if total[0] >= BUDGET_STOP:
                raise BudgetExceeded(f"recorded cost {total[0]:.2f} USD")
        cfg = settings(model)
        messages = prompts.messages(task, lang)
        reply = client.chat(model, cfg["provider"], messages, cfg["temperature"], MAX_TOKENS,
                            seed=sample if cfg["seed"] else None)
        row = {"part": part, "model": model, "task": task.id, "lang": lang, "arm": arm, "sample": sample,
               "max_tokens": MAX_TOKENS, "temperature": cfg["temperature"], "seed": sample if cfg["seed"] else None,
               "prompt": messages[0]["content"]}
        row |= reply.__dict__
        with lock:
            total[0] += reply.cost
            with path.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(call, todo))
