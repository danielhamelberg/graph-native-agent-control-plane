"""Build the distribution twice and require byte-identical artifacts."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from graph_native_agent_control_plane import __version__
from graph_native_agent_control_plane.canonical_json import JsonValue, canonical_bytes

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATE_EPOCH = "315532800"


class BuildReproducibilityError(RuntimeError):
    """Raised when isolated distribution builds are incomplete or unstable."""


def _artifact_paths(directory: Path) -> dict[str, Path]:
    return {
        path.name: path
        for path in sorted(directory.iterdir(), key=lambda item: item.name)
        if path.is_file()
    }


def compare_artifact_directories(first: Path, second: Path) -> dict[str, str]:
    """Compare artifact sets and bytes, returning stable SHA-256 values."""

    first_paths = _artifact_paths(first)
    second_paths = _artifact_paths(second)
    if not first_paths or set(first_paths) != set(second_paths):
        raise BuildReproducibilityError("artifact sets differ between isolated builds")
    hashes: dict[str, str] = {}
    for name in sorted(first_paths):
        first_bytes = first_paths[name].read_bytes()
        second_bytes = second_paths[name].read_bytes()
        if first_bytes != second_bytes:
            raise BuildReproducibilityError(f"artifact bytes differ between builds: {name}")
        hashes[name] = hashlib.sha256(first_bytes).hexdigest()
    return hashes


def _build(output_directory: Path, seed: str) -> None:
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = seed
    environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    completed = subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(output_directory)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise BuildReproducibilityError(f"isolated build failed under hash seed {seed}")


def main() -> int:
    """Run two isolated builds and emit a canonical machine result."""

    try:
        with tempfile.TemporaryDirectory(prefix="graph-native-build-") as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            _build(first, "0")
            _build(second, "123")
            hashes = compare_artifact_directories(first, second)
    except (BuildReproducibilityError, OSError) as exc:
        sys.stderr.write(f"reproducible build error: {exc}\n")
        return 1
    artifact_values: dict[str, JsonValue] = dict(hashes)
    result: dict[str, JsonValue] = {
        "artifacts": artifact_values,
        "kind": "graph_native_reproducible_build_v1",
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "status": "passed",
        "version": __version__,
    }
    sys.stdout.buffer.write(canonical_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
