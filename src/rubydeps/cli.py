import argparse
from pathlib import Path

from . import experiment, tasks

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
SEED = 2026
REPEAT_PER_CELL = 6
REPEATS = 3


def cmd_run(args):
    all_tasks = tasks.load(DATA / "tasks.jsonl")
    models = args.models
    if args.stage == "pilot":
        experiment.run(models, [t for t in all_tasks if t.id.endswith("01")], range(1), RESULTS / "pilot.jsonl")
    elif args.stage == "main":
        experiment.run(models, all_tasks, range(1), RESULTS / "replies.jsonl")
    else:
        subset = tasks.repeat_subset(all_tasks, REPEAT_PER_CELL, SEED)
        experiment.run(models, subset, range(1, REPEATS), RESULTS / "replies.jsonl")


def cmd_check(_):
    from . import analysis

    analysis.check_registry(RESULTS)


def cmd_analyze(_):
    from . import analysis

    analysis.main(tasks.load(DATA / "tasks.jsonl"), RESULTS, ROOT / "figures")


def cmd_revision(_):
    from . import revision

    revision.main(tasks.load(DATA / "tasks.jsonl"), ROOT)


def cmd_runc(args):
    from . import runc

    all_tasks = tasks.load(DATA / "tasks.jsonl")
    variants = runc.script_tasks(all_tasks, DATA / "script_tasks.jsonl")
    folder = RESULTS / "run-c"
    folder.mkdir(exist_ok=True)
    pilot, replies = folder / "pilot.jsonl", folder / "replies.jsonl"
    if args.stage == "pilot":
        first = dict(list(variants.items())[:3])
        pilot_main = [t for t in all_tasks if t.id.endswith("01")][:2]
        jobs = runc.jobs_script(args.models, first, pilot=True) + runc.jobs_main(args.models, pilot_main, pilot=True)
        runc.run(jobs, pilot, [pilot, replies])
        return
    if args.stage == "script":
        jobs = runc.jobs_script(args.models, variants)
    else:
        main_tasks = [t for t in all_tasks if t.context == "ukraine"] if args.ukraine_only else all_tasks
        jobs = runc.jobs_main(args.models, main_tasks)
    runc.run(jobs, replies, [pilot, replies])


def cmd_runc_check(_):
    from . import runc_analysis

    runc_analysis.check_registry(RESULTS / "run-c")


def cmd_runc_analyze(_):
    from . import runc_analysis

    runc_analysis.main(tasks.load(DATA / "tasks.jsonl"), ROOT)


def cmd_rund(_):
    from . import runc, rund

    all_tasks = tasks.load(DATA / "tasks.jsonl")
    variants = runc.script_tasks(all_tasks, DATA / "script_tasks.jsonl")
    folder = RESULTS / "run-d"
    folder.mkdir(exist_ok=True)
    replies = folder / "replies.jsonl"
    runc.run(rund.jobs(all_tasks, variants), replies, [replies], rund.BUDGET_STOP)


def cmd_rund_check(_):
    from . import rund_analysis

    rund_analysis.check_registry(ROOT)


def cmd_rund_analyze(_):
    from . import rund_analysis

    rund_analysis.main(tasks.load(DATA / "tasks.jsonl"), ROOT)


def main():
    parser = argparse.ArgumentParser(prog="rubydeps")
    sub = parser.add_subparsers(required=True)
    run = sub.add_parser("run")
    run.add_argument("stage", choices=["pilot", "main", "repeats"])
    run.add_argument("--models", nargs="+", default=list(experiment.MODELS), choices=list(experiment.MODELS))
    run.set_defaults(func=cmd_run)
    sub.add_parser("check").set_defaults(func=cmd_check)
    sub.add_parser("analyze").set_defaults(func=cmd_analyze)
    sub.add_parser("revision").set_defaults(func=cmd_revision)
    runc_parser = sub.add_parser("runc")
    runc_parser.add_argument("stage", choices=["pilot", "script", "main"])
    runc_parser.add_argument("--models", nargs="+", required=True)
    runc_parser.add_argument("--ukraine-only", action="store_true")
    runc_parser.set_defaults(func=cmd_runc)
    sub.add_parser("runc-check").set_defaults(func=cmd_runc_check)
    sub.add_parser("runc-analyze").set_defaults(func=cmd_runc_analyze)
    sub.add_parser("rund").set_defaults(func=cmd_rund)
    sub.add_parser("rund-check").set_defaults(func=cmd_rund_check)
    sub.add_parser("rund-analyze").set_defaults(func=cmd_rund_analyze)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
