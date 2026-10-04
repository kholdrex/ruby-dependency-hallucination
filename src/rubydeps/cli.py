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


def main():
    parser = argparse.ArgumentParser(prog="rubydeps")
    sub = parser.add_subparsers(required=True)
    run = sub.add_parser("run")
    run.add_argument("stage", choices=["pilot", "main", "repeats"])
    run.add_argument("--models", nargs="+", default=list(experiment.MODELS), choices=list(experiment.MODELS))
    run.set_defaults(func=cmd_run)
    sub.add_parser("check").set_defaults(func=cmd_check)
    sub.add_parser("analyze").set_defaults(func=cmd_analyze)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
