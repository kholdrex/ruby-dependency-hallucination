"""Registry classification of declared gems, rates by model, language and context, contrasts and figures."""

import json
import re
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

import numpy as np

from . import extract
from .experiment import MODELS, load_rows
from .registry import Registry, fetch_index, read_index
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
    """Look up every declared name and its original-rule variants; save the full name index once."""
    registry = Registry(results / "registry.json")
    names = set()
    for row in load_rows(results / "replies.jsonl"):
        for name in extract.parse(row["text"]).declared:
            if extract.valid(name):
                names.add(name)
                names.update(extract.original_variants(name))
    for name in sorted(names):
        registry.status(name)
    registry.save()
    index = results / "rubygems_names.txt.gz"
    if not index.exists():
        fetch_index(index)


def classify(name: str, cache: dict, keys: set[str], rule: str = "final") -> str:
    """exists, invented, near_miss, malformed or unknown.

    final rule: an absent name is a near miss when some published gem has the same name up to letter case, hyphens
    and underscores; original rule (first protocol version): when its case or wholesale hyphen/underscore variant
    exists.
    """
    if not extract.valid(name):
        return "malformed"
    status = cache.get(name, {}).get("status", "unknown")
    if status != "absent":
        return status
    if rule == "final":
        near = extract.key(name) in keys
    else:
        statuses = [cache.get(v, {}).get("status", "unknown") for v in extract.original_variants(name)]
        if "exists" not in statuses and "unknown" in statuses:
            return "unknown"
        near = "exists" in statuses
    return "near_miss" if near else "invented"


def label_rows(rows: list[dict], cache: dict, keys: set[str], rule: str = "final") -> list[dict]:
    out = []
    for r in rows:
        deps = extract.parse(r["text"])
        classes = {name: classify(name, cache, keys, rule) for name in deps.declared}
        if "unknown" in classes.values():
            raise ValueError(f"unresolved registry status in {r['model']} {r['task']} {r['lang']} {r['sample']}")
        out.append(
            {
                "empty": not r["text"].strip(),
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


def outcome_matrix(labelled: list[dict], tasks: list[Task], outcome: tuple[str, ...] = ("invented",)) -> dict:
    """outcome[model][lang] = 0/1 vector over tasks (sample 0): a reply declares a name of one of the given classes."""
    index = {t.id: i for i, t in enumerate(tasks)}
    out = {m: {lang: np.full(len(tasks), np.nan) for lang in LANGS} for m in MODELS}
    seen = set()
    for r in labelled:
        if r["sample"] == 0:
            key = (r["model"], r["lang"], r["task"])
            if key in seen:
                raise ValueError(f"duplicate main-run record {key}")
            seen.add(key)
            out[r["model"]][r["lang"]][index[r["task"]]] = float(any(c in outcome for c in r["classes"].values()))
    missing = {f"{m}/{lang}": int(np.isnan(out[m][lang]).sum()) for m in MODELS for lang in LANGS
               if np.isnan(out[m][lang]).any()}
    if missing:
        raise ValueError(f"missing main-run records: {missing}")
    return out


def gap(values: np.ndarray, context: np.ndarray) -> float:
    return float(values[context == "ukraine"].mean() - values[context == "global"].mean())


def gap_interval(values: np.ndarray, context: np.ndarray, boots: np.ndarray) -> list[float]:
    return interval(np.array([gap(values[b], context[b]) for b in boots]))


def rates(labelled: list[dict], tasks: list[Task], outcome: tuple[str, ...] = ("invented",)) -> dict:
    rng = np.random.default_rng(SEED)
    matrix = outcome_matrix(labelled, tasks, outcome)
    context = np.array([t.context for t in tasks])
    category = np.array([t.category for t in tasks])
    boots = rng.integers(0, len(tasks), (RESAMPLES, len(tasks)))
    res = {"models": {}}
    pvalues = {}
    for m in MODELS:
        en, uk = matrix[m]["en"], matrix[m]["uk"]
        cell, cell_ci = {}, {}
        for lang, v in (("en", en), ("uk", uk)):
            cell[lang] = float(v.mean())
            cell_ci[lang] = interval(v[boots].mean(axis=1))
            for ctx in ("global", "ukraine"):
                sel = v[context == ctx]
                cell[f"{lang}|{ctx}"] = float(sel.mean())
                cell_ci[f"{lang}|{ctx}"] = interval(sel[rng.integers(0, len(sel), (RESAMPLES, len(sel)))].mean(axis=1))
        d = uk - en
        gained, lost = int((d > 0).sum()), int((d < 0).sum())
        pvalues[m] = mcnemar(gained, lost)
        both = (en + uk) / 2
        res["models"][m] = {
            "rate": cell,
            "rate_ci": cell_ci,
            "uk_minus_en": {
                "value": float(d.mean()),
                "ci": interval(d[boots].mean(axis=1)),
                "uk_only": gained,
                "en_only": lost,
                "p": pvalues[m],
            },
            "ukraine_minus_global": {"value": gap(both, context), "ci": gap_interval(both, context, boots)},
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
        by_model[r["model"]]["empty"] += r["empty"]
        by_model[r["model"]]["external"] += len(r["external"])
    return {m: dict(by_model[m]) for m in MODELS}


def recurrence(labelled: list[dict]) -> dict:
    """Two views on the repeat subset (three samples per model, task and language) and names shared by models."""
    groups = defaultdict(dict)
    for r in labelled:
        groups[(r["model"], r["task"], r["lang"])][r["sample"]] = {
            n for n, c in r["classes"].items() if c == "invented"
        }
    repeated = [g for g in groups.values() if len(g) > 1]
    distinct = Counter()
    for g in repeated:
        for name in set().union(*g.values()):
            distinct[sum(name in names for names in g.values())] += 1
    first, again = 0, 0
    for g in repeated:
        later = set().union(*(names for sample, names in g.items() if sample > 0))
        first += len(g.get(0, set()))
        again += len(g.get(0, set()) & later)
    models_per_name = defaultdict(set)
    for r in labelled:
        for n, c in r["classes"].items():
            if c == "invented":
                models_per_name[n].add(r["model"])
    shared = {n: sorted(ms) for n, ms in models_per_name.items() if len(ms) >= 2}
    total = sum(distinct.values())
    return {
        "distinct_in_repeat_groups": total,
        "distinct_in_two_or_more_samples": total - distinct[1],
        "share_distinct_recurring": (total - distinct[1]) / total if total else None,
        "first_sample_invented": first,
        "first_sample_seen_again": again,
        "share_first_seen_again": again / first if first else None,
        "distinct_invented": len(models_per_name),
        "proposed_by_two_or_more_models": len(shared),
        "shared_examples": dict(sorted(shared.items(), key=lambda kv: -len(kv[1]))[:30]),
    }


RAILS_COMPONENTS = {"active_support", "active_record", "active_model", "active_storage", "active_job", "action_cable",
                    "action_mailer", "action_mailbox", "action_text", "action_view", "action_pack", "action_controller"}
RAILS_TASK = re.compile(r"\bRails\b|ActiveRecord|Action Cable|Devise")


def secondary(labelled: list[dict], tasks: list[Task]) -> dict:
    """Exploratory outcome added after the main analysis: a reply declares any absent name (invented, near miss or
    malformed)."""
    res = rates(labelled, tasks, ("invented", "near_miss", "malformed"))
    return {"pooled": res["pooled"],
            "models": {m: {"rate": v["rate"], "uk_minus_en": v["uk_minus_en"]} for m, v in res["models"].items()}}


def descriptive(labelled: list[dict], tasks: list[Task]) -> dict:
    """Counts quoted in the paper that are not part of the planned analysis (main run)."""
    main = [r for r in labelled if r["sample"] == 0]
    invented = lambda r: "invented" in r["classes"].values()  # noqa: E731
    by_finish = {}
    for finish in ("stop", "length"):
        group = [r for r in main if r["finish"] == finish]
        by_finish[finish] = {"replies": len(group), "with_invented": sum(map(invented, group))}
    truncated = {m: {lang: sum(r["finish"] == "length" for r in main if r["model"] == m and r["lang"] == lang)
                     for lang in LANGS} for m in MODELS}
    near = Counter(n for r in main for n, c in r["classes"].items() if c == "near_miss")
    by_id = {t.id: t for t in tasks}
    local = [r for r in main if by_id[r["task"]].context == "ukraine" and by_id[r["task"]].category in ("payments", "commerce")]
    absent, absent_models = Counter(), defaultdict(set)
    for r in main:
        for n, c in r["classes"].items():
            if c in ("invented", "near_miss"):
                absent[(n, c)] += 1
                absent_models[(n, c)].add(r["model"])
    rails_models = {r["model"] for r in main for n, c in r["classes"].items() if c == "near_miss" and n in RAILS_COMPONENTS}
    return {
        "most_frequent_absent": [{"name": n, "class": c, "replies": k, "models": len(absent_models[(n, c)])}
                                 for (n, c), k in absent.most_common(12)],
        "rails_component_models": sorted(rails_models),
        "rails_tasks": sum(bool(RAILS_TASK.search(t.text["en"])) for t in tasks),
        "invented_by_finish": by_finish,
        "truncated_by_model": truncated,
        "rails_component_near_misses": {n: near[n] for n in sorted(RAILS_COMPONENTS) if near[n]},
        "ukrainian_payment_delivery": {
            "replies": len(local),
            "httparty": sum("httparty" in r["classes"] for r in local),
            "liqpay": sum("liqpay" in r["classes"] for r in local),
        },
    }


def completeness(rows: list[dict]) -> dict:
    """Whether the first code block with gem lines was closed before the reply ended (main run)."""
    out = defaultdict(Counter)
    for r in rows:
        if r["sample"] != 0:
            continue
        blocks = r["text"].split("```")
        closed = [b for k, b in enumerate(blocks) if k % 2 == 1 and k < len(blocks) - 1]
        has_gems = any(extract.gem_lines(b)[0] for b in closed)
        open_tail = len(blocks) % 2 == 0 and extract.gem_lines(blocks[-1])[0]
        out[r["finish"]]["replies"] += 1
        out[r["finish"]]["closed_gem_block"] += bool(has_gems)
        out[r["finish"]]["only_in_unclosed_block"] += bool(open_tail and not has_gems)
    return {k: dict(v) for k, v in out.items()}


def figure(res: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    models = sorted(MODELS, key=lambda m: res["models"][m]["rate"]["en"] + res["models"][m]["rate"]["uk"])
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True, sharex=True)
    y = np.arange(len(models))
    for ax, ctx, title in ((axes[0], "global", "Global services"), (axes[1], "ukraine", "Ukrainian services")):
        en = [100 * res["models"][m]["rate"][f"en|{ctx}"] for m in models]
        uk = [100 * res["models"][m]["rate"][f"uk|{ctx}"] for m in models]
        ax.barh(y - 0.2, en, 0.4, label="English request", color="#303030")
        ax.barh(y + 0.2, uk, 0.4, label="Ukrainian request", color="#c8c8c8", edgecolor="#303030", hatch="//")
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
    index = read_index(results / "rubygems_names.txt.gz")
    keys = {extract.key(n) for n in index}
    rows = load_rows(results / "replies.jsonl")
    labelled = label_rows(rows, cache, keys)
    with (results / "labelled.jsonl").open("w") as f:
        for r in labelled:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    res = rates(labelled, tasks)
    original = rates(label_rows(rows, cache, keys, rule="original"), tasks)
    exists = {n for n, v in cache.items() if v["status"] == "exists"}
    summary = {
        "rates": res,
        "names": names(labelled),
        "recurrence": recurrence(labelled),
        "completeness": completeness(rows),
        "descriptive": descriptive(labelled, tasks),
        "sensitivity_original_near_miss_rule": {
            "pooled": original["pooled"],
            "models": {m: {"rate": v["rate"], "uk_minus_en": v["uk_minus_en"]} for m, v in original["models"].items()},
        },
        "secondary_any_absent": secondary(labelled, tasks),
        "index": {"names": len(index), "api_exists_missing_from_index": sorted(exists - index)},
    }
    (results / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    figures.mkdir(exist_ok=True)
    figure(res, figures / "invented_by_model.png")
