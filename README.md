# Steam Game List Exporter

Export every game visible in your desktop Steam library to a text, TSV, or JSON file, including games shared through **Steam Families**.

The tool reads Steam's local library and metadata caches. It needs no Steam Web API key, makes no network requests, and excludes dedicated servers, SDKs, compatibility runtimes, and other non-game tools.

## Requirements

- Python 3.10 or newer
- The desktop Steam client with its Library tab loaded at least once

Windows, Linux, and macOS Steam locations are detected automatically. You can also provide a custom location.

## Install

The quickest installation uses [pipx](https://pipx.pypa.io/):

```console
pipx install git+https://github.com/aesxsc/steam-game-list-exporter.git
```

Or clone it and install into a virtual environment:

```console
git clone https://github.com/aesxsc/steam-game-list-exporter.git
cd steam-game-list-exporter
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

On Linux or macOS:

```bash
source .venv/bin/activate
python -m pip install -e .
```

## Usage

Export an alphabetical text file with a compact completion field:

```console
steam-game-list
```

The default destination is `steam-games.txt` in the current directory. Completion uses achievement progress when available and falls back to lifetime playtime when the game has no achievement data.

Export names only, matching the original behavior:

```console
steam-game-list --no-completion
```

Choose a destination:

```console
steam-game-list --output my-steam-games.txt
```

Export every available metric as an analysis-friendly TSV file:

```console
steam-game-list --format tsv --all-metrics --include-appid --output steam-games.tsv
```

Or export the same data as JSON:

```console
steam-game-list --format json --all-metrics --include-appid --output steam-games.json
```

Metrics can also be enabled independently:

```console
steam-game-list --achievements --playtime --output progress.txt
steam-game-list --activity --installed --format tsv --output activity.tsv
```

| Option | Added data |
| --- | --- |
| `--achievements` | Unlocked achievements, total achievements, and completion percentage |
| `--playtime` | Lifetime minutes/hours and playtime from the last two weeks |
| `--activity` | First and last played timestamps, when present in Steam's cache |
| `--installed` | Whether the game is currently installed |
| `--all-metrics` | All four groups above |
| `--no-completion` | Removes the default achievement/playtime completion summary |

Timestamps use ISO 8601 UTC. Steam normally stores last-played time locally, but often does not store first-played time; unavailable values are blank in text/TSV and `null` in JSON.

If more than one Steam account uses the computer, select one by account name, account ID, or SteamID64:

```console
steam-game-list --user account-name --all-metrics --format json
```

Use a nonstandard Steam installation:

```console
steam-game-list --steam-dir "D:\Steam"
```

You can also run the package without installing its command:

```console
python -m steam_game_list_exporter --help
```

## How it works

Steam stores the app IDs visible to the signed-in user's merged library under `appcache/librarycache`. That includes eligible games from Steam Families. The exporter matches those IDs against `appcache/appinfo.vdf`, keeps entries whose Steam type is `game`, and writes their display names in alphabetical order.

Per-user achievement data comes from `userdata/<account>/config/librarycache`; playtime and activity come from `localconfig.vdf`; installation status comes from `libraryfolders.vdf`. Metrics are local-cache snapshots and can be absent for games that have never loaded their metadata on that account.

The cache reflects the currently loaded Steam library. If a newly shared or purchased game is missing, open Steam's Library tab, wait for it to refresh, and run the exporter again.

## Development

```console
python -m pip install -e . pytest
pytest
```

## License

[WTFPL](LICENSE)
