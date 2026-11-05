# Reality Shift — YouTube Analytics Advisor (`yt_analytics_advisor.py`)

Reads the channel's **real** numbers and turns them into signals for the next Short: which pillar, title style,
length and upload slot are working. Nothing is estimated or invented — a number that isn't available shows as `--`.

## What it shows

| Section | Source | Needs |
|---|---|---|
| Views, likes, upload time (IST), length, multiplier vs median | YouTube Data API v3 | API key (`.env`) |
| Live views/hour since the last run | `snapshots.jsonl` (saved every run) | run it twice, 10+ min apart |
| Pillars, Hinglish vs English titles, length, upload slot | the above, grouped (groups under 3 Shorts are marked *weak*) | API key |
| Average % viewed, avg view duration, subs gained per Short | YouTube Analytics API | one-time `--auth` |
| Shorts views in the last 90 days, long-form watch hours (365 d), daily views | YouTube Analytics API | one-time `--auth` |

"Stayed to watch vs swiped away" is not available in any public API — read it in Studio → Content → the Short.
Analytics API numbers lag 2-3 days behind the live view counts.

Every live run also writes **`advisor_report.json`** (machine-readable; the Short-making pipeline reads it).

## Run

```bash
python yt_analytics_advisor.py            # live channel (or double-click start_advisor.bat)
python yt_analytics_advisor.py --mock     # demo layout with made-up sample data (NOT your channel)
python yt_analytics_advisor.py --data export.csv   # analyze an exported file
```

`.env` needs `YOUTUBE_API_KEY` (and `YOUTUBE_CHANNEL_ID`), see `.env.example`.
If the API fails, the script stops and says why — it never falls back to sample data.

## One-time Analytics setup (free, ~5 minutes)

1. Google Cloud Console → same project as your API key → **APIs & Services → Library** → enable
   **YouTube Analytics API** (YouTube Data API v3 is already on).
2. **APIs & Services → OAuth consent screen** → User type **External** → app name "Reality Shift Advisor",
   your email → Save. Under **Audience / Test users** add the Google account that owns the channel.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID** → Application type
   **Desktop app** → Create → **Download JSON** → save it in this folder as **`client_secret.json`**.
4. Run `python yt_analytics_advisor.py --auth` → a browser opens → pick the channel's account →
   "Google hasn't verified this app" → **Continue** (it's your own app) → **Allow**.
   The login is saved to `token.json`; normal runs use it automatically.

While the consent screen is in **Testing**, Google expires the login after 7 days — the script then says so and you
run `--auth` again. To stop that, click **Publish app** on the consent screen (fine for personal use; you'll still
see the "unverified" warning once).

`client_secret.json`, `token.json`, `snapshots.jsonl` and `advisor_report.json` are in `.gitignore` — never share them.

## YPP runway

Current bar: 1,000 subscribers + **10M public Shorts views in the last 90 days** (a rolling window, i.e. about
111K views/day sustained) **or** 4,000 long-form watch hours in 365 days. The bar for new applicants changes on
2027-02-01 — verify on YouTube's help page.

## Files

- `yt_analytics_advisor.py` — the advisor
- `video_inspector.py` — pre-upload check of a rendered mp4
- `analytics_data.json`, `studio_export.csv` — **sample data for `--mock` only**, not the channel
