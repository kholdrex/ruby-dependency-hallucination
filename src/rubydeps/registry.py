"""Existence of gem names on rubygems.org, cached with the time of each lookup."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://rubygems.org/api/v1/gems/{name}.json"
RETRIES = 5


class Registry:
    def __init__(self, path: Path):
        self.path = path
        self.cache = json.loads(path.read_text()) if path.exists() else {}
        self.session = requests.Session()

    def status(self, name: str) -> str:
        """'exists', 'absent' or 'unknown' (network or server failure after retries)."""
        if name in self.cache and self.cache[name]["status"] != "unknown":
            return self.cache[name]["status"]
        status = "unknown"
        for attempt in range(RETRIES):
            try:
                response = self.session.get(API.format(name=name), timeout=30)
            except requests.RequestException:
                time.sleep(2**attempt)
                continue
            if response.status_code == 200:
                status = "exists"
                break
            if response.status_code == 404:
                status = "absent"
                break
            time.sleep(2**attempt)
        self.cache[name] = {"status": status, "checked": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        time.sleep(0.12)
        return status

    def save(self) -> None:
        self.path.write_text(json.dumps(dict(sorted(self.cache.items())), indent=1, ensure_ascii=False) + "\n")


INDEX = "https://rubygems.org/names"


def fetch_index(path: Path) -> None:
    """Save the full list of gem names published by rubygems.org (compact index), gzip-compressed."""
    import gzip

    response = requests.get(INDEX, timeout=300)
    response.raise_for_status()
    with gzip.open(path, "wt") as f:
        f.write(f"# {INDEX} {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n")
        f.write(response.text)


def read_index(path: Path) -> set[str]:
    import gzip

    with gzip.open(path, "rt") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith(("#", "---"))}
