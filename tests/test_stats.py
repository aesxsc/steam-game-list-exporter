from pathlib import Path

from steam_game_list_exporter.stats import (
    find_user_directory,
    installed_app_ids,
    parse_text_vdf,
    read_user_stats,
)


def test_parse_nested_text_vdf() -> None:
    parsed = parse_text_vdf('"root" { "child" { "value" "42" } }')
    assert parsed == {"root": {"child": {"value": "42"}}}


def _steam_fixture(root: Path) -> Path:
    (root / "config").mkdir(parents=True)
    (root / "config/loginusers.vdf").write_text(
        '"users" { "76561199064595157" { "AccountName" "tester" "AutoLogin" "1" } }',
        encoding="utf-8",
    )
    user = root / "userdata/1104329429"
    (user / "config/librarycache").mkdir(parents=True)
    (user / "config/localconfig.vdf").write_text(
        '"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" {'
        ' "10" { "Playtime" "150" "Playtime2wks" "30" "LastPlayed" "1700000000" }'
        '} } } } }',
        encoding="utf-8",
    )
    (user / "config/librarycache/10.json").write_text(
        '[["achievements", {"version": 2, "data": {"nTotal": 20, "nAchieved": 5}}]]',
        encoding="utf-8",
    )
    (root / "config/libraryfolders.vdf").write_text(
        '"libraryfolders" { "0" { "apps" { "10" "123" } } }', encoding="utf-8"
    )
    return user


def test_reads_user_metrics(tmp_path: Path) -> None:
    user = _steam_fixture(tmp_path)
    stats, selected_user = read_user_stats(tmp_path, {10})
    assert selected_user == user
    assert stats[10].playtime_minutes == 150
    assert stats[10].recent_playtime_minutes == 30
    assert stats[10].last_played == 1700000000
    assert stats[10].achievements_unlocked == 5
    assert stats[10].achievements_total == 20
    assert stats[10].achievement_percent == 25.0
    assert stats[10].installed is True


def test_resolves_explicit_user_and_installed_apps(tmp_path: Path) -> None:
    user = _steam_fixture(tmp_path)
    assert find_user_directory(tmp_path, "tester") == user
    assert find_user_directory(tmp_path, "76561199064595157") == user
    assert installed_app_ids(tmp_path) == {10}
