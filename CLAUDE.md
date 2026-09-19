# TwitchClipMatchFinder

## What this is

Given a Twitch clip (or YouTube video) of someone playing Dota 2, this tool identifies
which Dota match the clip is from by:
1. Extracting the first video frame of the clip.
2. Using OpenCV template matching to identify the 10 heroes shown in the top hero bar
   of the frame (and their team side / slot order).
3. Querying the OpenDota `findMatches` API for matches with that exact hero
   composition/side.
4. Picking the candidate match whose `start_time` is the closest one before the clip's
   creation timestamp.

A Reddit bot (`redditbot.py`) runs this automatically against new posts on r/dota2 that
link Twitch clips, and replies with the match id and links (OpenDota/Dotabuff/Stratz/
datdota). Live bot: [/u/DotaClipMatchFinder](https://www.reddit.com/user/DotaClipMatchFinder).

See `README.md` for a full example of the CLI output and reasoning.

## Entry points

- **`finder.py`** — core matching library, also runnable directly:
  ```
  python finder.py <clip_slug>                  # twitch clip slug (end of clips.twitch.tv/<slug> url)
  python finder.py <youtube_url>                # also supports youtube.com / youtu.be urls
  python finder.py <path/to/image.png>           # run against a local image file directly
  python finder.py <slug> -superdebug            # also dumps intermediate debug images to superdebug/
  ```
  Programmatic use: `finder.find_match(slug)`, `finder.find_match_from_youtube(url)`,
  `finder.find_match_from_file(path)`.
- **`redditbot.py`** — the long-running bot: `python redditbot.py`. Polls r/dota2 every
  10 minutes (searches `site:twitch.tv`), runs `finder.find_match` on new clip links, and
  replies on Reddit with the result (unless `debug` is set in config, in which case it
  only prints instead of posting/commenting).
- **`updatearcanalinks.py`** — one-off/offline generator script for
  `data/arcana_links.json`. Requires a local Dota VPK extract and a parsed
  `items_game` file (a side-product of `dotabase-builder`, not part of this repo) —
  paths configured via `config.json`'s `arcanascript` section. Not part of the normal
  runtime path.

## Architecture

- `finder.py` is the standalone matching engine — no dependency on Reddit/praw. It owns:
  Twitch Helix API auth/calls, clip download + frame extraction (OpenCV), the hero
  template-matching algorithm, and the OpenDota `findMatches`/`matches` API calls.
- `redditbot.py` imports `finder` and adds the Reddit polling/posting loop (via `praw`).
  It has no matching logic of its own — it just orchestrates when `finder.find_match` is
  called and what to do with results/errors.
- `updatearcanalinks.py` is independent tooling that regenerates `data/arcana_links.json`
  (consumed by `finder.py`) from raw Dota game files. It uses the `dotabase` library
  directly but does not import `finder.py` or `redditbot.py`.
- The `dotabase` package (external pip dependency, `dotabase>=4.7.0`) supplies the list
  of Dota heroes and their base icon image paths (`Hero.image`) via a SQLite-backed
  session (`dotabase_session()`).

## Config (`config.json`, repo root — gitignored, not committed)

Not printing actual values (file exists locally and is blocked from being read/shown).
Shape, based on `README.md` and code references (`config["..."]` lookups in
`finder.py`/`redditbot.py`/`updatearcanalinks.py`):

```
{
  "twitch": {
    "client_id": "...",
    "client_secret": "..."
  },
  "reddit": {
    "client_id": "...",
    "client_secret": "...",
    "user_agent": "...",
    "username": "...",
    "password": "..."
  },
  "debug": false,                 // optional; redditbot.py — if true, prints instead of posting/commenting, and uses a wider reddit search time_filter ("week" vs "day")
  "healthchecks_url": "...",      // optional; redditbot.py pings this (POST) once per poll loop if present
  "arcanascript": {                // only needed to run updatearcanalinks.py
    "items_game_path": "...",     // path to a parsed items_game json
    "vpk_path": "..."             // path to an extracted Dota vpk
  }
}
```

`docker-compose.yml` also mounts a `./containers.json` into the container, but no such
file exists in this repo checkout and nothing in the Python code reads it — likely a
stale/deploy-environment-only artifact worth confirming before relying on it.

## Data files

- **`data/arcana_links.json`** — maps Dota hero id (string) → list of VPK image paths
  for alternate hero appearances (arcanas/personas that change the hero icon). Generated
  by `updatearcanalinks.py`. `finder.py` loads this at import time and adds these as
  extra template images per hero (`HeroMatch.add_image`) so arcana/persona skins are
  still matched correctly.
- **`cache/`** (gitignored, runtime cache, created if missing) — per Twitch-clip-slug
  files: `<slug>.json` (Twitch Helix clip metadata), `<slug>.mp4` (downloaded clip),
  `<slug>.png` (extracted first frame). Also `<match_id>.json` (cached OpenDota match
  detail responses, used to enrich replies with league/team names). `cache/vpk/` holds
  hero template images downloaded from `http://dotabase.dillerm.io/dota-vpk` (mirrors
  the VPK path structure). `redditbot.py`'s loop calls `clean_data_cache("cache", 7)`
  each iteration to delete cache files older than 7 days.
- **`superdebug/`** — only populated when `SUPERDEBUG` is enabled (`-superdebug` CLI
  flag): `first_frame.png` (raw extracted frame), `herobar.png` (cropped hero-bar region
  used for template matching), `normalbar.png` (older/other debug dump — not currently
  written by any code path found in `finder.py`, may be stale).
- **`temp/`** — gitignored, appears to be legacy/deprecated scripts from ~2019
  (`clipprocessing.py`, `dothing.py`, `prepare.py`, `local_prepare.py`, `notes.md`), not
  imported or referenced by any current code. Treat as historical scratch, not live code.

## Tests

`tests/test.py` is a standalone script (not pytest-based — no test framework, just a
`__main__` block):
```
python tests/test.py           # run all cases in tests/testdata.json, print ✔️/❌ per clip
python tests/test.py add <slug>  # download a new clip's first frame into tests/images/
                                  # and append an expected-heroes entry to testdata.json
```
`tests/testdata.json` holds one entry per test clip: `slug`, expected `heroes` (dotabase
hero internal names, in detected slot order 0-9), and optionally `match_id` to also
assert the full match lookup. `tests/images/*.png` are pre-extracted first frames so
tests don't need to hit Twitch/download mp4s. Failures print which heroes were expected
vs found, plus extended score/position debug info.

## Notable conventions / gotchas

- `finder_y_tolerance = 4` and `finder_x_tolerance = 18` (top of `finder.py`) control how
  strict slot-position matching is; `finder_x_tolerance` was recently adjusted per git
  history ("adjusted x tolerance").
- The OpenDota `findMatches` timestamp cutoff: clips created before Unix time
  `1555200000` (~April 2019) raise `MatchTooEarlyException` — the API doesn't have data
  that far back.
- Twitch's old "kraken" API (v5) is referenced in `notes.md` as early scratch notes but
  the current code uses the newer "helix" API. A comment in `finder.py`
  (`find_match_with_info`) notes the helix API dropped the VOD `offset` field, so a more
  precise "better_minutes_diff" (based on VOD timestamp) can no longer be computed —
  that code path is commented out.
- `requirements.txt` pins `youtube-dl` (used only for the YouTube-URL support path in
  `finder.py`); this project is largely unmaintained upstream in favor of `yt-dlp`, worth
  checking if YouTube support breaks.
- Reference resolution for hero-bar layout is a 2160px-tall (4K) image; `hero_positions`
  and crop math scale from that baseline via `image_ratio = image.height / 2160`.
- `python-3.8` base image in `Dockerfile`; installs `ffmpeg libsm6 libxext6` as OpenCV/
  video prerequisites.
- `redditbot.py` catches `prawcore.exceptions.ServerError`/`ResponseException` per loop
  iteration and just skips that cycle; also backs off entirely (returns from
  `bot_check_posts`, retries next 10-min loop) if Reddit rate-limits a reply.

## Docker

`docker-compose.yml` builds from `Dockerfile` (base `python:3.8`), mounts
`config.json`, `containers.json` (see config note above), and `cache/` as volumes, and
runs `python -u redditbot.py` as the container command.
