"""Run the complete local conformance gate and emit one canonical JSON result."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from graph_native_agent_control_plane import __version__
from graph_native_agent_control_plane.canonical_json import canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hypothesis",
        ".mypy_cache",
        ".pyright",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
    }
)
_TEXT_SUFFIXES = frozenset(
    {"", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
)
_PRIVATE_MARKERS = (
    ("{# " + "Model Get Context", "private context-block marker"),
    ("26," + "193 directives", "private corpus-size marker"),
    ("protocols." + "normalized", "private normalized-corpus marker"),
    ("C:" + "\\Users\\", "absolute Windows user path"),
    ("C:" + "/Users/", "absolute Windows user path"),
)


def _repository_files(root: Path) -> tuple[Path, ...]:
    paths = (
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.name != ".coverage"
        and path.suffix.casefold() in _TEXT_SUFFIXES
        and not any(part in _IGNORED_DIRECTORIES for part in path.relative_to(root).parts)
    )
    return tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))


def scan_private_material(root: Path) -> tuple[str, ...]:
    """Return deterministic findings for material excluded from the public boundary."""

    findings: list[str] = []
    for path in _repository_files(root):
        try:
            content = path.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            findings.append(f"{path.relative_to(root).as_posix()}: invalid UTF-8 text")
            continue
        for marker, description in _PRIVATE_MARKERS:
            if marker in content:
                findings.append(f"{path.relative_to(root).as_posix()}: {description}")
    return tuple(sorted(findings))


def result_bytes(checks: Sequence[str], *, status: str) -> bytes:
    """Serialize the stable public verification result."""

    return canonical_bytes(
        {
            "checks": list(checks),
            "kind": "graph_native_verification_v1",
            "status": status,
            "version": __version__,
        }
    )


def _run_command(name: str, command: Sequence[str]) -> bool:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode == 0:
        return True
    sys.stderr.write(f"[{name}] failed\n")
    sys.stderr.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return False


def main() -> int:
    """Run every release check without weakening later checks after a failure."""

    coverage_file = ROOT / ".coverage"
    coverage_file.unlink(missing_ok=True)
    python = sys.executable
    commands: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "release_manifest",
            (python, "scripts/release_manifest.py", "--check"),
        ),
        (
            "unit_property_tests",
            (python, "-m", "coverage", "run", "--branch", "-m", "unittest", "discover"),
        ),
        ("branch_coverage", (python, "-m", "coverage", "report", "--fail-under=100")),
        ("ruff", (python, "-m", "ruff", "check", ".")),
        ("mypy_strict", (python, "-m", "mypy", "src", "tests", "scripts")),
        ("pyright_strict", (python, "-m", "pyright", "src", "tests", "scripts")),
        (
            "schema_and_seed_determinism",
            (python, "-m", "unittest", "tests.test_schemas_and_replay"),
        ),
        ("reproducible_build", (python, "scripts/reproducible_build.py")),
    )
    passed: list[str] = []
    failed = False
    for name, command in commands:
        if _run_command(name, command):
            passed.append(name)
        else:
            failed = True

    private_findings = scan_private_material(ROOT)
    if private_findings:
        failed = True
        sys.stderr.write("[private_material_scan] failed\n")
        for finding in private_findings:
            sys.stderr.write(f"{finding}\n")
    else:
        passed.append("private_material_scan")

    sys.stdout.buffer.write(result_bytes(tuple(passed), status="failed" if failed else "passed"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
