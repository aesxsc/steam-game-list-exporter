"""Read per-user statistics from Steam's local text and JSON caches."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys


@dataclass(slots=True)
class GameStats:
    achievements_unlocked: int | None = None
    achievements_total: int | None = None
    achievement_percent: float | None = None
    playtime_minutes: int | None = None
    recent_playtime_minutes: int | None = None
    first_played: int | None = None
    last_played: int | None = None
    installed: bool = False


_TOKEN = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])')


def _unescape(value: str) -> str:
    return re.sub(r'\\([\\"])', r'\1', value)


def parse_text_vdf(text: str) -> dict[str, object]:
    """Parse the subset of Valve's text VDF used by Steam configuration files."""
    tokens: list[str] = []
    for match in _TOKEN.finditer(text):
        tokens.append(match.group(2) or _unescape(match.group(1)))

    position = 0

    def parse_object(expect_close: bool = False) -> dict[str, object]:
        nonlocal position
        result: dict[str, object] = {}
        while position < len(tokens):
            token = tokens[position]
            position += 1
            if token == "}":
                if not expect_close:
                    raise ValueError("Unexpected closing brace in VDF")
                return result
            if token == "{":
                raise ValueError("Unexpected opening brace in VDF")
            if position >= len(tokens):
                raise ValueError("Missing value in VDF")
            value = tokens[position]
            position += 1
            if value == "{":
                result[token] = parse_object(expect_close=True)
            elif value == "}":
                raise ValueError("Missing value before closing brace in VDF")
            else:
                result[token] = value
        if expect_close:
            raise ValueError("Unclosed object in VDF")
        return result

    return parse_object()


def _read_vdf(path: Path) -> dict[str, object]:
    return parse_text_vdf(path.read_text(encoding="utf-8", errors="replace"))


def _integer(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def find_user_directory(steam_directory: Path, requested_user: str | None = None) -> Path:
    """Find the active Steam userdata directory or resolve an explicit user."""
    userdata = steam_directory / "userdata"
    if not userdata.is_dir():
        raise FileNotFoundError(f"Steam userdata directory was not found at {userdata}")

    login_path = steam_directory / "config/loginusers.vdf"
    users: dict[str, object] = {}
    if login_path.is_file():
        parsed = _read_vdf(login_path)
        candidate = parsed.get("users")
        if isinstance(candidate, dict):
            users = candidate

    if requested_user:
        normalized = requested_user.casefold()
        for steamid, details in users.items():
            account_id = str(int(steamid) & 0xFFFFFFFF) if steamid.isdigit() else steamid
            account_name = details.get("AccountName", "") if isinstance(details, dict) else ""
            if normalized in (steamid.casefold(), account_id.casefold(), str(account_name).casefold()):
                path = userdata / account_id
                if path.is_dir():
                    return path
        direct = userdata / requested_user
        if direct.is_dir():
            return direct
        raise FileNotFoundError(f"Steam user was not found: {requested_user}")

    ranked: list[tuple[int, int, Path]] = []
    for steamid, details in users.items():
        if not steamid.isdigit() or not isinstance(details, dict):
            continue
        account_id = str(int(steamid) & 0xFFFFFFFF)
        path = userdata / account_id
        if path.is_dir():
            preferred = int(details.get("MostRecent", "0") == "1") * 2 + int(
                details.get("AutoLogin", "0") == "1"
            )
            ranked.append((preferred, _integer(details.get("Timestamp")) or 0, path))
    if ranked:
        return max(ranked, key=lambda item: (item[0], item[1]))[2]

    local_configs = list(userdata.glob("*/config/localconfig.vdf"))
    if local_configs:
        return max(local_configs, key=lambda path: path.stat().st_mtime).parents[1]
    raise FileNotFoundError("No Steam user with a local configuration was found")


def _local_app_stats(user_directory: Path) -> dict[int, GameStats]:
    path = user_directory / "config/localconfig.vdf"
    if not path.is_file():
        return {}
    parsed = _read_vdf(path)
    def app_sections(value: object):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.casefold() == "apps" and isinstance(child, dict):
                    yield child
                else:
                    yield from app_sections(child)

    apps = {}
    for section in app_sections(parsed):
        for appid, fields in section.items():
            if isinstance(fields, dict):
                normalized = {key.casefold(): value for key, value in fields.items()}
                if any(key in normalized for key in (
                    "playtime", "playtime2wks", "firstplayed", "lastplayed"
                )):
                    apps.setdefault(appid, {}).update(normalized)

    result: dict[int, GameStats] = {}
    for appid_text, values in apps.items():
        if not appid_text.isdigit() or not isinstance(values, dict):
            continue
        stats = GameStats()
        stats.playtime_minutes = _integer(values.get("playtime"))
        stats.recent_playtime_minutes = _integer(values.get("playtime2wks"))
        stats.first_played = _integer(values.get("firstplayed"))
        stats.last_played = _integer(values.get("lastplayed"))
        result[int(appid_text)] = stats
    return result


def _read_cache_sections(path: Path) -> list[list[object]]:
    """Read Steam cache sections, including concatenated JSON values.

    Steam can store an array of section pairs followed immediately by more
    section pairs (each its own valid JSON value). ``json.loads`` rejects the
    extra values, so decode each in turn and normalize them into one list.
    """
    content = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    sections: list[list[object]] = []
    position = 0

    while position < len(content):
        while position < len(content) and content[position].isspace():
            position += 1
        if position == len(content):
            break

        try:
            value, position = decoder.raw_decode(content, position)
        except json.JSONDecodeError:
            # A valid prefix may contain complete achievement data even when
            # Steam appends an incomplete or malformed JSON value afterward.
            if not sections:
                raise
            break
        if not isinstance(value, list):
            continue

        # A single section pair: ["achievements", {"version": ..., "data": ...}]
        if len(value) == 2 and isinstance(value[0], str):
            sections.append(value)
        else:
            # A collection of section pairs: [["achievements", {...}], ...]
            sections.extend(
                section
                for section in value
                if isinstance(section, list)
                and len(section) == 2
                and isinstance(section[0], str)
            )

    return sections


def _add_achievements(user_directory: Path, result: dict[int, GameStats]) -> None:
    cache = user_directory / "config/librarycache"
    if not cache.is_dir():
        return

    for path in cache.glob("*.json"):
        if not path.stem.isdigit():
            continue

        try:
            records = _read_cache_sections(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue

        # Collect all valid achievement counts, regardless of section order.
        by_total: dict[int, int] = {}

        for record in records:
            if record[0] != "achievements":
                continue

            wrapper = record[1]
            data = wrapper.get("data", {}) if isinstance(wrapper, dict) else {}
            if not isinstance(data, dict):
                continue

            total = _integer(data.get("nTotal"))
            unlocked = _integer(data.get("nAchieved"))

            if (
                total is None
                or unlocked is None
                or total <= 0
                or not 0 <= unlocked <= total
            ):
                continue

            by_total[total] = max(by_total.get(total, -1), unlocked)

        # Different totals may indicate changed achievement schemas.
        # Don't guess which one is current.
        if len(by_total) > 1:
            print(
                f"Warning: conflicting achievement totals in {path}: {sorted(by_total)}",
                file=sys.stderr,
            )
            continue

        if by_total:
            total, unlocked = next(iter(by_total.items()))
            stats = result.setdefault(int(path.stem), GameStats())
            stats.achievements_total = total
            stats.achievements_unlocked = unlocked
            stats.achievement_percent = round(unlocked * 100 / total, 1)


def installed_app_ids(steam_directory: Path) -> set[int]:
    """Read installed app IDs recorded in libraryfolders.vdf."""
    paths = [
        steam_directory / "config/libraryfolders.vdf",
        steam_directory / "steamapps/libraryfolders.vdf",
    ]
    path = next((candidate for candidate in paths if candidate.is_file()), None)
    if path is None:
        return set()
    parsed = _read_vdf(path)
    installed: set[int] = set()

    def visit(value: object, parent: str = "") -> None:
        if not isinstance(value, dict):
            return
        if parent.casefold() == "apps":
            installed.update(int(key) for key in value if key.isdigit())
        for key, child in value.items():
            visit(child, key)

    visit(parsed)
    return installed


def read_user_stats(
    steam_directory: Path, wanted_ids: set[int], requested_user: str | None = None
) -> tuple[dict[int, GameStats], Path]:
    """Read playtime, activity, achievements, and installation state."""
    user_directory = find_user_directory(steam_directory, requested_user)
    result = _local_app_stats(user_directory)
    _add_achievements(user_directory, result)
    installed = installed_app_ids(steam_directory)
    for appid in wanted_ids:
        result.setdefault(appid, GameStats()).installed = appid in installed
    return result, user_directory


def iso_time(timestamp: int | None) -> str | None:
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None
