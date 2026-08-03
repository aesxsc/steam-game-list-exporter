from steam_game_list_exporter.appinfo import SteamApp
from steam_game_list_exporter.cli import _game_record
from steam_game_list_exporter.stats import GameStats


def test_completion_prefers_achievements() -> None:
    record = _game_record(
        SteamApp(10, "A Game", "game"),
        GameStats(
            achievements_unlocked=5,
            achievements_total=10,
            achievement_percent=50.0,
            playtime_minutes=600,
        ),
        completion=True,
        achievements=False,
        playtime=False,
        activity=False,
        installed=False,
        include_appid=False,
    )
    assert record["completion"] == "5/10 achievements (50.0%)"


def test_completion_falls_back_to_playtime() -> None:
    record = _game_record(
        SteamApp(10, "A Game", "game"),
        GameStats(playtime_minutes=150),
        completion=True,
        achievements=False,
        playtime=False,
        activity=False,
        installed=False,
        include_appid=False,
    )
    assert record["completion"] == "2.5 hours played"
