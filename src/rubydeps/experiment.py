"""Replies of every model to every task in both languages; stored as JSONL and resumable."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from . import prompts
from .client import OpenRouter
from .tasks import LANGS, Task

MODELS = {
    "openai/gpt-4o-mini": "openai",
    "google/gemini-2.5-flash-lite": "google-ai-studio",
    "deepseek/deepseek-chat-v3.1": "siliconflow/fp8",
    "meta-llama/llama-3.3-70b-instruct": "novita/bf16",
    "qwen/qwen3-coder-30b-a3b-instruct": "novita/fp8",
    "mistralai/mistral-small-3.2-24b-instruct": "deepinfra/fp8",
    "google/gemma-3-12b-it": "deepinfra/bf16",
    "meta-llama/llama-3.1-8b-instruct": "deepinfra/fp8",
}
TEMPERATURE = 0.7
MAX_TOKENS = 1200
WORKERS = 24


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f]


def key(row: dict) -> tuple:
    return row["model"], row["task"], row["lang"], row["sample"]


def run(models: list[str], tasks: list[Task], samples: range, path: Path) -> None:
    done = {key(r) for r in load_rows(path)}
    jobs = [(m, t, lang, s) for m in models for t in tasks for lang in LANGS for s in samples
            if (m, t.id, lang, s) not in done]
    client = OpenRouter()
    lock = threading.Lock()

    def call(job):
        model, task, lang, sample = job
        reply = client.chat(model, MODELS[model], prompts.messages(task, lang), TEMPERATURE, MAX_TOKENS, seed=sample)
        row = {"model": model, "task": task.id, "lang": lang, "sample": sample, **asdict(reply)}
        with lock, path.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(call, jobs))
