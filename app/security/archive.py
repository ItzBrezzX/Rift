"""ZIP safety. Names are validated before any extract. Uploaded executables are never run."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path


class UnsafeArchiveError(ValueError):
    def __init__(self, message: str, code: str = "unsafe") -> None:
        super().__init__(message)
        self.code = code


def validate_entry_name(raw: str, max_depth: int = 24, max_len: int = 512) -> str:
    if "\0" in raw:
        raise UnsafeArchiveError(f"Unsafe ZIP path (NUL): {raw}", "zip_slip")
    name = raw.replace("\\", "/")
    if len(name) > max_len:
        raise UnsafeArchiveError(f"Path too long: {raw}", "path_limit")
    if name.startswith("/") or (len(name) >= 2 and name[1] == ":"):
        raise UnsafeArchiveError(f"Unsafe ZIP path (absolute): {raw}", "zip_slip")
    parts = name.split("/")
    if len(parts) > max_depth or any(part == ".." for part in parts):
        raise UnsafeArchiveError(f"Unsafe ZIP path: {raw}", "zip_slip")
    return "/".join(part for part in parts if part not in ("", "."))


def validate_zip_names(names: list[str]) -> list[str]:
    return [validate_entry_name(name) for name in names]


def assert_zip_limits(
    zf: zipfile.ZipFile,
    max_entries: int = 20_000,
    max_uncompressed: int = 2 * 1024**3,
    max_ratio: int = 80,
) -> None:
    infos = zf.infolist()
    if len(infos) > max_entries:
        raise UnsafeArchiveError("Too many ZIP entries.", "too_many_entries")
    total = 0
    for info in infos:
        validate_entry_name(info.filename)
        if (info.flag_bits & 0x1) != 0:
            raise UnsafeArchiveError(f"Encrypted entry: {info.filename}", "encrypted")
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if (info.create_system == 3) and (unix_mode & 0o170000) == 0o120000:
            raise UnsafeArchiveError(f"Symlink rejected: {info.filename}", "symlink")
        total += info.file_size
        if total > max_uncompressed:
            raise UnsafeArchiveError("Uncompressed size exceeds the limit.", "zip_bomb")
        if (
            info.compress_size
            and info.file_size > 1_000_000
            and info.file_size / info.compress_size > max_ratio
        ):
            raise UnsafeArchiveError(
                f"Compression ratio too high: {info.filename}", "zip_bomb"
            )


def safe_extract(zf: zipfile.ZipFile, dest: Path) -> list[str]:
    """Extract only after every name is checked. Returns relative paths written."""
    assert_zip_limits(zf)
    dest = dest.resolve()
    written: list[str] = []
    for info in zf.infolist():
        name = validate_entry_name(info.filename)
        if not name or name.endswith("/"):
            continue
        target = (dest / name).resolve()
        if os.path.commonpath([str(dest), str(target)]) != str(dest):
            raise UnsafeArchiveError(
                f"Extract escaped workspace: {info.filename}", "zip_slip"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as src, target.open("wb") as out:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        written.append(name)
    return written
