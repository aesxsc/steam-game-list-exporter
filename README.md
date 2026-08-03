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

Export an alphabetical, names-only text file:

```console
steam-game-list
```

The default destination is `steam-games.txt` in the current directory.

Choose a destination:

```console
steam-game-list --output my-steam-games.txt
```

Include AppIDs in a tab-separated file:

```console
steam-game-list --format tsv --include-appid --output steam-games.tsv
```

Export JSON:

```console
steam-game-list --format json --include-appid --output steam-games.json
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

The cache reflects the currently loaded Steam library. If a newly shared or purchased game is missing, open Steam's Library tab, wait for it to refresh, and run the exporter again.

## Development

```console
python -m pip install -e . pytest
pytest
```

## License

[WTFPL](LICENSE)
