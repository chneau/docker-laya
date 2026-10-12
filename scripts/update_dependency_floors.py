#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.15"
# ///
"""Bump the lower bounds in pyproject.toml and the pinned torch version to uv.lock."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
LOCKFILE = ROOT / "uv.lock"
DOCKERFILE = ROOT / "Dockerfile"
README = ROOT / "README.md"

REQUIREMENT = re.compile(r'^(\s*)"([^"]+)"(.*)', re.DOTALL)
NAME = re.compile(r"^[A-Za-z0-9._-]+")
EXTRAS = re.compile(r"^(\[[^\]]*\])?")
TORCH_ARG = re.compile(r"(?m)^(ARG TORCH_VERSION=)\S+")
TORCH_DOC = re.compile(r"(torch `)\d+\.\d+(?:\.\d+)?(`)")


def direct_dependency_names(pyproject: dict) -> list[str]:
    """Return the runtime and development dependency names declared in pyproject.toml."""
    names = []

    def collect(requirement: str) -> None:
        match = NAME.match(requirement.strip())
        if match:
            names.append(match.group(0))

    for requirement in pyproject["project"]["dependencies"]:
        collect(requirement)
    for group in pyproject.get("dependency-groups", {}).values():
        for requirement in group:
            collect(requirement)
    return names


def locked_versions(lock: dict) -> dict[str, str]:
    """Map each locked package name to its version, dropping any local segment."""
    versions: dict[str, str] = {}
    for package in lock["package"]:
        versions.setdefault(package["name"], package["version"].split("+", 1)[0])
    return versions


def bump_requirement(line: str, names: set[str], versions: dict[str, str]) -> str:
    """Replace a dependency line's specifier with a lower bound on its locked version."""
    match = REQUIREMENT.match(line)
    if not match:
        return line
    indent, requirement, rest = match.groups()
    name_match = NAME.match(requirement)
    if not name_match or name_match.group(0) not in names:
        return line
    name = name_match.group(0)
    extras = EXTRAS.match(requirement[len(name) :])
    suffix = extras.group(1) if extras else None
    return f'{indent}"{name}{suffix or ""}>={versions[name]}"{rest}'


def sync_torch_version(text: str, version: str) -> str:
    """Replace pinned torch versions (Dockerfile arg, README prose) with the locked one."""
    text = TORCH_ARG.sub(rf"\g<1>{version}", text)
    return TORCH_DOC.sub(rf"\g<1>{version}\g<2>", text)


def main() -> None:
    """Pin pyproject.toml lower bounds and the torch version to the current uv.lock."""
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    lock = tomllib.loads(LOCKFILE.read_text(encoding="utf-8"))
    names = direct_dependency_names(pyproject)
    versions = locked_versions(lock)
    missing = [name for name in names if name not in versions]
    if missing:
        raise SystemExit(f"Missing uv.lock versions for: {', '.join(missing)}")
    updated = [
        bump_requirement(line, set(names), versions)
        for line in PYPROJECT.read_text(encoding="utf-8").splitlines(keepends=True)
    ]
    PYPROJECT.write_text("".join(updated), encoding="utf-8")
    for path in (DOCKERFILE, README):
        text = path.read_text(encoding="utf-8")
        path.write_text(sync_torch_version(text, versions["torch"]), encoding="utf-8")


if __name__ == "__main__":
    main()
