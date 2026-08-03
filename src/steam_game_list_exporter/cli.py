"""Command-line interface for Steam Game List Exporter."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .appinfo import AppInfoError, SteamApp, read_apps


def find_steam_directory(explicit: Path | None = None) -> Path:
    """Find a Steam installation, preferring an explicit path."""
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if path.is_dir():
            return path
        raise FileNotFoundError(f"Steam directory does not exist: {path}")

    candidates: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg

            registry_keys = (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
            )
            for hive, key, value_name in registry_keys:
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        candidates.append(Path(winreg.QueryValueEx(handle, value_name)[0]))
                except OSError:
                    pass
        except ImportError:
            pass
        if os.environ.get("ProgramFiles(x86)"):
            candidates.append(Path(os.environ["ProgramFiles(x86)"]) / "Steam")
        if os.environ.get("ProgramFiles"):
            candidates.append(Path(os.environ["ProgramFiles"]) / "Steam")
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library/Application Support/Steam")
    else:
        candidates.extend(
            [
                Path.home() / ".steam/steam",
                Path.home() / ".local/share/Steam",
                Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam",
            ]
        )

    for candidate in candidates:
        if (candidate / "appcache/appinfo.vdf").is_file():
            return candidate.resolve()
    raise FileNotFoundError("Steam installation was not found; pass --steam-dir explicitly")


def library_app_ids(steam_directory: Path) -> set[int]:
    """Return app IDs in Steam's merged local library cache."""
    cache = steam_directory / "appcache/librarycache"
    if not cache.is_dir():
        raise FileNotFoundError(
            f"Steam library cache was not found at {cache}. Open Steam's Library tab and try again."
        )
    ids = {int(item.name) for item in cache.iterdir() if item.is_dir() and item.name.isdigit()}
    if not ids:
        raise RuntimeError("Steam's library cache is empty; open the Library tab and let it load")
    return ids


def write_games(games: list[SteamApp], output: Path, output_format: str, include_appid: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        records = [
            ({"name": game.name, "appid": game.appid} if include_appid else {"name": game.name})
            for game in games
        ]
        output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    if include_appid:
        lines = [f"{game.name}\t{game.appid}" for game in games]
    else:
        lines = [game.name for game in games]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="steam-game-list",
        description="Export every game in the local Steam library, including Steam Families games.",
    )
    parser.add_argument("-o", "--output", type=Path, default=Path("steam-games.txt"), help="output file")
    parser.add_argument("--steam-dir", type=Path, help="Steam installation directory")
    parser.add_argument("--format", choices=("text", "tsv", "json"), default="text")
    parser.add_argument("--include-appid", action="store_true", help="include each Steam AppID")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        steam_directory = find_steam_directory(args.steam_dir)
        ids = library_app_ids(steam_directory)
        games = sorted(
            read_apps(steam_directory / "appcache/appinfo.vdf", ids),
            key=lambda game: (game.name.casefold(), game.appid),
        )
        if not games:
            raise RuntimeError("No games could be matched in Steam's local metadata")
        write_games(games, args.output.resolve(), args.format, args.include_appid)
    except (AppInfoError, FileNotFoundError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Exported {len(games)} games to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
