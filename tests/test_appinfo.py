from pathlib import Path
import struct

from steam_game_list_exporter.appinfo import APPINFO_MAGIC_V41, read_apps


def _entry(appid: int, name: str, app_type: str) -> bytes:
    keys = {"appinfo": 0, "common": 1, "name": 2, "type": 3}
    vdf = bytearray()
    vdf += b"\x00" + struct.pack("<I", keys["appinfo"])
    vdf += b"\x00" + struct.pack("<I", keys["common"])
    vdf += b"\x01" + struct.pack("<I", keys["name"]) + name.encode() + b"\0"
    vdf += b"\x01" + struct.pack("<I", keys["type"]) + app_type.encode() + b"\0"
    vdf += b"\x08\x08\x08"
    size = 60 + len(vdf)
    return struct.pack("<II", appid, size) + bytes(60) + vdf


def _fixture(path: Path) -> None:
    entries = _entry(10, "Counter-Strike", "game") + _entry(20, "A Tool", "tool")
    table_offset = 16 + len(entries)
    table = struct.pack("<I", 4) + b"appinfo\0common\0name\0type\0"
    path.write_bytes(struct.pack("<IIQ", APPINFO_MAGIC_V41, 1, table_offset) + entries + table)


def test_reads_only_wanted_games(tmp_path: Path) -> None:
    path = tmp_path / "appinfo.vdf"
    _fixture(path)
    apps = read_apps(path, {10, 20})
    assert [(app.appid, app.name) for app in apps] == [(10, "Counter-Strike")]


def test_respects_wanted_ids(tmp_path: Path) -> None:
    path = tmp_path / "appinfo.vdf"
    _fixture(path)
    assert read_apps(path, {999}) == []
