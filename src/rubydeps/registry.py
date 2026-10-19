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


GEM = "https://rubygems.org/api/v1/gems/{name}.json"
VERSIONS = "https://rubygems.org/api/v1/versions/{name}.json"


def details(names: list[str], path: Path) -> dict:
    """Downloads, latest and first release dates of published gems (added for the revision), cached with the time of
    each lookup."""
    cache = json.loads(path.read_text()) if path.exists() else {}
    session = requests.Session()
    for name in names:
        if name in cache:
            continue
        gem = versions = None
        for attempt in range(RETRIES):
            try:
                gem = session.get(GEM.format(name=name), timeout=30)
                versions = session.get(VERSIONS.format(name=name), timeout=30)
            except requests.RequestException:
                time.sleep(2**attempt)
                continue
            if gem.status_code in (200, 404) and versions.status_code in (200, 404):
                break
            time.sleep(2**attempt)
        entry = {"checked": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if gem is not None and gem.status_code == 200 and versions.status_code == 200:
            g, v = gem.json(), versions.json()
            entry |= {
                "name": g["name"],
                "downloads": g["downloads"],
                "latest_release": g["version_created_at"],
                "first_release": min(x["created_at"] for x in v) if v else None,
                "versions": len(v),
                "info": (g.get("info") or "")[:300],
            }
        else:
            entry["status"] = gem.status_code if gem is not None else "error"
        cache[name] = entry
        time.sleep(0.12)
    path.write_text(json.dumps(dict(sorted(cache.items())), indent=1, ensure_ascii=False) + "\n")
    return cache
