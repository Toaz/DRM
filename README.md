# De Re Militari – map of channel posts

An interactive map built from the posts of the public Telegram channel **@drmjournal**.
GitHub Actions reads new posts three times a day, rebuilds the page and publishes it on GitHub Pages.
The map is one static HTML file: no server, no database, and **no Telegram login or secret of any kind**.

```
.github/workflows/update.yml   schedule: pull -> commit data -> build -> deploy
.github/workflows/test.yml     runs the tests on pull requests and non-main pushes
src/web.py                     reads the public preview https://t.me/s/<channel> (no login)
src/pull.py                    posts -> data/result_DD.MM.YYYY.json (one file per day)
src/build.py                   data/*.json -> site/index.html
src/place.py, cats.py          rules: location, attacker/target, categories
data/result_old.json           the archive up to 12.10.2026 (slimmed export)
data/result_13.10.2026.json    ...one file per day from now on (created by the workflow)
data/curated.json              103 hand-placed posts
assets/, template/             map shapes and the page template
tests/                         offline tests;  tools/  helper scripts
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
There is nothing to steal: the project needs no password, API key or Telegram session, and the repository contains only public posts and code.
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

## Good to know
* This reads the **public preview** of the channel. It works only while the channel is public and the preview is enabled, and it depends on
  the layout of that page. Be gentle: it makes about 3–5 requests per run, one per second, which is what a person scrolling would cause.
  If Telegram changes the page, the workflow fails and you get GitHub's failure e-mail; the map just stays as it was.
* GitHub may delay scheduled runs and **switches schedules off after 60 days without repository activity**. The daily data commits should keep it alive;
  if the schedule stops, re-enable it in the Actions tab. Cron is in UTC, so local run times shift by an hour when the clocks change.
* Edits or deletions of posts older than two days are not picked up (use *Run workflow* with a `from_date` to refresh older days; very long backfills may need `MAX_PAGES`).
* Locations, categories and the attacker→target arrows come from keyword rules, not from understanding the text. They are right most of the time and wrong sometimes (see `src/place.py`).

## Optional: read through the Telegram API instead
Only if the preview stops working. It needs a Telegram login, which is **full access to that account**, so use a dedicated account if you can.
`pip install -r requirements-api.txt`, create the session with `python tools/make_session.py`, store `TG_API_ID`, `TG_API_HASH`, `TG_SESSION` as
**environment secrets** (restricted to `main`), pass them to the pull step in `update.yml` and set `SOURCE: api`.
