"""Static PE inspection. Never executes the image."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

MACHINE = {
    "I386": 0x14C,
    "ARM": 0x1C0,
    "AMD64": 0x8664,
    "ARM64": 0xAA64,
}

MACHINES = {0x14C: "x86", 0x1C0: "arm", 0x8664: "x64", 0xAA64: "arm64"}


@dataclass
class PeInfo:
    valid: bool
    reason: str = ""
    machine: int | None = None
    machine_name: str | None = None
    pe32plus: bool | None = None
    is_dll: bool = False
    is_dotnet: bool = False
    imports: list[str] = field(default_factory=list)
    section_names: list[str] = field(default_factory=list)
    interesting_strings: list[str] = field(default_factory=list)


def _u16(buf: bytes, off: int) -> int:
    return struct.unpack_from("<H", buf, off)[0]


def _u32(buf: bytes, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def _ascii_strings(data: bytes, min_len: int = 6) -> list[str]:
    found: list[str] = []
    start = -1
    limit = min(len(data), 1_500_000)

    def flush(end: int) -> None:
        nonlocal start
        if start >= 0 and end - start >= min_len:
            found.append(data[start:end].decode("ascii", "replace"))
        start = -1

    for i in range(limit):
        c = data[i]
        if 32 <= c <= 126:
            if start < 0:
                start = i
        else:
            flush(i)
    flush(limit)
    return found


INTERESTING = [
    "unityplayer.dll",
    "gameassembly.dll",
    "d3d11.dll",
    "d3d12.dll",
    "d3d9.dll",
    "dxgi.dll",
    "opengl32.dll",
    "xinput1_4.dll",
    "xinput1_3.dll",
    "dinput8.dll",
    "xaudio2_9.dll",
    "ws2_32.dll",
    "user32.dll",
    "kernel32.dll",
    "mono-2.0-bdwgc.dll",
    "baselib.dll",
]


def interesting_strings(data: bytes) -> list[str]:
    raw = _ascii_strings(data, 5)
    hits: set[str] = set()
    import re

    version_re = re.compile(
        r"(?:^|[^0-9])((?:6000|\d{4})\.\d+\.\d+[abfcp]\d+|\d+\.\d+\.\d+[abfcp]\d+)"
    )
    for s in raw:
        lower = s.lower()
        for needle in INTERESTING:
            if needle in lower:
                hits.add(needle)
        if "unrealengine" in lower or "unreal engine" in lower:
            hits.add("unreal engine")
        if "unityplayer" in lower:
            hits.add("unityplayer")
        if "il2cpp" in lower:
            hits.add("il2cpp")
        m = version_re.search(s)
        if m:
            hits.add(f"version:{m.group(1)}")
    return sorted(hits)


def parse_pe(data: bytes) -> PeInfo:
    strings = interesting_strings(data)
    blank = PeInfo(False, interesting_strings=strings)
    if len(data) < 0x40 or data[:2] != b"MZ":
        return PeInfo(False, "Missing MZ header.", interesting_strings=strings)
    lfanew = _u32(data, 0x3C)
    if lfanew <= 0 or lfanew + 24 > len(data) or data[lfanew : lfanew + 4] != b"PE\0\0":
        return PeInfo(False, "PE header missing or out of range.", interesting_strings=strings)
    machine = _u16(data, lfanew + 4)
    sections = _u16(data, lfanew + 6)
    opt_size = _u16(data, lfanew + 20)
    characteristics = _u16(data, lfanew + 22)
    opt = lfanew + 24
    if opt + opt_size > len(data):
        return PeInfo(
            False,
            "Optional header truncated.",
            machine,
            MACHINES.get(machine),
            interesting_strings=strings,
        )
    magic = _u16(data, opt)
    pe32plus = magic == 0x20B
    if magic not in (0x10B, 0x20B):
        return PeInfo(
            False,
            f"Unknown optional magic 0x{magic:x}.",
            machine,
            MACHINES.get(machine),
            interesting_strings=strings,
        )
    rva_count = _u32(data, opt + (108 if pe32plus else 92))
    dir_at = opt + (112 if pe32plus else 96)

    def directory(index: int) -> tuple[int, int] | None:
        if index >= rva_count:
            return None
        at = dir_at + index * 8
        if at + 8 > len(data):
            return None
        return _u32(data, at), _u32(data, at + 4)

    parsed_sections = []
    table = opt + opt_size
    for i in range(sections):
        at = table + i * 40
        if at + 40 > len(data):
            break
        name = data[at : at + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        parsed_sections.append(
            {
                "name": name,
                "vsize": _u32(data, at + 8),
                "va": _u32(data, at + 12),
                "raw_size": _u32(data, at + 16),
                "raw": _u32(data, at + 20),
            }
        )

    def rva_off(rva: int) -> int | None:
        for section in parsed_sections:
            span = max(section["vsize"], section["raw_size"])
            if section["va"] <= rva < section["va"] + span:
                return section["raw"] + (rva - section["va"])
        return None

    imports: list[str] = []
    imp = directory(1)
    if imp and imp[0] and imp[1]:
        start = rva_off(imp[0])
        if start is not None:
            for n in range(64):
                at = start + n * 20
                if at + 20 > len(data):
                    break
                name_rva = _u32(data, at + 12)
                if name_rva == 0 and _u32(data, at) == 0:
                    break
                name_off = rva_off(name_rva)
                if name_off is None:
                    continue
                end = data.find(b"\0", name_off, name_off + 128)
                if end < 0:
                    continue
                imports.append(data[name_off:end].decode("ascii", "replace"))
    clr = directory(14)
    return PeInfo(
        True,
        "",
        machine,
        MACHINES.get(machine, f"unknown_{machine:#x}"),
        pe32plus,
        bool(characteristics & 0x2000),
        bool(clr and clr[0] and clr[1]),
        imports,
        [s["name"] for s in parsed_sections],
        strings,
    )


def synthesize_pe(
    machine: int,
    imports: list[str] | None = None,
    dotnet: bool = False,
    dll: bool = False,
    extra_ascii: str = "",
) -> bytes:
    """Build a minimal PE for tests. Not a real executable."""
    imports = imports or []
    blob = bytearray(0x400 + 0x800)
    blob[0:2] = b"MZ"
    struct.pack_into("<I", blob, 0x3C, 0x80)
    struct.pack_into("<I", blob, 0x80, 0x00004550)
    struct.pack_into("<H", blob, 0x84, machine)
    struct.pack_into("<H", blob, 0x86, 1)
    struct.pack_into("<H", blob, 0x94, 240)
    struct.pack_into("<H", blob, 0x96, 0x2102 if dll else 0x22)
    opt = 0x98
    struct.pack_into("<H", blob, opt, 0x20B)
    struct.pack_into("<Q", blob, opt + 24, 0x140000000)
    struct.pack_into("<I", blob, opt + 32, 0x1000)
    struct.pack_into("<I", blob, opt + 36, 0x200)
    struct.pack_into("<I", blob, opt + 56, 0x2000)
    struct.pack_into("<I", blob, opt + 60, 0x400)
    struct.pack_into("<H", blob, opt + 68, 3)
    struct.pack_into("<I", blob, opt + 108, 16)
    va, raw = 0x1000, 0x400
    if imports:
        struct.pack_into("<I", blob, opt + 112 + 8, va)
        struct.pack_into("<I", blob, opt + 112 + 12, (len(imports) + 1) * 20)
    if dotnet:
        struct.pack_into("<I", blob, opt + 112 + 14 * 8, va + 0x700)
        struct.pack_into("<I", blob, opt + 112 + 14 * 8 + 4, 72)
    sec = opt + 240
    blob[sec : sec + 6] = b".rdata"
    struct.pack_into("<I", blob, sec + 8, 0x800)
    struct.pack_into("<I", blob, sec + 12, va)
    struct.pack_into("<I", blob, sec + 16, 0x800)
    struct.pack_into("<I", blob, sec + 20, raw)
    name_cursor = 0x180
    for index, dll_name in enumerate(imports):
        encoded = dll_name.encode("ascii")
        blob[raw + name_cursor : raw + name_cursor + len(encoded)] = encoded
        desc = index * 20
        hint = 0x400 + index * 64
        struct.pack_into("<I", blob, raw + desc, va + 0x200 + index * 16)
        struct.pack_into("<I", blob, raw + desc + 12, va + name_cursor)
        struct.pack_into("<I", blob, raw + desc + 16, va + 0x300 + index * 16)
        name_cursor += len(encoded) + 1
        struct.pack_into("<I", blob, raw + 0x200 + index * 16, va + hint)
        blob[raw + hint + 2 : raw + hint + 2 + len(encoded)] = encoded
    if extra_ascii:
        encoded = extra_ascii.encode("ascii")
        blob[raw + 0x600 : raw + 0x600 + len(encoded)] = encoded
    return bytes(blob)
