"""Minimal reader for Steam's binary appinfo.vdf formats."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct


APPINFO_MAGIC_V40 = 0x07564428
APPINFO_MAGIC_V41 = 0x07564429
ENTRY_HEADER_SIZE = 68
HEADER_AFTER_SIZE = 60


class AppInfoError(ValueError):
    """Raised when appinfo.vdf is missing, corrupt, or unsupported."""


@dataclass(frozen=True, slots=True)
class SteamApp:
    appid: int
    name: str
    type: str


class _Reader:
    def __init__(self, data: bytes, position: int = 0, string_table: list[str] | None = None):
        self.data = data
        self.position = position
        self.string_table = string_table

    def require(self, size: int) -> None:
        if self.position + size > len(self.data):
            raise AppInfoError("Unexpected end of appinfo.vdf")

    def u8(self) -> int:
        self.require(1)
        value = self.data[self.position]
        self.position += 1
        return value

    def u32(self) -> int:
        self.require(4)
        value = struct.unpack_from("<I", self.data, self.position)[0]
        self.position += 4
        return value

    def u64(self) -> int:
        self.require(8)
        value = struct.unpack_from("<Q", self.data, self.position)[0]
        self.position += 8
        return value

    def cstring(self) -> str:
        end = self.data.find(b"\0", self.position)
        if end < 0:
            raise AppInfoError("Unterminated string in appinfo.vdf")
        value = self.data[self.position:end].decode("utf-8", errors="replace")
        self.position = end + 1
        return value

    def wstring(self) -> str:
        start = self.position
        while self.position + 1 < len(self.data):
            if self.data[self.position : self.position + 2] == b"\0\0":
                value = self.data[start:self.position].decode("utf-16-le", errors="replace")
                self.position += 2
                return value
            self.position += 2
        raise AppInfoError("Unterminated wide string in appinfo.vdf")

    def key(self) -> str:
        if self.string_table is None:
            return self.cstring()
        index = self.u32()
        try:
            return self.string_table[index]
        except IndexError as exc:
            raise AppInfoError(f"Invalid appinfo.vdf string-table index: {index}") from exc


def _read_object(reader: _Reader, end: int, path: tuple[str, ...], found: dict[str, str]) -> None:
    while reader.position < end:
        value_type = reader.u8()
        if value_type == 8:
            return

        key = reader.key()
        if value_type == 0:
            _read_object(reader, end, (*path, key), found)
            continue

        value: str | None = None
        if value_type == 1:
            value = reader.cstring()
        elif value_type in (2, 3, 4, 6):
            reader.require(4)
            reader.position += 4
        elif value_type == 5:
            value = reader.wstring()
        elif value_type == 7:
            reader.require(8)
            reader.position += 8
        else:
            raise AppInfoError(
                f"Unknown binary VDF value type {value_type} at offset {reader.position - 1}"
            )

        if path == ("appinfo", "common") and value is not None and key in ("name", "type"):
            found[key] = value
        if reader.position > end:
            raise AppInfoError("A value extends beyond its appinfo.vdf entry")


def read_apps(path: Path, wanted_ids: set[int]) -> list[SteamApp]:
    """Read metadata for selected app IDs from appinfo.vdf."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise AppInfoError(f"Could not read {path}: {exc}") from exc

    reader = _Reader(data)
    magic = reader.u32()
    reader.u32()  # Steam universe

    apps_end = len(data)
    string_table: list[str] | None = None
    if magic == APPINFO_MAGIC_V41:
        apps_end = reader.u64()
        if apps_end >= len(data):
            raise AppInfoError("Invalid appinfo.vdf string-table offset")
        table_reader = _Reader(data, apps_end)
        count = table_reader.u32()
        string_table = [table_reader.cstring() for _ in range(count)]
    elif magic != APPINFO_MAGIC_V40:
        raise AppInfoError(f"Unsupported appinfo.vdf format: 0x{magic:08X}")

    reader.string_table = string_table
    apps: list[SteamApp] = []
    while reader.position + ENTRY_HEADER_SIZE <= apps_end:
        entry_start = reader.position
        appid = reader.u32()
        if appid == 0:
            break
        size = reader.u32()
        if size < HEADER_AFTER_SIZE:
            raise AppInfoError(f"Invalid appinfo.vdf entry size for AppID {appid}")
        entry_end = entry_start + 8 + size
        if entry_end > apps_end:
            raise AppInfoError(f"AppID {appid} extends beyond appinfo.vdf")

        if appid in wanted_ids:
            reader.position = entry_start + ENTRY_HEADER_SIZE
            found: dict[str, str] = {}
            _read_object(reader, entry_end, (), found)
            if found.get("name") and found.get("type", "").casefold() == "game":
                apps.append(SteamApp(appid, found["name"], found["type"]))
        reader.position = entry_end

    return apps
