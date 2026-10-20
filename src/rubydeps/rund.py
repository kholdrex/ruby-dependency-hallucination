"""Run D (protocol of 20 October 2026): Claude Sonnet 5.5 in the script experiment and the main run, and DeepSeek V4
Pro on the global tasks of the main run, which run C left out."""

from . import runc
from .tasks import LANGS, Task

SONNET = "anthropic/claude-sonnet-5.5"
DEEPSEEK = "deepseek/deepseek-v4-pro"
BUDGET_STOP = 36.0


def jobs(tasks: list[Task], variants: dict) -> list[tuple]:
    script = [("script", SONNET, arms[arm], "uk", arm, 10) for arms in variants.values() for arm in runc.ARMS]
    main = [("main", SONNET, t, lang, "original", 0) for t in tasks for lang in LANGS]
    main += [("main", DEEPSEEK, t, lang, "original", 0) for t in tasks if t.context == "global" for lang in LANGS]
    return script + main
