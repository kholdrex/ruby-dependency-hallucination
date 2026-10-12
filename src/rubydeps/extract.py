"""Dependencies named in a reply: Gemfile declarations, install commands and require calls."""

import re
from dataclasses import dataclass

GEM_LINE = re.compile(r"""^(?:echo[ \t]+["'])?[ \t]*gem[ \t]*\(?[ \t]*["']([^"']+)["'](.*)$""")
SOURCE_BLOCK = re.compile(r"""^(?:git|github|gitlab|bitbucket|path)\b.*\bdo\s*(\|.*\|)?\s*$""")
BLOCK_END = re.compile(r"^end\b")
BLOCK_OPEN = re.compile(r"\bdo\s*(\|.*\|)?\s*$")
INSTALL = re.compile(r"""\b(?:gem install|bundle add)[ \t]+([^\n`]+)""")
REQUIRE = re.compile(r"""^[ \t]*require[ \t]*\(?[ \t]*["']([^"']+)["']""", re.MULTILINE)
EXTERNAL_SOURCE = re.compile(r"""\b(?:git|github|gitlab|bitbucket|path)\s*(?::|=>)""")
VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHELL_STOP = {"&&", "||", ";", "|", ">", ">>", "2>&1"}
FLAGS_WITH_VALUE = {"-v", "--version", "-i", "--install-dir", "-s", "--source", "--platform", "-g", "--group"}


@dataclass(frozen=True)
class Dependencies:
    declared: tuple[str, ...]
    external: tuple[str, ...]
    required: tuple[str, ...]


def unique(names) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))


def install_names(arguments: str) -> list[str]:
    """Gem names after `gem install` or `bundle add`, skipping options and stopping at shell operators."""
    names, skip = [], False
    for word in arguments.split():
        if skip:
            skip = False
            continue
        if word in SHELL_STOP or word.startswith("#"):
            break
        if word.startswith("-"):
            skip = word in FLAGS_WITH_VALUE
            continue
        name = word.strip("'\"`,")
        if name.endswith(";"):
            names.append(name.rstrip(";"))
            break
        names.append(name)
    return [n for n in names if n]


def logical_lines(text: str) -> list[str]:
    """Stripped lines, with a line that ends in a comma joined to the next one (multi-line gem options)."""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if out and out[-1].endswith(","):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return out


def gem_lines(text: str) -> tuple[list[str], list[str]]:
    """Names from `gem` lines; gems inside a git/github/path block or with such an option are external."""
    declared, external, depth = [], [], 0
    for line in logical_lines(text):
        if SOURCE_BLOCK.match(line) or (depth and BLOCK_OPEN.search(line)):
            depth += 1
            continue
        if depth and BLOCK_END.match(line):
            depth -= 1
            continue
        m = GEM_LINE.match(line)
        if not m:
            continue
        name, rest = m.group(1), m.group(2).split("#", 1)[0]
        (external if depth or EXTERNAL_SOURCE.search(rest) else declared).append(name)
    return declared, external


def parse(text: str) -> Dependencies:
    declared, external = gem_lines(text)
    for arguments in INSTALL.findall(text):
        declared += install_names(arguments)
    required = REQUIRE.findall(text)
    return Dependencies(unique(declared), unique(external), unique(required))


def valid(name: str) -> bool:
    return bool(VALID_NAME.match(name))


def key(name: str) -> str:
    """Spelling-insensitive form of a name: letter case, hyphens and underscores are ignored."""
    return re.sub(r"[-_]", "", name.lower())


def original_variants(name: str) -> list[str]:
    """The near-miss rule of the first protocol version: case and a wholesale hyphen/underscore swap."""
    lower = name.lower()
    candidates = [
        lower,
        name.replace("_", "-"),
        name.replace("-", "_"),
        lower.replace("_", "-"),
        lower.replace("-", "_"),
    ]
    return [c for c in dict.fromkeys(candidates) if c != name]
