"""Dependencies named in a reply: Gemfile declarations, install commands and require calls."""

import re
from dataclasses import dataclass

GEM_LINE = re.compile(r"""^[ \t]*gem[ \t]*\(?[ \t]*["']([^"']+)["']([^\n]*)""", re.MULTILINE)
INSTALL = re.compile(r"""\b(?:gem install|bundle add)[ \t]+([^\n`]+)""")
REQUIRE = re.compile(r"""^[ \t]*require[ \t]*\(?[ \t]*["']([^"']+)["']""", re.MULTILINE)
EXTERNAL_SOURCE = re.compile(r"""\b(?:git|github|gitlab|bitbucket|path)\s*(?::|=>)""")
VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class Dependencies:
    declared: tuple[str, ...]
    external: tuple[str, ...]
    required: tuple[str, ...]


def unique(names) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))


def install_names(arguments: str) -> list[str]:
    names = []
    for word in arguments.split():
        if word.startswith("-") or word.startswith("#"):
            break
        names.append(word.strip("'\"`;,"))
    return [n for n in names if n]


def parse(text: str) -> Dependencies:
    declared, external = [], []
    for name, rest in GEM_LINE.findall(text):
        (external if EXTERNAL_SOURCE.search(rest) else declared).append(name.strip())
    for arguments in INSTALL.findall(text):
        declared += install_names(arguments)
    required = [r.strip() for r in REQUIRE.findall(text)]
    return Dependencies(unique(declared), unique(external), unique(required))


def valid(name: str) -> bool:
    return bool(VALID_NAME.match(name))


def variants(name: str) -> list[str]:
    """Spellings that differ only in letter case or in hyphens and underscores (including their omission)."""
    lower = name.lower()
    candidates = [
        lower,
        name.replace("_", "-"),
        name.replace("-", "_"),
        lower.replace("_", "-"),
        lower.replace("-", "_"),
        lower.replace("_", "").replace("-", ""),
    ]
    return [c for c in dict.fromkeys(candidates) if c != name]
