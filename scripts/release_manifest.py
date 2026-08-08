"""Create or verify the deterministic public release manifest."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

from graph_native_agent_control_plane import __version__
from graph_native_agent_control_plane.canonical_json import (
    JsonValue,
    canonical_bytes,
    canonical_sha256,
    loads_strict,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "evidence" / "release-manifest.json"
_ROOT_FILES = frozenset(
    {
        ".gitattributes",
        ".gitignore",
        "CITATION.cff",
        "CONTRIBUTING.md",
        "LICENSE",
        "NOTICE",
        "README.md",
        "SECURITY.md",
        "pyproject.toml",
        "uv.lock",
    }
)
_PUBLIC_DIRECTORIES = (
    ".github",
    "docs",
    "evidence",
    "examples",
    "schemas",
    "scripts",
    "src",
    "tests",
)
_EXCLUDED_NAMES = frozenset({".release-manifest.tmp", "release-manifest.json"})
_EXCLUDED_PARTS = frozenset({"__pycache__"})


class ManifestError(ValueError):
    """Raised when public release input is incomplete or noncanonical."""


def _public_paths(root: Path) -> Iterator[Path]:
    for name in sorted(_ROOT_FILES):
        path = root / name
        if path.is_file():
            yield path
    for directory_name in _PUBLIC_DIRECTORIES:
        directory = root / directory_name
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
            relative = path.relative_to(root)
            if (
                path.is_file()
                and path.name not in _EXCLUDED_NAMES
                and not any(part in _EXCLUDED_PARTS for part in relative.parts)
            ):
                yield path


def _validate_text(path: Path, data: bytes) -> None:
    relative = path.as_posix()
    if data.startswith(b"\xef\xbb\xbf"):
        raise ManifestError(f"UTF-8 BOM is forbidden: {relative}")
    if b"\r\n" in data or b"\r" in data:
        raise ManifestError(f"CRLF or CR line endings are forbidden: {relative}")
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ManifestError(f"invalid UTF-8 at byte {exc.start}: {relative}") from None
    if not data.endswith(b"\n"):
        raise ManifestError(f"public text must end with LF: {relative}")


def build_manifest(root: Path) -> dict[str, JsonValue]:
    """Hash every public source artifact except the self-referential manifest."""

    files: dict[str, JsonValue] = {}
    for path in _public_paths(root):
        data = path.read_bytes()
        _validate_text(path.relative_to(root), data)
        relative = path.relative_to(root).as_posix()
        files[relative] = {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    if "README.md" not in files or "pyproject.toml" not in files:
        raise ManifestError("release root must contain README.md and pyproject.toml")
    return {
        "files": dict(sorted(files.items())),
        "kind": "graph_native_release_manifest_v1",
        "version": __version__,
    }


def _summary(manifest: dict[str, JsonValue], status: str) -> bytes:
    return canonical_bytes(
        {
            "kind": "graph_native_release_manifest_result_v1",
            "manifest_sha256": canonical_sha256(manifest),
            "status": status,
            "version": __version__,
        }
    )


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / ".release-manifest.tmp"
    temporary.write_bytes(data)
    temporary.replace(path)


def main(arguments: Sequence[str] | None = None) -> int:
    """Write or check the manifest and emit one canonical result."""

    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="atomically replace the manifest")
    mode.add_argument("--check", action="store_true", help="verify the checked-in manifest")
    options = parser.parse_args(arguments)
    try:
        manifest = build_manifest(ROOT)
        if options.write:
            _write_atomic(MANIFEST_PATH, canonical_bytes(manifest))
            status = "written"
        else:
            if not MANIFEST_PATH.is_file():
                raise ManifestError("checked-in release manifest is missing")
            if loads_strict(MANIFEST_PATH.read_bytes()) != manifest:
                raise ManifestError("checked-in release manifest does not match public artifacts")
            status = "passed"
    except (ManifestError, OSError) as exc:
        sys.stderr.write(f"release manifest error: {exc}\n")
        return 1
    sys.stdout.buffer.write(_summary(manifest, status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
