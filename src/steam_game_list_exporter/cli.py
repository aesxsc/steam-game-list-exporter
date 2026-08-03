"""Command-line interface for Steam Game List Exporter."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from . import __version__
from .appinfo import AppInfoError, SteamApp, read_apps
from .stats import GameStats, iso_time, read_user_stats


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


def _completion(stats: GameStats) -> str | None:
    if stats.achievements_total:
        return (
            f"{stats.achievements_unlocked}/{stats.achievements_total} achievements "
            f"({stats.achievement_percent:.1f}%)"
        )
    if stats.playtime_minutes is not None:
        return f"{stats.playtime_minutes / 60:.1f} hours played"
    return None


def _game_record(
    game: SteamApp,
    stats: GameStats,
    *,
    completion: bool,
    achievements: bool,
    playtime: bool,
    activity: bool,
    installed: bool,
    include_appid: bool,
) -> dict[str, Any]:
    record: dict[str, Any] = {"name": game.name}
    if include_appid:
        record["appid"] = game.appid
    if completion:
        record["completion"] = _completion(stats)
    if achievements:
        record["achievements_unlocked"] = stats.achievements_unlocked
        record["achievements_total"] = stats.achievements_total
        record["achievement_percent"] = stats.achievement_percent
    if playtime:
        record["playtime_minutes"] = stats.playtime_minutes
        record["playtime_hours"] = (
            round(stats.playtime_minutes / 60, 1) if stats.playtime_minutes is not None else None
        )
        record["recent_playtime_minutes"] = stats.recent_playtime_minutes
    if activity:
        record["first_played"] = iso_time(stats.first_played)
        record["last_played"] = iso_time(stats.last_played)
    if installed:
        record["installed"] = stats.installed
    return record


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _human_value(value: Any) -> str:
    return "unknown" if value is None else _text_value(value)


def write_records(records: list[dict[str, Any]], output: Path, output_format: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        text = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    elif output_format == "tsv":
        columns = list(records[0])
        lines = ["\t".join(columns)]
        lines.extend("\t".join(_text_value(record[column]) for column in columns) for record in records)
        text = "\n".join(lines) + "\n"
    elif list(records[0]) == ["name"]:
        text = "\n".join(record["name"] for record in records) + "\n"
    else:
        columns = list(records[0])
        lines = []
        for record in records:
            details = [
                f"{column}={_human_value(record[column])}" for column in columns if column != "name"
            ]
            lines.append(f"{record['name']} | " + " | ".join(details))
        text = "\n".join(lines) + "\n"
    output.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="steam-game-list",
        description="Export every game in the local Steam library, including Steam Families games.",
    )
    parser.add_argument("-o", "--output", type=Path, default=Path("steam-games.txt"), help="output file")
    parser.add_argument("--steam-dir", type=Path, help="Steam installation directory")
    parser.add_argument(
        "--user",
        help="Steam account name, account ID, or SteamID64 (defaults to the active account)",
    )
    parser.add_argument("--format", choices=("text", "tsv", "json"), default="text")
    parser.add_argument("--include-appid", action="store_true", help="include each Steam AppID")
    parser.add_argument(
        "--no-completion",
        action="store_true",
        help="omit the default completion field (achievement progress, then playtime fallback)",
    )
    parser.add_argument(
        "--achievements",
        action="store_true",
        help="include unlocked, total, and percentage achievement columns",
    )
    parser.add_argument(
        "--playtime",
        action="store_true",
        help="include lifetime hours/minutes and recent playtime columns",
    )
    parser.add_argument(
        "--activity",
        action="store_true",
        help="include first and last played timestamps when Steam stores them",
    )
    parser.add_argument("--installed", action="store_true", help="include installation status")
    parser.add_argument(
        "--all-metrics",
        action="store_true",
        help="include achievements, playtime, activity, and installation status",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
        stats_by_app, _user_directory = read_user_stats(steam_directory, ids, args.user)
        records = [
            _game_record(
                game,
                stats_by_app.get(game.appid, GameStats()),
                completion=not args.no_completion,
                achievements=args.achievements or args.all_metrics,
                playtime=args.playtime or args.all_metrics,
                activity=args.activity or args.all_metrics,
                installed=args.installed or args.all_metrics,
                include_appid=args.include_appid,
            )
            for game in games
        ]
        write_records(records, args.output.resolve(), args.format)
    except (AppInfoError, FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Exported {len(games)} games to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
