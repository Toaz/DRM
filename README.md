# De Re Militari – map of channel posts

An interactive map built from the posts of the public Telegram channel **@drmjournal**.
GitHub Actions reads new posts three times a day, rebuilds the page and publishes it on GitHub Pages.
The map is one static HTML file: no server, no database and **no Telegram login** by default. The only secret is the optional key of the language model (see "Countries and arrows: read by an LLM").

```
.github/workflows/update.yml   schedule: pull -> commit data -> build -> deploy
.github/workflows/test.yml     runs the tests on pull requests and non-main pushes
src/web.py                     reads the public preview https://t.me/s/<channel> (no login)
src/pull.py                    posts -> data/result_DD.MM.YYYY.json (one file per day)
src/build.py                   data/*.json -> site/index.html
src/place.py, cats.py          keyword rules: location, attacker/target, categories (used for posts the model has not read)
src/extract.py, arrows.py      the language model reads each post; its answer becomes arrows
src/geo.py                     the place name the model found -> coordinates (GeoNames cities, inside a trusted country)
data/result_old.json           the archive up to 12.10.2026 (slimmed export)
data/result_13.10.2026.json    ...one file per day from now on (created by the workflow)
data/curated.json              103 hand-placed posts
assets/, template/             map shapes and the page template
tests/                         offline tests;  tools/  helper scripts (tools/audit_map.py measures how reliable the arrows are)
```

## How the data files work
* `result_old.json` is never touched.
* Every run rewrites the files from **yesterday** (or from the last day it knows, if days were missed) up to **today**.
  `result_13.10.2026.json` is overwritten three times during 13.10, then a new file appears for 14.10, and so on.
  Re-running is safe: the same post id never appears twice, and a late post is picked up on the next run.
* Days are cut in the timezone `Europe/Sofia` (set `TZ_NAME` on the pull step in `update.yml` to change it).
* If a post id is in several files, the newest file wins.
* All-or-nothing: the day files are written only after the whole read succeeded. If Telegram changes its page or blocks the
  request, the run **fails visibly** and the existing files are left untouched.

## Setup (about 5 minutes)
1. Create a GitHub repository and upload the contents of this folder (keep `.github/` and the folder names).
2. **Settings → Pages → Source: GitHub Actions.**
3. **Actions → Update map → Run workflow.** The first run fills the gap since the last post in `result_old.json`
   and publishes the page (its address is shown in the *deploy* job and under Settings → Pages).

Before relying on the schedule, check the reader once on your computer: `pip install -r requirements.txt` then
`python src/pull.py --check`. It prints the newest three posts as the parser sees them; compare the ids and times with
the channel. (I could only test the parser on imitated pages, not on the live site.)

## Security
Reading the channel needs no password or Telegram session, and the repository contains only public posts and code. The one secret is the optional `GROQ_API_KEY` (a GitHub Actions secret, never written to the repository). Anyone who can edit the workflow can make it print that key, which is one more reason to review changes to `.github/`.
* Still, anyone with **write access** can change the workflow. Add collaborators carefully and review changes to `.github/` and `src/`.
* The workflow only has `contents: write` (to commit data files) and the Pages permissions. Do not add triggers such as `pull_request_target`.
* Dependencies are pinned in `requirements.txt`; actions are on fixed major versions (for stronger protection pin them to commit SHAs).
* If you protect `main` with required pull requests, allow the *github-actions* bot to push, otherwise the data commit fails.

## Sharing with other people
* Share the Pages link, or the repository (public repositories are readable by everyone).
* Others can fork and run their own copy: fork → Settings → Pages → Source: GitHub Actions → enable Actions.
* GitHub Pages on a **private** repository needs a paid plan. On a free plan use a public repository, or publish `site/` on another host (Netlify, Cloudflare Pages).
* The page shows the first 360 characters of each post and links to the original. Check that you may republish them and keep the link to the channel.

## Run it on your own computer
```
pip install -r requirements.txt
python src/pull.py          # reads new posts into data/ (needs internet)
python src/build.py         # builds site/index.html (works offline)
python -m unittest discover -s tests
```
To use the full original Telegram Desktop export instead of the slim one: `python tools/slim.py path/to/result.json`.

## Countries and arrows: read by an LLM

Each post is read once by a language model (free Groq tier by default). It returns the countries in the post, the country where it happens, a
category and any number of arrows `attacker -> victim` with a confidence. The result is stored in `data/events.json`, one line per post.

- `src/extract.py` does the reading. A post is only sent again if its text was edited; changing the prompt never rewrites old results.
- `src/arrows.py` turns the stored result into map arrows. A post can have several. Weak arrows (physical below 0.7, verbal below 0.9, see
  `SHOW_PHYSICAL` / `SHOW_VERBAL` in `src/extract.py`) stay in the data but are not drawn.
- Posts the model has not read yet still use the old keyword rules in `src/place.py`, so the map is never empty while the backlog is processed.
- Countries are not hard-coded any more for these posts: every country the model finds appears in the country filter and on the map.
  Set `MENTIONED_IN_FILTER = False` in `src/build.py` to filter only by location and arrows.
- Setup: create a free key at console.groq.com, then in GitHub: Settings -> Secrets and variables -> Actions -> New repository secret
  named `GROQ_API_KEY`. Without it the step is skipped and nothing breaks.
- Try it on your computer: `export GROQ_API_KEY=...`, then `python src/extract.py --dry`, then `python src/extract.py --limit 5`.
- Check quality on hard posts: `python tools/llm_probe.py` (cases in `tools/probe_cases.json`; add a case whenever you find a misread post).
- Attacks on ships at sea: when the post names the attacker but no victim country, the arrow goes from the attacker to the exact place found in the post
  (for example the Strait of Hormuz) and is labelled "посоченото място". Without an exact place there is no arrow. Hand-placed posts in `data/curated.json` still win.
- Read one post again (for example after a prompt change): `python src/extract.py --redo 20152`. See the results next to the text: `python tools/show_events.py`.
- Row format of the page data: element 8 is now a list of arrows `[from_lat, from_lon, to_lat, to_lon, label, kind, attacker_iso]` or `null`.

### Exact places
The model also returns `place`: the most specific named city, town or region of the event, in English (`"Kharkiv"`). `src/geo.py` looks it up in the
GeoNames city list that `geonamescache` ships, **only inside a country we already trust** (the post's location or the target of an arrow). If the name is
not found, ambiguous or in the wrong country, nothing changes and the old keyword city list is used. When it is found, the dot and the arrow end sit at
that city ("exact place") instead of somewhere in the country. A place the model names and the keyword list disagrees with by more than 150 km is counted in the
build output (`place: model differs from city list`), so you can look at those posts. Switch it off with `PLACE_FROM_LLM = False` in `src/build.py`.

Posts read before this field existed have no place. To add it, read them again (newest first, within the daily quota):
`python src/extract.py --redo-stale --limit 90`. `--dry` shows how many were read with an older prompt. The old record is only replaced when the new answer arrives.

### How reliable are the arrows?
`python tools/audit_map.py --n 40` writes `data/audit_map.csv`: half drawn arrows, half posts the model gave **no** arrow (leaning towards posts with attack words,
because that is where a missed arrow hides). Open each link, write `y` or `n` in the `ok` column, then `python tools/audit_map.py --score` prints both rates with a
95% interval. Forty correct answers out of forty means "about 91% or better", not "100%", so mark more rows when a number matters.

### On the page
* **Search:** the field in the toolbar filters posts by words in the shown text (the first 360 characters). It combines with every other filter and the counts update.
* **Links:** the address after `#` always holds the filters, period, search and the open post. "Копирай връзка" next to a post copies it; opening such a link restores the same view.
  Editing the address in the same tab applies it too. Unknown or broken values are ignored.

## Good to know
* This reads the **public preview** of the channel. It works only while the channel is public and the preview is enabled, and it depends on
  the layout of that page. Be gentle: it makes about 3–5 requests per run, one per second, which is what a person scrolling would cause.
  If Telegram changes the page, the workflow fails and you get GitHub's failure e-mail; the map just stays as it was.
* GitHub may delay scheduled runs and **switches schedules off after 60 days without repository activity**. The daily data commits should keep it alive;
  if the schedule stops, re-enable it in the Actions tab. Cron is in UTC, so local run times shift by an hour when the clocks change.
* Edits or deletions of posts older than two days are not picked up (use *Run workflow* with a `from_date` to refresh older days; very long backfills may need `MAX_PAGES`).
* For posts the model has read, countries, arrows and exact places come from the model (with guards in `src/extract.py`); for all other posts they come from keyword rules (`src/place.py`). Both are right most of the time and wrong sometimes: measure it with `tools/audit_map.py` instead of guessing.

## Optional: read through the Telegram API instead
Only if the preview stops working. It needs a Telegram login, which is **full access to that account**, so use a dedicated account if you can.
`pip install -r requirements-api.txt`, create the session with `python tools/make_session.py`, store `TG_API_ID`, `TG_API_HASH`, `TG_SESSION` as
**environment secrets** (restricted to `main`), pass them to the pull step in `update.yml` and set `SOURCE: api`.
