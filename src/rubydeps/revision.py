"""Analyses added after the review of 19 October 2026 (post hoc, exploratory): wording equivalence strata, the
registry's typo protection for near misses, task-context intervals, robustness across runs and near-miss rules,
agreement between runs and existing names flagged for inspection."""

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import extract
from .analysis import RESAMPLES, SEED, interval, label_rows, outcome_matrix
from .experiment import MODELS, load_rows
from .registry import read_index
from .tasks import LANGS, Task

FLAGS = ("name_script_switch", "en_has_cyrillic", "content_differs")
DOWNLOADS_THRESHOLD = 10_000
PROTECTION_YEARS = 5
FLAG_FIRST_RELEASE = "2025-01-01"
FLAG_DOWNLOADS = 1_000
PLACEHOLDER_WORDS = ("placeholder", "reserved", "squat", "malicious", "dummy", "empty gem", "do not use", "hallucinat")


def load_coding(path: Path) -> dict[str, dict[str, int]]:
    with path.open() as f:
        return {r["id"]: {k: int(r[k]) for k in FLAGS} for r in csv.DictReader(f)}


def agreement(path: Path) -> dict:
    """Per flag: raw agreement, Cohen's kappa and the 2x2 counts of the two annotations."""
    by = defaultdict(dict)
    with path.open() as f:
        for r in csv.DictReader(f):
            by[r["coder"]][r["id"]] = {k: int(r[k]) for k in FLAGS}
    a, b = by["A"], by["B"]
    out = {}
    for flag in FLAGS:
        pairs = Counter((a[i][flag], b[i][flag]) for i in a)
        n = sum(pairs.values())
        po = (pairs[(0, 0)] + pairs[(1, 1)]) / n
        pa = (pairs[(1, 0)] + pairs[(1, 1)]) / n
        pb = (pairs[(0, 1)] + pairs[(1, 1)]) / n
        pe = pa * pb + (1 - pa) * (1 - pb)
        out[flag] = {"agreement": po, "kappa": (po - pe) / (1 - pe) if pe < 1 else 1.0,
                     "counts": {f"{x}{y}": pairs[(x, y)] for x in (0, 1) for y in (0, 1)}}
    return out


def pooled(matrix: dict) -> dict[str, np.ndarray]:
    """Mean over models of the 0/1 outcome per task, per language."""
    return {lang: np.vstack([matrix[m][lang] for m in MODELS]).mean(axis=0) for lang in LANGS}


def cell(values: dict[str, np.ndarray], mask: np.ndarray, rng) -> dict:
    """EN and UK rates and the paired UK-EN difference over the tasks in mask, bootstrap over those tasks."""
    idx = np.flatnonzero(mask)
    d = values["uk"][idx] - values["en"][idx]
    boots = rng.integers(0, len(idx), (RESAMPLES, len(idx)))
    return {"tasks": int(len(idx)), "en": float(values["en"][idx].mean()), "uk": float(values["uk"][idx].mean()),
            "uk_minus_en": {"value": float(d.mean()), "ci": interval(d[boots].mean(axis=1))}}


def stratified_boots(groups: np.ndarray, rng) -> np.ndarray:
    """Task indices resampled within every group (category x context), RESAMPLES rows."""
    parts = []
    for g in sorted(set(groups)):
        idx = np.flatnonzero(groups == g)
        parts.append(idx[rng.integers(0, len(idx), (RESAMPLES, len(idx)))])
    return np.hstack(parts)


def contrasts(values: dict[str, np.ndarray], tasks: list[Task], keep: np.ndarray, rng) -> dict:
    """Pooled UK-EN, context gap and their interaction over the kept tasks, resampling within category x context."""
    context = np.array([t.context for t in tasks])[keep]
    groups = np.array([f"{t.category}|{t.context}" for t in tasks])[keep]
    en, uk = values["en"][keep], values["uk"][keep]
    d, both = uk - en, (uk + en) / 2
    boots = stratified_boots(groups, rng)

    def gap(v, c):
        return v[c == "ukraine"].mean() - v[c == "global"].mean()

    def est(fn):
        return {"value": float(fn(np.arange(len(d)))), "ci": interval(np.array([fn(b) for b in boots]))}

    return {
        "tasks": {c: int((context == c).sum()) for c in ("global", "ukraine")},
        "uk_minus_en": est(lambda b: d[b].mean()),
        "ukraine_minus_global": est(lambda b: gap(both[b], context[b])),
        "interaction": est(lambda b: gap(d[b], context[b])),
    }


def equivalence(labelled: list[dict], tasks: list[Task], coding: dict, outcome=("invented",)) -> dict:
    rng = np.random.default_rng(SEED)
    values = pooled(outcome_matrix(labelled, tasks, outcome))
    context = np.array([t.context for t in tasks])
    flag = {k: np.array([coding[t.id][k] for t in tasks]).astype(bool) for k in FLAGS}
    strata = {}
    for ctx in ("global", "ukraine"):
        for s in (0, 1):
            mask = (context == ctx) & (flag["name_script_switch"] == bool(s))
            if mask.any():
                strata[f"{ctx}|switch={s}"] = cell(values, mask, rng)
    any_flag = flag["name_script_switch"] | flag["en_has_cyrillic"] | flag["content_differs"]
    return {
        "strata": strata,
        "all_tasks": contrasts(values, tasks, np.ones(len(tasks), bool), rng),
        "without_switch": contrasts(values, tasks, ~flag["name_script_switch"], rng),
        "without_any_flag": contrasts(values, tasks, ~any_flag, rng),
    }


def invented_by_stratum(labelled: list[dict], tasks: list[Task], coding: dict, name_classes: dict) -> dict:
    """Invented names in main-run replies to name-switch tasks, by language, with reply counts and the hand-coded
    class of each name (entity_derived: a spelling, transliteration or translation of the switched name)."""
    switched = {t.id for t in tasks if coding[t.id]["name_script_switch"]}
    names = {lang: Counter() for lang in LANGS}
    replies = {lang: 0 for lang in LANGS}
    for r in labelled:
        if r["sample"] == 0 and r["task"] in switched:
            inv = [n for n, c in r["classes"].items() if c == "invented"]
            names[r["lang"]].update(inv)
            replies[r["lang"]] += bool(inv)
    out = {}
    for lang in LANGS:
        by_class = Counter()
        for n, k in names[lang].items():
            by_class[name_classes[n]] += k
        out[lang] = {"replies_with_invented": replies[lang], "distinct": len(names[lang]),
                     "occurrences_by_class": dict(by_class), "names": dict(names[lang].most_common())}
    return out


def typo_protection(labelled: list[dict], index: set[str], details: dict, assessed: datetime) -> dict:
    """RubyGems' typo-protection predicate (gem_typo.rb, commit fc87b0c) applied to near misses, for a pusher who owns
    none of the colliding gems and with the exception list unknown: a name with a published case-insensitive exact
    match is refused by the name-uniqueness validation instead; otherwise it is blocked when any published gem with
    the same name after upper-casing and removing every '_' and '-' has at least 10,000 downloads or a most recent
    version created within the last five years."""
    cutoff = assessed.replace(year=assessed.year - PROTECTION_YEARS)
    by_upper = defaultdict(list)
    by_key = defaultdict(list)
    for n in index:
        by_upper[n.upper()].append(n)
        by_key[n.upper().replace("_", "").replace("-", "")].append(n)

    def status(name):
        if by_upper.get(name.upper()):
            return "case_only_exists", by_upper[name.upper()]
        targets = by_key.get(name.upper().replace("_", "").replace("-", ""), [])
        info = [details.get(t) for t in targets]
        if not targets or any(i is None or "downloads" not in i for i in info):
            return "unresolved", targets
        protected = [t for t, i in zip(targets, info, strict=True) if i["downloads"] >= DOWNLOADS_THRESHOLD
                     or datetime.fromisoformat(i["latest_release"].replace("Z", "+00:00")) >= cutoff]
        return ("blocked" if protected else "not_blocked"), targets

    occurrences = Counter()
    main_names = Counter()
    for r in labelled:
        for n, c in r["classes"].items():
            if c == "near_miss":
                occurrences[n] += 1
                main_names[n] += r["sample"] == 0
    per_name = {}
    for n in sorted(occurrences):
        s, targets = status(n)
        per_name[n] = {"status": s, "targets": sorted(targets), "main_run": main_names[n], "all": occurrences[n]}
    summary = {}
    for scope in ("main_run", "all"):
        names = [n for n in per_name if per_name[n][scope]]
        summary[scope] = {
            "distinct": dict(Counter(per_name[n]["status"] for n in names)),
            "occurrences": dict(sum((Counter({per_name[n]["status"]: per_name[n][scope]}) for n in names), Counter())),
        }
    return {"assessed": assessed.date().isoformat(), "cutoff": cutoff.date().isoformat(), "summary": summary,
            "names": per_name}


def context_table(labelled: list[dict], tasks: list[Task]) -> dict:
    """Invented-gem rate per category x context (mean over models and languages) and the context difference per
    category, resampling tasks within each category x context cell; pointwise exploratory intervals."""
    rng = np.random.default_rng(SEED)
    values = pooled(outcome_matrix(labelled, tasks))
    both = (values["en"] + values["uk"]) / 2
    category = np.array([t.category for t in tasks])
    context = np.array([t.context for t in tasks])
    groups = np.array([f"{c}|{x}" for c, x in zip(category, context, strict=True)])
    boots = stratified_boots(groups, rng)
    out = {}
    for c in sorted(set(category)):
        g, u = (category == c) & (context == "global"), (category == c) & (context == "ukraine")
        rate = lambda b, m: both[b][m[b]].mean()  # noqa: E731
        out[c] = {
            "global": {"value": float(both[g].mean()), "ci": interval(np.array([rate(b, g) for b in boots]))},
            "ukraine": {"value": float(both[u].mean()), "ci": interval(np.array([rate(b, u) for b in boots]))},
            "ukraine_minus_global": {
                "value": float(both[u].mean() - both[g].mean()),
                "ci": interval(np.array([rate(b, u) - rate(b, g) for b in boots])),
            },
        }
    return out


def robustness(runs: dict[str, tuple[list[dict], dict, set[str]]], tasks: list[Task]) -> dict:
    """Language contrast, context gap and interaction for run A and run B under the final and the original near-miss
    rule, and the any-absent outcome; the same stratified bootstrap for every row."""
    out = {}
    for run, (rows, cache, keys) in runs.items():
        for rule in ("final", "original"):
            labelled = label_rows(rows, cache, keys, rule)
            for name, outcome in (("invented", ("invented",)), ("any_absent", ("invented", "near_miss", "malformed"))):
                if rule == "original" and name == "any_absent":
                    continue
                rng = np.random.default_rng(SEED)
                values = pooled(outcome_matrix(labelled, tasks, outcome))
                out[f"{run}|{rule}|{name}"] = contrasts(values, tasks, np.ones(len(tasks), bool), rng)
    return out


def reclassified(rows: list[dict], cache: dict, keys: set[str]) -> dict:
    """Main-run names whose class differs between the original and the final near-miss rule, by language."""
    final = label_rows(rows, cache, keys, "final")
    original = label_rows(rows, cache, keys, "original")
    out = defaultdict(Counter)
    for f, o in zip(final, original, strict=True):
        if f["sample"] != 0:
            continue
        for n, c in f["classes"].items():
            if o["classes"][n] != c:
                out[f["lang"]][f"{o['classes'][n]}->{c}"] += 1
    return {lang: dict(v) for lang, v in out.items()}


def bundler_name_level(labelled: list[dict]) -> dict:
    """Share of declared main-run names that are invented, with and without the name 'bundler'."""
    out = {}
    for label, skip in (("all", set()), ("without_bundler", {"bundler"})):
        declared = invented = 0
        for r in labelled:
            if r["sample"] != 0:
                continue
            for n, c in r["classes"].items():
                if n in skip:
                    continue
                declared += 1
                invented += c == "invented"
        out[label] = {"declared": declared, "invented": invented, "share": invented / declared}
    out["bundler_declarations"] = sum("bundler" in r["classes"] for r in labelled if r["sample"] == 0)
    return out


def run_agreement(run_a: list[dict], run_b: list[dict]) -> dict:
    """Per model and scope (main run, repeats): run B replies identical to the run A reply for the same task,
    language and seed, strict extensions of it, or other."""
    a = {(r["model"], r["task"], r["lang"], r["sample"]): r for r in run_a}
    out = {}
    for m in MODELS:
        res = {}
        for scope, pick in (("main_run", lambda s: s == 0), ("repeats", lambda s: s > 0)):
            c = Counter()
            for r in run_b:
                if r["model"] != m or not pick(r["sample"]):
                    continue
                old = a.get((r["model"], r["task"], r["lang"], r["sample"]))
                if old is None or not r["text"].strip():
                    c["not_comparable"] += 1
                elif r["text"] == old["text"]:
                    c["identical"] += 1
                elif r["text"].startswith(old["text"]) and old["text"].strip():
                    c["extends_run_a"] += 1
                else:
                    c["other"] += 1
            res[scope] = dict(c)
        out[m] = res
    return out


def within_run_duplicates(run_b: list[dict]) -> dict:
    """Per model: repeat groups (task, language) in run B whose different-seed replies are textually identical."""
    groups = defaultdict(list)
    for r in run_b:
        groups[(r["model"], r["task"], r["lang"])].append(r["text"])
    out = Counter()
    for (m, _, _), texts in groups.items():
        if len(texts) > 1 and len(set(texts)) < len(texts):
            out[m] += 1
    return {m: out[m] for m in MODELS}


HTTP_CLIENTS = {"httparty", "faraday", "rest-client", "http", "excon", "typhoeus", "httpclient", "net-http-persistent"}


def http_clients(labelled: list[dict], tasks: list[Task]) -> dict:
    """Share of main-run replies that declare a general HTTP client, by category and context."""
    by_id = {t.id: t for t in tasks}
    counts = defaultdict(Counter)
    for r in labelled:
        if r["sample"] != 0:
            continue
        t = by_id[r["task"]]
        for key in (t.context, f"{t.category}|{t.context}"):
            counts[key]["replies"] += 1
            counts[key]["with_http_client"] += bool(HTTP_CLIENTS & set(r["classes"]))
    return {k: {**v, "share": v["with_http_client"] / v["replies"]} for k, v in sorted(counts.items())}


def recurrence_interval(labelled: list[dict]) -> dict:
    """Share of invented names from the first reply that reappear in a repeated reply, with an interval from
    resampling whole repeated tasks (all models, languages and samples of a task together)."""
    rng = np.random.default_rng(SEED)
    groups = defaultdict(dict)
    for r in labelled:
        invented = {n for n, c in r["classes"].items() if c == "invented"}
        groups[(r["model"], r["task"], r["lang"])][r["sample"]] = invented
    per_task = defaultdict(lambda: [0, 0])
    for (_, task, _), g in groups.items():
        if len(g) < 2:
            continue
        later = set().union(*(names for sample, names in g.items() if sample > 0))
        per_task[task][0] += len(g.get(0, set()))
        per_task[task][1] += len(g.get(0, set()) & later)
    ids = sorted(per_task)
    first = np.array([per_task[i][0] for i in ids])
    again = np.array([per_task[i][1] for i in ids])
    boots = rng.integers(0, len(ids), (RESAMPLES, len(ids)))
    shares = again[boots].sum(axis=1) / np.maximum(first[boots].sum(axis=1), 1)
    return {"tasks": len(ids), "first": int(first.sum()), "again": int(again.sum()),
            "value": float(again.sum() / first.sum()), "ci": interval(shares)}


def flagged_existing(labelled: list[dict], details: dict) -> dict:
    """Declared names that exist but were first published recently with few downloads, or whose description
    suggests a placeholder: flagged for inspection, not classified."""
    counts = Counter(n for r in labelled for n, c in r["classes"].items() if c == "exists")
    flagged = {}
    for n in sorted(counts):
        i = details.get(n, {})
        if "downloads" not in i:
            continue
        young = (i["first_release"] or "") >= FLAG_FIRST_RELEASE and i["downloads"] < FLAG_DOWNLOADS
        words = [w for w in PLACEHOLDER_WORDS if w in i["info"].lower()]
        if young or words:
            flagged[n] = {"declarations": counts[n], "downloads": i["downloads"], "first_release": i["first_release"],
                          "versions": i["versions"], "young_and_rare": young, "description_words": words,
                          "info": i["info"]}
    return {"existing_names": len(counts), "rule": f"first release >= {FLAG_FIRST_RELEASE} and downloads < "
            f"{FLAG_DOWNLOADS}, or a description word in {list(PLACEHOLDER_WORDS)}", "flagged": flagged}


def main(tasks: list[Task], root: Path) -> None:
    results, archive = root / "results", root / "archive" / "run-a"
    coding = load_coding(root / "data" / "task_coding.csv")
    labelled = [json.loads(line) for line in (results / "labelled.jsonl").open()]
    rows_b = load_rows(results / "replies.jsonl")
    rows_a = load_rows(archive / "replies.jsonl")
    cache_b = json.loads((results / "registry.json").read_text())
    cache_a = json.loads((archive / "registry.json").read_text())
    index_b = read_index(results / "rubygems_names.txt.gz")
    keys_b = {extract.key(n) for n in index_b}
    keys_a = {extract.key(n) for n in read_index(archive / "rubygems_names.txt.gz")}
    labelled_a = label_rows(rows_a, cache_a, keys_a)
    with (root / "data" / "switch_task_invented_names.csv").open() as f:
        name_classes = {r["name"]: r["class"] for r in csv.DictReader(f)}
    details_path = results / "gem_details.json"
    details = json.loads(details_path.read_text())
    assessed = max(datetime.fromisoformat(v["checked"]) for v in details.values()).astimezone(timezone.utc)
    out = {
        "coding_agreement": agreement(root / "data" / "task_coding_annotations.csv"),
        "coding_counts": {k: dict(Counter((t.context, coding[t.id][k]) for t in tasks).items()) for k in FLAGS},
        "equivalence_run_b": equivalence(labelled, tasks, coding),
        "equivalence_run_a": equivalence(labelled_a, tasks, coding),
        "equivalence_run_b_any_absent": equivalence(labelled, tasks, coding, ("invented", "near_miss", "malformed")),
        "invented_in_switch_tasks": invented_by_stratum(labelled, tasks, coding, name_classes),
        "typo_protection": typo_protection(labelled, index_b, details, assessed),
        "context_table": context_table(labelled, tasks),
        "robustness": robustness({"run_b": (rows_b, cache_b, keys_b), "run_a": (rows_a, cache_a, keys_a)}, tasks),
        "reclassified_by_rule_run_b": reclassified(rows_b, cache_b, keys_b),
        "reclassified_by_rule_run_a": reclassified(rows_a, cache_a, keys_a),
        "name_level_bundler": bundler_name_level(labelled),
        "run_agreement": run_agreement(rows_a, rows_b),
        "within_run_b_duplicates": within_run_duplicates(rows_b),
        "flagged_existing": flagged_existing(labelled, details),
        "http_clients": http_clients(labelled, tasks),
        "recurrence_task_bootstrap": recurrence_interval(labelled),
    }
    out["coding_counts"] = {k: {f"{c}|{v}": n for (c, v), n in d.items()} for k, d in out["coding_counts"].items()}
    (results / "revision.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
