"""Analysis of run D as fixed in PROTOCOL.md (2026-10-20): registry lookups, labels, the script contrast of Claude
Sonnet 5.5 and the run B analyses 1 and 2 for Claude Sonnet 5.5 and DeepSeek V4 Pro over all 200 tasks."""

import json
from collections import Counter
from pathlib import Path

from . import extract
from .experiment import load_rows
from .registry import Registry, fetch_index, read_index
from .runc_analysis import ANY_ABSENT, PRIMARY_EXCLUDED, added_main, arm_rates, estimate, label, script_differences
from .rund import DEEPSEEK, SONNET
from .tasks import Task


def replies(root: Path) -> tuple[list[dict], list[dict]]:
    """Run D replies and the run C main-run replies of DeepSeek V4 Pro (Ukrainian-service tasks)."""
    run_d = load_rows(root / "results" / "run-d" / "replies.jsonl")
    run_c = [r for r in load_rows(root / "results" / "run-c" / "replies.jsonl")
             if r["part"] == "main" and r["model"] == DEEPSEEK]
    return run_d, run_c


def check_registry(root: Path) -> None:
    folder = root / "results" / "run-d"
    registry = Registry(folder / "registry.json")
    names = set()
    for rows in replies(root):
        for r in rows:
            names.update(n for n in extract.parse(r["text"]).declared if extract.valid(n))
    for name in sorted(names):
        registry.status(name)
    registry.save()
    index = folder / "rubygems_names.txt.gz"
    if not index.exists():
        fetch_index(index)


def status_changes(old: list[dict], new: list[dict]) -> list[list[str]]:
    """Names of the run C DeepSeek V4 Pro replies whose class differs between the run C and run D lookups."""
    before = {n: c for r in old for n, c in r["classes"].items()}
    after = {n: c for r in new for n, c in r["classes"].items()}
    return sorted([n, before[n], after[n]] for n in after if before[n] != after[n])


def main(tasks: list[Task], root: Path) -> None:
    folder = root / "results" / "run-d"
    run_d, run_c = replies(root)
    cache = json.loads((folder / "registry.json").read_text())
    keys = {extract.key(n) for n in read_index(folder / "rubygems_names.txt.gz")}
    labelled = label(run_d, cache, keys)
    relabelled = label(run_c, cache, keys)
    with (folder / "labelled.jsonl").open("w") as f:
        for r in labelled:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (root / "data" / "script_tasks.jsonl").open() as f:
        primary_ids = [i for i in (json.loads(line)["id"] for line in f) if i not in PRIMARY_EXCLUDED]
    old = [r for r in load_rows(root / "results" / "run-c" / "labelled.jsonl")
           if r["part"] == "main" and r["model"] == DEEPSEEK]
    summary = {
        "requests": len(run_d),
        "cost_usd": sum(r.get("cost", 0.0) for r in run_d),
        "script_sonnet": estimate(script_differences(labelled, [SONNET], primary_ids, ("invented",)))
        | {"rates": arm_rates(labelled, [SONNET], set(primary_ids), ("invented",)),
           "any_absent": estimate(script_differences(labelled, [SONNET], primary_ids, ANY_ABSENT))},
        "main": added_main(labelled + relabelled, tasks, (SONNET, DEEPSEEK)),
        "deepseek_run_c_status_changes": status_changes(old, relabelled),
        "finish": {f"{m}|{f}": n for (m, f), n in Counter((r["model"], r["finish"]) for r in run_d).items()},
        "empty_or_error": dict(Counter(r["model"] for r in run_d if not r["text"].strip() or r["finish"] == "error")),
        "reasoning_tokens_mean": {m: sum(r.get("reasoning_tokens", 0) for r in run_d if r["model"] == m)
                                  / max(1, sum(r["model"] == m for r in run_d)) for m in (SONNET, DEEPSEEK)},
    }
    (folder / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
