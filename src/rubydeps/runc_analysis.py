"""Analysis of run C as fixed in PROTOCOL.md (2026-10-19): registry lookups, labels and the script experiment and
added-model contrasts."""

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from . import extract
from .analysis import RESAMPLES, SEED, classify, holm, interval, mcnemar
from .experiment import MODELS, load_rows
from .registry import Registry, fetch_index, read_index
from .runc import ADDED, ARMS
from .tasks import LANGS, Task

PRIMARY_EXCLUDED = {"msg-u14"}
ANY_ABSENT = ("invented", "near_miss", "malformed")


def check_registry(folder: Path) -> None:
    registry = Registry(folder / "registry.json")
    names = set()
    for r in load_rows(folder / "replies.jsonl"):
        for name in extract.parse(r["text"]).declared:
            if extract.valid(name):
                names.add(name)
    for name in sorted(names):
        registry.status(name)
    registry.save()
    index = folder / "rubygems_names.txt.gz"
    if not index.exists():
        fetch_index(index)


def label(rows: list[dict], cache: dict, keys: set[str]) -> list[dict]:
    out = []
    for r in rows:
        deps = extract.parse(r["text"])
        classes = {n: classify(n, cache, keys) for n in deps.declared}
        if "unknown" in classes.values():
            raise ValueError(f"unresolved registry status in {r['model']} {r['task']} {r['arm']} {r['sample']}")
        out.append({k: r[k] for k in ("part", "model", "task", "lang", "arm", "sample", "finish")}
                   | {"empty": not r["text"].strip(), "classes": classes})
    return out


def hit(r: dict, outcome: tuple[str, ...]) -> float:
    return float(any(c in outcome for c in r["classes"].values()))


def script_differences(labelled: list[dict], models: list[str], task_ids: list[str],
                       outcome: tuple[str, ...]) -> np.ndarray:
    """Per task: mean over the given models and their samples of (cyrillic - latin), equal model weights."""
    cell = defaultdict(list)
    for r in labelled:
        if r["part"] == "script" and r["model"] in models:
            cell[(r["task"], r["model"], r["sample"], r["arm"])] = hit(r, outcome)
    out = []
    for t in task_ids:
        per_model = []
        for m in models:
            samples = sorted({s for (tt, mm, s, _) in cell if tt == t and mm == m})
            if not samples:
                raise ValueError(f"no script replies for {m} {t}")
            per_model.append(np.mean([cell[(t, m, s, "cyrillic")] - cell[(t, m, s, "latin")] for s in samples]))
        out.append(np.mean(per_model))
    return np.array(out)


def estimate(d: np.ndarray, test: bool = False) -> dict:
    rng = np.random.default_rng(SEED)
    boots = rng.integers(0, len(d), (RESAMPLES, len(d)))
    res = {"tasks": int(len(d)), "value": float(d.mean()), "ci": interval(d[boots].mean(axis=1))}
    if test:
        signs = rng.choice([-1.0, 1.0], (RESAMPLES, len(d)))
        observed = abs(d.mean())
        exceed = int((np.abs((signs * d).mean(axis=1)) >= observed - 1e-12).sum())
        res["p_sign_flip"] = (1 + exceed) / (RESAMPLES + 1)
    return res


def arm_rates(labelled: list[dict], models: list[str], task_ids: set[str], outcome) -> dict:
    out = {}
    for arm in ARMS:
        v = [hit(r, outcome) for r in labelled
             if r["part"] == "script" and r["arm"] == arm and r["model"] in models and r["task"] in task_ids]
        out[arm] = {"replies": len(v), "rate": float(np.mean(v))}
    return out


def script(labelled: list[dict], tasks: list[Task], variant_ids: list[str]) -> dict:
    by_id = {t.id: t for t in tasks}
    original = list(MODELS)
    primary_ids = [t for t in variant_ids if t not in PRIMARY_EXCLUDED]
    ukraine_ids = [t for t in variant_ids if by_id[t].context == "ukraine"]
    res = {
        "primary": estimate(script_differences(labelled, original, primary_ids, ("invented",)), test=True)
        | {"rates": arm_rates(labelled, original, set(primary_ids), ("invented",))},
        "all_36": estimate(script_differences(labelled, original, variant_ids, ("invented",))),
        "ukraine_only": estimate(script_differences(labelled, original, [t for t in ukraine_ids
                                                                          if t not in PRIMARY_EXCLUDED],
                                                    ("invented",))),
        "any_absent": estimate(script_differences(labelled, original, primary_ids, ANY_ABSENT)),
        "per_model": {m: estimate(script_differences(labelled, [m], primary_ids, ("invented",)))
                      | {"rates": arm_rates(labelled, [m], set(primary_ids), ("invented",))} for m in original},
        "added_models": {m: estimate(script_differences(labelled, [m], primary_ids, ("invented",)))
                         | {"rates": arm_rates(labelled, [m], set(primary_ids), ("invented",))}
                         for m in ADDED if any(r["model"] == m and r["part"] == "script" for r in labelled)},
    }
    names = Counter()
    for r in labelled:
        if r["part"] == "script":
            names.update(n for n, c in r["classes"].items() if c == "invented")
    res["invented_names_for_blind_coding"] = sorted(names)
    return res


def added_main(labelled: list[dict], tasks: list[Task], models=tuple(ADDED)) -> dict:
    """Run B analyses 1 and 2 and the name classes for each added model (sample 0)."""
    context = {t.id: t.context for t in tasks}
    out, pvalues = {}, {}
    for m in models:
        rows = [r for r in labelled if r["part"] == "main" and r["model"] == m]
        if not rows:
            continue
        ids = sorted({r["task"] for r in rows})
        v = {lang: np.array([next(hit(r, ("invented",)) for r in rows if r["task"] == t and r["lang"] == lang)
                             for t in ids]) for lang in LANGS}
        d = v["uk"] - v["en"]
        rng = np.random.default_rng(SEED)
        boots = rng.integers(0, len(ids), (RESAMPLES, len(ids)))
        gained, lost = int((d > 0).sum()), int((d < 0).sum())
        pvalues[m] = mcnemar(gained, lost)
        classes = Counter(c for r in rows for c in r["classes"].values())
        out[m] = {
            "tasks": len(ids),
            "rate": {lang: float(v[lang].mean()) for lang in LANGS}
            | {f"{lang}|{ctx}": float(np.mean([x for x, t in zip(v[lang], ids, strict=True) if context[t] == ctx]))
               for lang in LANGS for ctx in ("global", "ukraine") if any(context[t] == ctx for t in ids)},
            "uk_minus_en": {"value": float(d.mean()), "ci": interval(d[boots].mean(axis=1)), "uk_only": gained,
                            "en_only": lost, "p": pvalues[m]},
            "names": dict(classes),
            "no_dependency": sum(not r["classes"] for r in rows),
            "truncated": sum(r["finish"] == "length" for r in rows),
            "empty": sum(r["empty"] for r in rows),
        }
    for m, p in holm(pvalues).items():
        out[m]["uk_minus_en"]["p_holm"] = p
    return out


def duplicates(rows: list[dict]) -> dict:
    """Script replies that are textually identical between arms or between the two samples of an arm."""
    by = defaultdict(dict)
    for r in rows:
        if r["part"] == "script":
            by[(r["model"], r["task"])][(r["arm"], r["sample"])] = r["text"]
    out = Counter()
    for (m, _), g in by.items():
        texts = list(g.values())
        out[m] += len(texts) - len(set(texts))
    return dict(out)


def derived_by_arm(labelled: list[dict], path: Path) -> dict:
    """Invented-name occurrences in script replies of the eight run-B models by arm and by the class coded without
    arm labels (derived from a switched name, other, ambiguous)."""
    import csv

    with path.open() as f:
        classes = {r["name"]: r["class"] for r in csv.DictReader(f)}
    out = {arm: Counter() for arm in ARMS}
    for r in labelled:
        if r["part"] == "script" and r["model"] in MODELS:
            for n, c in r["classes"].items():
                if c == "invented":
                    out[r["arm"]][classes[n]] += 1
    return {arm: dict(v) for arm, v in out.items()}


def versus_run_b(labelled: list[dict], run_b: list[dict], task_ids: list[str]) -> dict:
    """Descriptive: run B English and Ukrainian rates (sample 0) and run C arm rates on the same tasks and models."""
    ids = set(task_ids)
    out = {}
    for lang in LANGS:
        v = [hit(r, ("invented",)) for r in run_b if r["sample"] == 0 and r["lang"] == lang and r["task"] in ids]
        out[f"run_b_{lang}"] = {"replies": len(v), "rate": float(np.mean(v))}
    out |= {f"run_c_{k}": v for k, v in arm_rates(labelled, list(MODELS), ids, ("invented",)).items()}
    return out


def main(tasks: list[Task], root: Path) -> None:
    folder = root / "results" / "run-c"
    rows = load_rows(folder / "replies.jsonl")
    cache = json.loads((folder / "registry.json").read_text())
    keys = {extract.key(n) for n in read_index(folder / "rubygems_names.txt.gz")}
    labelled = label(rows, cache, keys)
    with (folder / "labelled.jsonl").open("w") as f:
        for r in labelled:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (root / "data" / "script_tasks.jsonl").open() as f:
        variant_ids = [json.loads(line)["id"] for line in f]
    summary = {
        "requests": len(rows),
        "cost_usd": sum(r.get("cost", 0.0) for r in rows),
        "script": script(labelled, tasks, variant_ids),
        "added_main": added_main(labelled, tasks),
        "duplicates": duplicates(rows),
        "finish": dict(Counter((r["model"], r["finish"]) for r in rows).items()),
    }
    summary["finish"] = {f"{m}|{f}": n for (m, f), n in summary["finish"].items()}
    summary["script"]["derived_by_arm"] = derived_by_arm(labelled, root / "data" / "script_run_c_invented_names.csv")
    run_b = [json.loads(line) for line in (root / "results" / "labelled.jsonl").open()]
    primary_ids = [t for t in variant_ids if t not in PRIMARY_EXCLUDED]
    summary["script"]["versus_run_b"] = versus_run_b(labelled, run_b, primary_ids)
    broken = [r["model"] for r in rows if not r["text"].strip() or r["finish"] == "error"]
    summary["empty_or_error"] = dict(Counter(broken))
    (folder / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
