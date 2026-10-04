"""Registry classification of declared gems, rates by model, language and context, contrasts and figures."""

import json
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

import numpy as np

from . import extract
from .experiment import MODELS, load_rows
from .registry import Registry
from .tasks import LANGS, Task

SEED = 2026
RESAMPLES = 10000
LABELS = {
    "openai/gpt-4o-mini": "GPT-4o mini",
    "google/gemini-2.5-flash-lite": "Gemini 2.5 Flash-Lite",
    "deepseek/deepseek-chat-v3.1": "DeepSeek V3.1",
    "meta-llama/llama-3.3-70b-instruct": "Llama 3.3 70B",
    "qwen/qwen3-coder-30b-a3b-instruct": "Qwen3 Coder 30B",
    "mistralai/mistral-small-3.2-24b-instruct": "Mistral Small 3.2",
    "google/gemma-3-12b-it": "Gemma 3 12B",
    "meta-llama/llama-3.1-8b-instruct": "Llama 3.1 8B",
}


def check_registry(results: Path) -> None:
    registry = Registry(results / "registry.json")
    names = set()
    for row in load_rows(results / "replies.jsonl"):
        for name in extract.parse(row["text"]).declared:
            if extract.valid(name):
                names.add(name)
                names.update(extract.variants(name))
    for name in sorted(names):
        registry.status(name)
    registry.save()


def classify(name: str, cache: dict) -> str:
    """exists, invented, near_miss, malformed or unknown."""
    if not extract.valid(name):
        return "malformed"
    status = cache[name]["status"]
    if status != "absent":
        return status
    if any(cache.get(v, {}).get("status") == "exists" for v in extract.variants(name)):
        return "near_miss"
    return "invented"


def label_rows(rows: list[dict], cache: dict) -> list[dict]:
    out = []
    for r in rows:
        deps = extract.parse(r["text"])
        classes = {name: classify(name, cache) for name in deps.declared}
        out.append(
            {
                **{k: r[k] for k in ("model", "task", "lang", "sample", "finish")},
                "classes": classes,
                "external": list(deps.external),
                "required": list(deps.required),
            }
        )
    return out


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, k) for k in range(min(b, c) + 1)) / 2**n)


def holm(pvalues: dict) -> dict:
    order = sorted(pvalues, key=pvalues.get)
    adjusted, running = {}, 0.0
    for rank, key in enumerate(order):
        running = max(running, min(1.0, (len(order) - rank) * pvalues[key]))
        adjusted[key] = running
    return adjusted


def interval(values: np.ndarray) -> list[float]:
    return [float(v) for v in np.percentile(values, [2.5, 97.5])]


def outcome_matrix(labelled: list[dict], tasks: list[Task]) -> dict:
    """invented[model][lang] = 0/1 vector over tasks (sample 0)."""
    index = {t.id: i for i, t in enumerate(tasks)}
    out = {m: {lang: np.full(len(tasks), np.nan) for lang in LANGS} for m in MODELS}
    for r in labelled:
        if r["sample"] == 0:
            out[r["model"]][r["lang"]][index[r["task"]]] = float("invented" in r["classes"].values())
    return out


def gap(values: np.ndarray, context: np.ndarray) -> float:
    return float(values[context == "ukraine"].mean() - values[context == "global"].mean())


def gap_interval(values: np.ndarray, context: np.ndarray, boots: np.ndarray) -> list[float]:
    return interval(np.array([gap(values[b], context[b]) for b in boots]))


def rates(labelled: list[dict], tasks: list[Task]) -> dict:
    rng = np.random.default_rng(SEED)
    matrix = outcome_matrix(labelled, tasks)
    context = np.array([t.context for t in tasks])
    category = np.array([t.category for t in tasks])
    boots = rng.integers(0, len(tasks), (RESAMPLES, len(tasks)))
    res = {"models": {}}
    pvalues = {}
    for m in MODELS:
        en, uk = matrix[m]["en"], matrix[m]["uk"]
        cell = {lang: float(v.mean()) for lang, v in (("en", en), ("uk", uk))}
        for lang, v in (("en", en), ("uk", uk)):
            for ctx in ("global", "ukraine"):
                cell[f"{lang}|{ctx}"] = float(v[context == ctx].mean())
        d = uk - en
        gained, lost = int((d > 0).sum()), int((d < 0).sum())
        pvalues[m] = mcnemar(gained, lost)
        both = (en + uk) / 2
        res["models"][m] = {
            "rate": cell,
            "uk_minus_en": {
                "value": float(d.mean()),
                "ci": interval(d[boots].mean(axis=1)),
                "uk_only": gained,
                "en_only": lost,
                "p": pvalues[m],
            },
            "ukraine_minus_global": {"value": gap(both, context), "ci": gap_interval(both, context, boots[:2000])},
        }
    for m, p in holm(pvalues).items():
        res["models"][m]["uk_minus_en"]["p_holm"] = p
    stack = {lang: np.vstack([matrix[m][lang] for m in MODELS]) for lang in LANGS}
    diff = (stack["uk"] - stack["en"]).mean(axis=0)
    both = ((stack["uk"] + stack["en"]) / 2).mean(axis=0)
    res["pooled"] = {
        "en": float(stack["en"].mean()),
        "uk": float(stack["uk"].mean()),
        "uk_minus_en": {"value": float(diff.mean()), "ci": interval(diff[boots].mean(axis=1))},
        "ukraine_minus_global": {"value": gap(both, context), "ci": gap_interval(both, context, boots)},
        "interaction": {"value": gap(diff, context), "ci": gap_interval(diff, context, boots)},
        "by_context": {
            ctx: {lang: float(stack[lang][:, context == ctx].mean()) for lang in LANGS} for ctx in ("global", "ukraine")
        },
        "by_category": {
            c: {ctx: float(both[(category == c) & (context == ctx)].mean()) for ctx in ("global", "ukraine")}
            for c in sorted(set(category))
        },
    }
    return res


def names(labelled: list[dict]) -> dict:
    by_model = defaultdict(Counter)
    for r in labelled:
        if r["sample"] != 0:
            continue
        for cls in r["classes"].values():
            by_model[r["model"]][cls] += 1
        if not r["classes"]:
            by_model[r["model"]]["no_dependency"] += 1
        by_model[r["model"]]["replies"] += 1
        by_model[r["model"]]["truncated"] += r["finish"] == "length"
        by_model[r["model"]]["external"] += len(r["external"])
    return {m: dict(by_model[m]) for m in MODELS}


def recurrence(labelled: list[dict]) -> dict:
    groups = defaultdict(list)
    for r in labelled:
        groups[(r["model"], r["task"], r["lang"])].append(r)
    repeated = {k: v for k, v in groups.items() if len(v) > 1}
    total, again = 0, 0
    for replies in repeated.values():
        per_sample = [{n for n, c in r["classes"].items() if c == "invented"} for r in replies]
        for i, current in enumerate(per_sample):
            others = set().union(*(s for j, s in enumerate(per_sample) if j != i))
            total += len(current)
            again += len(current & others)
    models_per_name = defaultdict(set)
    for r in labelled:
        for n, c in r["classes"].items():
            if c == "invented":
                models_per_name[n].add(r["model"])
    shared = {n: sorted(ms) for n, ms in models_per_name.items() if len(ms) >= 2}
    return {
        "invented_in_repeat_groups": total,
        "seen_again": again,
        "share_seen_again": again / total if total else None,
        "distinct_invented": len(models_per_name),
        "proposed_by_two_or_more_models": len(shared),
        "shared_examples": dict(sorted(shared.items(), key=lambda kv: -len(kv[1]))[:30]),
    }


def figure(res: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    models = sorted(MODELS, key=lambda m: res["models"][m]["rate"]["en"] + res["models"][m]["rate"]["uk"])
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    y = np.arange(len(models))
    for ax, ctx, title in ((axes[0], "global", "Global services"), (axes[1], "ukraine", "Ukrainian services")):
        en = [100 * res["models"][m]["rate"][f"en|{ctx}"] for m in models]
        uk = [100 * res["models"][m]["rate"][f"uk|{ctx}"] for m in models]
        ax.barh(y - 0.2, en, 0.4, label="English request", color="#1f4e79")
        ax.barh(y + 0.2, uk, 0.4, label="Ukrainian request", color="#d98c1f")
        ax.set_title(title, fontsize=12)
        ax.set_xlabel("Replies with an invented gem, %", fontsize=11)
        ax.tick_params(labelsize=10)
        ax.grid(axis="x", alpha=0.3)
    axes[0].set_yticks(y, [LABELS[m] for m in models])
    axes[1].legend(fontsize=10, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def main(tasks: list[Task], results: Path, figures: Path) -> None:
    cache = json.loads((results / "registry.json").read_text())
    labelled = label_rows(load_rows(results / "replies.jsonl"), cache)
    with (results / "labelled.jsonl").open("w") as f:
        for r in labelled:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    res = rates(labelled, tasks)
    summary = {"rates": res, "names": names(labelled), "recurrence": recurrence(labelled)}
    (results / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    figures.mkdir(exist_ok=True)
    figure(res, figures / "invented_by_model.png")
