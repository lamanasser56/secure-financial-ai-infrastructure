"""Check local documentation links and repository-root file references."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
ROOT_FILE = re.compile(
    r"(?<![\w/])(?:docs|runtime|contracts|kubernetes|scripts|database|tests|policy|k3s|\.github)"
    r"/[\w./-]+\.(?:md|yaml|yml|json|py|sh|sql)"
)
SOURCE_SUFFIXES = {".md", ".py"}


def main() -> None:
    failures: list[str] = []
    checked_links = 0
    checked_references = 0
    files = sorted(
        path for path in ROOT.rglob("*")
        if path.is_file() and not {".git", ".venv", "__pycache__"}.intersection(path.parts)
    )
    for path in files:
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        content = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        if path.suffix == ".md":
            for match in LINK.finditer(content):
                target = match.group(1).split(" ", 1)[0].strip("<>")
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or target.startswith(("#", "/")):
                    continue
                checked_links += 1
                candidate = (path.parent / unquote(parsed.path)).resolve()
                if not candidate.is_relative_to(ROOT) or not candidate.exists():
                    failures.append(f"{relative}: missing local link {target}")
        if path.suffix == ".py" and not relative.parts[:1] == ("runtime",):
            continue
        for match in ROOT_FILE.finditer(content):
            reference = match.group()
            checked_references += 1
            if not (ROOT / reference).is_file() and not (path.parent / reference).is_file():
                failures.append(f"{relative}: missing file reference {reference}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Validated {checked_links} local documentation links and {checked_references} file references")


if __name__ == "__main__":
    main()
