#!/usr/bin/env python3
"""
================================================================================
YT ANALYTICS ADVISOR - "Reality Shift"
================================================================================
Reads the channel's REAL numbers and turns them into signals for the next Short.

Data sources (nothing is estimated or invented; a metric that isn't available is shown as "--"):
  - YouTube Data API v3 (API key in .env): titles, upload times, durations, views, likes, comments, subscribers.
  - YouTube Analytics API (one-time Google login, `--auth`): average % viewed, average view duration,
    subs gained per Short, Shorts views in the last 90 days, long-form watch hours (365 days), daily views.
    YouTube's "stayed to watch vs swiped away" is not in any public API - read it in Studio.
  - snapshots.jsonl: every run stores each Short's view count, so the next run shows real views/hour gained.

Every live run writes advisor_report.json (machine-readable, read by the Short-making pipeline).
Demo data (--mock / analytics_data.json) is made-up sample data, never your channel, and is never saved as a report.

Usage:
  python yt_analytics_advisor.py            # live channel
  python yt_analytics_advisor.py --auth     # one-time Google login for the Analytics API (see README)
  python yt_analytics_advisor.py --mock     # demo layout with sample data
"""

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
except ImportError:
    pass

from colorama import Fore, Style, init
from tabulate import tabulate

init(autoreset=True)

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
CHANNEL_NAME = "Reality Shift"
IST = timezone(timedelta(hours=5, minutes=30))
CLIENT_SECRET = HERE / "client_secret.json"   # OAuth desktop client from Google Cloud (never commit)
TOKEN = HERE / "token.json"                   # saved login (never commit)
SNAPSHOTS = HERE / "snapshots.jsonl"
REPORT = HERE / "advisor_report.json"
DEMO_FILE = HERE / "analytics_data.json"
SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly",
          "https://www.googleapis.com/auth/youtube.readonly"]

SHORTS_MAX_SEC = 180               # YouTube counts uploads up to 3 minutes as Shorts
TOP_MULT, LOW_MULT = 1.5, 0.5      # vs the channel median
MIN_SAMPLE = 3                     # below this a group is shown but flagged as a weak signal

# YPP (current bar; changes for new applicants on 2027-02-01 - verify on YouTube's help page)
YPP_SUBS = 1_000
YPP_SHORTS_VIEWS_90D = 10_000_000
YPP_WATCH_HOURS_365D = 4_000
YPP_DEADLINE = date(2027, 1, 31)

PILLARS = {
    "Geopolitics & Strategic Diplomacy": [
        "chabahar", "cpec", "malacca", "dollar", "brics", "taiwan", "iran", "diplomacy", "border", "gwadar",
        "quad", "geopolitics", "russia", "china", "oil", "sanction", "trade route", "pakistan", "maldives",
        "chicken's neck", "lithium", "boycott", "kaladan", "bangladesh"
    ],
    "Indigenous Defense & Tech": [
        "s-400", "s400", "kusha", "brahmos", "pinaka", "tejas", "amca", "ins vikrant", "hypersonic", "drdo",
        "radar", "submarine", "air defense", "air defence", "missile", "stealth", "iaf", "indian navy", "army",
        "defense", "defence", "sky shield", "rocket", "agni", "akash"
    ],
    "Consumer Manipulation / Business Case Studies": [
        "meesho", "popcorn", "dark store", "zepto", "blinkit", "mrp", "scam", "fast fashion", "zomato", "swiggy",
        "subscription", "emi", "free delivery", "consumer", "decoy", "psychology", "marketing", "pricing", "rupee"
    ],
    "High-Impact Tech": [
        "upi", "dead internet", "ai ", "surveillance", "quantum", "deepfake", "starlink", "microchip",
        "semiconductor", "6g", "data mining", "algorithm", "bot"
    ],
}
OTHER_PILLAR = "Other / History"

# Words that mark a Hinglish (Roman-script Hindi) title
HINGLISH = {"ka", "ki", "ke", "hai", "hain", "mein", "me", "se", "kya", "kyun", "kyon", "ne", "ko", "nahi", "aur",
            "sab", "jisne", "kaise", "raha", "rahi", "kar", "diya", "bharat", "duniya", "sirf", "tabah", "baj",
            "kiya", "sach", "asli", "kitna", "kaun", "kab", "tak", "wala", "wali", "apna", "apni"}


# ------------------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------------------
def iso_seconds(d: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    days, h, mi, s = (int(x or 0) for x in m.groups())
    return days * 86400 + h * 3600 + mi * 60 + s


def clean_title(t: str) -> str:
    return re.sub(r"\s*#\S+", "", str(t)).strip()


def classify_pillar(title: str, tags: Any) -> str:
    text = clean_title(title).lower() + " "
    text += " ".join(tags).lower() if isinstance(tags, list) else str(tags or "").lower()
    hits = {p: sum(kw in text for kw in kws) for p, kws in PILLARS.items()}
    best = max(hits.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else OTHER_PILLAR


def title_style(title: str) -> str:
    words = set(re.findall(r"[a-z']+", clean_title(title).lower()))
    return "Hinglish" if len(words & HINGLISH) >= 2 else "English"


def duration_bucket(sec: int) -> str:
    if sec <= 0:
        return "unknown"
    if sec < 35:
        return "< 35s"
    if sec <= 50:
        return "35-50s"
    return "> 50s"


def time_slot(hour: int) -> str:
    if 6 <= hour < 11:
        return "06-11 Morning"
    if 11 <= hour < 15:
        return "11-15 Midday"
    if 15 <= hour < 18:
        return "15-18 Afternoon"
    if 18 <= hour < 22:
        return "18-22 Evening"
    return "22-06 Night"


def short_title(t: str, n: int = 40) -> str:
    t = clean_title(t)
    return t if len(t) <= n else t[:n - 2] + ".."


def pct(v: Optional[float]) -> str:
    return "--" if v is None else f"{v:.1f}%"


# ------------------------------------------------------------------------------
# DATA: PUBLIC (Data API v3, API key)
# ------------------------------------------------------------------------------
def fetch_public(api_key: str, channel_id: Optional[str], max_videos: int) -> Dict[str, Any]:
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
    if not channel_id:
        items = yt.search().list(q=CHANNEL_NAME, type="channel", part="id", maxResults=1).execute().get("items", [])
        if not items:
            raise RuntimeError(f"could not find channel '{CHANNEL_NAME}' - set YOUTUBE_CHANNEL_ID in .env")
        channel_id = items[0]["id"]["channelId"]
    ch = yt.channels().list(part="contentDetails,statistics,snippet", id=channel_id).execute()["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while len(ids) < max_videos:
        resp = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50,
                                       pageToken=page).execute()
        ids += [it["contentDetails"]["videoId"] for it in resp.get("items", [])]
        page = resp.get("nextPageToken")
        if not page:
            break
    ids = ids[:max_videos]
    videos = []
    for k in range(0, len(ids), 50):
        resp = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids[k:k + 50])).execute()
        for it in resp.get("items", []):
            sn, st = it["snippet"], it.get("statistics", {})
            published = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00")).astimezone(IST)
            dur = iso_seconds(it["contentDetails"].get("duration", ""))
            videos.append({
                "video_id": it["id"], "title": sn.get("title", ""), "tags": sn.get("tags", []),
                "published_ist": published.strftime("%Y-%m-%d %H:%M"), "_published": published,
                "duration_s": dur, "is_short": 0 < dur <= SHORTS_MAX_SEC,
                "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)),
            })
    videos.sort(key=lambda v: v["_published"])
    stats = ch.get("statistics", {})
    return {"channel_id": channel_id, "channel_title": ch["snippet"].get("title", CHANNEL_NAME),
            "subscribers": int(stats.get("subscriberCount", 0)) if not stats.get("hiddenSubscriberCount") else None,
            "videos": videos}


# ------------------------------------------------------------------------------
# DATA: PRIVATE (Analytics API, OAuth)
# ------------------------------------------------------------------------------
def credentials(interactive: bool = False):
    """Saved Google login, refreshed if needed; with interactive=True, opens the browser login once."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        return None
    creds = None
    if TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                TOKEN.write_text(creds.to_json(), encoding="utf-8")
        except Exception as e:
            print(f"{Fore.YELLOW}[!] Saved Google login no longer works ({e}). Run: python yt_analytics_advisor.py --auth")
            creds = None
    if (creds is None or not creds.valid) and interactive:
        if not CLIENT_SECRET.exists():
            raise SystemExit(f"{Fore.RED}[x] {CLIENT_SECRET.name} not found. Follow 'One-time Analytics setup' in README.md.")
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
        print(f"{Fore.GREEN}[ok] Google login saved to {TOKEN.name}")
    return creds if creds and creds.valid else None


def fetch_private(creds, video_ids: List[str]) -> Dict[str, Any]:
    """Real Studio metrics. Analytics data lags ~2-3 days behind live view counts."""
    from googleapiclient.discovery import build
    yta = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    today = date.today()
    out: Dict[str, Any] = {"per_video": {}, "errors": []}

    def query(**kw):
        return yta.reports().query(ids="channel==MINE", endDate=today.isoformat(), **kw).execute()

    def rows(resp):
        cols = [h["name"] for h in resp.get("columnHeaders", [])]
        return [dict(zip(cols, r)) for r in resp.get("rows", [])]

    try:
        for k in range(0, len(video_ids), 200):
            resp = query(startDate="2015-01-01", dimensions="video", sort="-views", maxResults=200,
                         metrics="views,averageViewPercentage,averageViewDuration,subscribersGained",
                         filters="video==" + ",".join(video_ids[k:k + 200]))
            for r in rows(resp):
                out["per_video"][r["video"]] = {
                    "apv_percent": round(float(r["averageViewPercentage"]), 1),
                    "avg_view_s": round(float(r["averageViewDuration"]), 1),
                    "subs_gained": int(r["subscribersGained"]),
                }
    except Exception as e:
        out["errors"].append(f"per-video metrics: {e}")

    try:
        resp = query(startDate=(today - timedelta(days=89)).isoformat(), dimensions="creatorContentType",
                     metrics="views")
        by_type = {str(r["creatorContentType"]).lower(): int(r["views"]) for r in rows(resp)}
        out["shorts_views_90d"] = sum(v for t, v in by_type.items() if "short" in t)
    except Exception as e:
        out["errors"].append(f"90-day Shorts views: {e}")

    try:
        resp = query(startDate=(today - timedelta(days=364)).isoformat(), dimensions="creatorContentType",
                     metrics="estimatedMinutesWatched")
        mins = sum(int(r["estimatedMinutesWatched"]) for r in rows(resp)
                   if "short" not in str(r["creatorContentType"]).lower())
        out["longform_watch_hours_365d"] = round(mins / 60, 1)
    except Exception as e:
        out["errors"].append(f"watch hours: {e}")

    try:
        resp = query(startDate=(today - timedelta(days=27)).isoformat(), dimensions="day", metrics="views",
                     sort="day")
        out["daily_views_28d"] = [{"day": r["day"], "views": int(r["views"])} for r in rows(resp)]
    except Exception as e:
        out["errors"].append(f"daily views: {e}")
    return out


# ------------------------------------------------------------------------------
# SNAPSHOTS: real views/hour between runs
# ------------------------------------------------------------------------------
def last_snapshot() -> Optional[Dict[str, Any]]:
    if not SNAPSHOTS.exists():
        return None
    lines = [ln for ln in SNAPSHOTS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else None


def save_snapshot(now: datetime, videos: List[Dict[str, Any]]) -> None:
    rec = {"t": now.isoformat(), "views": {v["video_id"]: v["views"] for v in videos}}
    with SNAPSHOTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def apply_live_delta(now: datetime, videos: List[Dict[str, Any]], prev: Optional[Dict[str, Any]]) -> Optional[float]:
    """Adds views gained / views per hour since the previous run; returns hours since that run."""
    if not prev:
        return None
    hours = (now - datetime.fromisoformat(prev["t"])).total_seconds() / 3600
    if hours < 1 / 6:   # under 10 minutes: too short to mean anything
        return None
    for v in videos:
        old = prev["views"].get(v["video_id"])
        if old is not None:
            v["gained_since_last_run"] = v["views"] - old
            v["views_per_hour_live"] = round((v["views"] - old) / hours, 1)
    return round(hours, 2)


# ------------------------------------------------------------------------------
# ANALYSIS
# ------------------------------------------------------------------------------
def group_stats(shorts: List[Dict[str, Any]], key: str, med: float) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for v in shorts:
        groups.setdefault(v[key], []).append(v)
    out = []
    for name, vs in groups.items():
        views = [v["views"] for v in vs]
        best = max(vs, key=lambda v: v["views"])
        out.append({"group": name, "shorts": len(vs), "median_views": int(median(views)),
                    "median_multiplier": round(median(views) / med, 2), "best_title": clean_title(best["title"]),
                    "best_views": best["views"], "weak_signal": len(vs) < MIN_SAMPLE})
    return sorted(out, key=lambda g: g["median_views"], reverse=True)


def analyze(data: Dict[str, Any], private: Optional[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    videos = data["videos"]
    for v in videos:
        v["pillar"] = classify_pillar(v["title"], v.get("tags"))
        v["title_style"] = title_style(v["title"])
        v["duration_bucket"] = duration_bucket(v.get("duration_s", 0))
        pub = v.get("_published")
        v["slot_ist"] = time_slot(pub.hour) if pub else "unknown"
        v["age_hours"] = round((now - pub).total_seconds() / 3600, 1) if pub else None
        if private:
            v.update(private["per_video"].get(v["video_id"], {}))
    shorts = [v for v in videos if v.get("is_short", True)]
    med = float(median([v["views"] for v in shorts])) if shorts else 1.0
    med = med or 1.0
    for v in shorts:
        v["multiplier"] = round(v["views"] / med, 2)
        v["label"] = "TOP" if v["multiplier"] >= TOP_MULT else ("LOW" if v["multiplier"] < LOW_MULT else "")

    ranked = sorted(shorts, key=lambda v: v["views"], reverse=True)
    report = {
        "median_views": int(med),
        "shorts": shorts,
        "longform_count": len(videos) - len(shorts),
        "pillars": group_stats(shorts, "pillar", med),
        "title_styles": group_stats(shorts, "title_style", med),
        "durations": group_stats(shorts, "duration_bucket", med),
        "slots": group_stats(shorts, "slot_ist", med),
        "top": [clean_title(v["title"]) for v in ranked[:3]],
        "bottom": [clean_title(v["title"]) for v in ranked[-2:]] if len(ranked) > 3 else [],
        "recent_topics": [clean_title(v["title"]) for v in shorts[-5:]],
    }
    with_apv = [v for v in shorts if v.get("apv_percent") is not None]
    if with_apv:
        report["best_retention"] = [{"title": clean_title(v["title"]), "apv_percent": v["apv_percent"]}
                                    for v in sorted(with_apv, key=lambda v: v["apv_percent"], reverse=True)[:3]]
        report["worst_retention"] = [{"title": clean_title(v["title"]), "apv_percent": v["apv_percent"]}
                                     for v in sorted(with_apv, key=lambda v: v["apv_percent"])[:2]
                                     if v["video_id"] not in {b["video_id"] for b in
                                                              sorted(with_apv, key=lambda v: -v["apv_percent"])[:3]}]
    report["runway"] = runway(data, private, shorts, now)
    return report


def runway(data, private, shorts, now) -> Dict[str, Any]:
    """YPP progress from real numbers only. Shorts path = 10M views inside a rolling 90-day window."""
    days_left = max((YPP_DEADLINE - now.date()).days, 0)
    r: Dict[str, Any] = {"deadline": YPP_DEADLINE.isoformat(), "days_left": days_left,
                         "subscribers": data.get("subscribers"), "subs_needed": YPP_SUBS,
                         "shorts_views_90d_needed": YPP_SHORTS_VIEWS_90D,
                         "required_daily_avg": round(YPP_SHORTS_VIEWS_90D / 90),
                         "watch_hours_needed": YPP_WATCH_HOURS_365D}
    if private:
        r["shorts_views_90d"] = private.get("shorts_views_90d")
        r["longform_watch_hours_365d"] = private.get("longform_watch_hours_365d")
        daily = private.get("daily_views_28d") or []
        if daily:
            last7 = daily[-7:]
            r["daily_avg_last_7d"] = round(sum(d["views"] for d in last7) / len(last7))
            r["daily_source"] = "Analytics API (all content, lags ~2-3 days)"
    if "daily_avg_last_7d" not in r:
        live = [v.get("views_per_hour_live") for v in shorts if v.get("views_per_hour_live") is not None]
        if live:
            r["daily_avg_last_7d"] = round(sum(live) * 24)
            r["daily_source"] = "live snapshots (views/hour since last run x 24, recent uploads only)"
    if r.get("daily_avg_last_7d") is not None:
        r["pace_gap_x"] = round(r["required_daily_avg"] / max(r["daily_avg_last_7d"], 1), 1)
    return r


# ------------------------------------------------------------------------------
# OUTPUT
# ------------------------------------------------------------------------------
def head(n: str, t: str) -> None:
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{n}. {t}{Style.RESET_ALL}")


def render(rep: Dict[str, Any], source: str, demo: bool, private_on: bool, live_hours: Optional[float]) -> None:
    print("\n" + "=" * 92)
    print(f"{Fore.CYAN}{Style.BRIGHT}   >>> REALITY SHIFT : YOUTUBE ANALYTICS ADVISOR <<<")
    if demo:
        print(f"{Fore.RED}{Style.BRIGHT}   DEMO / FILE DATA - NOT YOUR LIVE CHANNEL. Nothing below describes Reality Shift.")
    print(f"{Fore.LIGHTBLACK_EX}   Source: {Fore.WHITE}{source}")
    print(f"{Fore.LIGHTBLACK_EX}   Studio metrics: " + (f"{Fore.GREEN}connected (Analytics API)" if private_on else
          f"{Fore.YELLOW}not connected - APV/subs columns show '--' (run --auth, see README)"))
    live = f"{live_hours} h since last run" if live_hours else "first run / too soon - shown from the next run"
    print(f"{Fore.LIGHTBLACK_EX}   Live views/hour: {Fore.WHITE}{live}")
    print(f"{Fore.LIGHTBLACK_EX}   Time: {Fore.WHITE}{datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}"
          f"{Fore.LIGHTBLACK_EX} | Shorts: {Fore.GREEN}{len(rep['shorts'])}"
          f"{Fore.LIGHTBLACK_EX} | Median views: {Fore.YELLOW}{rep['median_views']:,}")
    print("=" * 92)

    head("1", "SHORTS (newest last) - multiplier vs channel median")
    rows = []
    for v in rep["shorts"][-15:]:
        lab = v.get("label", "")
        col = Fore.GREEN if lab == "TOP" else (Fore.RED if lab == "LOW" else Fore.WHITE)
        vph = v.get("views_per_hour_live")
        rows.append([short_title(v["title"], 38), v.get("published_ist", "--"), f"{v.get('duration_s', 0)}s",
                     f"{v['views']:,}", f"{col}{v['multiplier']}x {lab}{Style.RESET_ALL}",
                     "--" if vph is None else f"+{vph}/h", pct(v.get("apv_percent")),
                     "--" if v.get("subs_gained") is None else v["subs_gained"], v["pillar"][:22]])
    print(tabulate(rows, headers=["Title", "Upload (IST)", "Len", "Views", "Mult", "Live", "Avg % viewed",
                                  "Subs+", "Pillar"], tablefmt="grid"))

    def group_table(key: str, title: str, n: str):
        head(n, title)
        rows = [[g["group"], g["shorts"], f"{g['median_views']:,}", f"{g['median_multiplier']}x",
                 short_title(g["best_title"], 34), (f"{Fore.YELLOW}weak (n<{MIN_SAMPLE}){Style.RESET_ALL}"
                                                   if g["weak_signal"] else f"{Fore.GREEN}ok{Style.RESET_ALL}")]
                for g in rep[key]]
        print(tabulate(rows, headers=["Group", "Shorts", "Median views", "Median mult", "Best Short", "Signal"],
                       tablefmt="simple"))

    group_table("pillars", "CONTENT PILLARS (ranked by median views)", "2")
    group_table("title_styles", "TITLE STYLE: Hinglish vs English", "3")
    group_table("durations", "SHORT LENGTH", "4")
    group_table("slots", "UPLOAD SLOT (IST)", "5")
    solid = [g for g in rep["slots"] if not g["weak_signal"]]
    if solid:
        print(f"   {Fore.GREEN}-> Best slot with {MIN_SAMPLE}+ Shorts: {solid[0]['group']} "
              f"(median {solid[0]['median_views']:,} views)")
    else:
        print(f"   {Fore.YELLOW}-> No slot has {MIN_SAMPLE}+ Shorts yet - not enough data to pick a time. "
              f"Keep the fixed schedule and let the data build.")

    head("6", "RETENTION (Studio average % viewed)")
    if rep.get("best_retention"):
        for r in rep["best_retention"]:
            print(f"   {Fore.GREEN}+ {r['apv_percent']}%  {r['title']}")
        for r in rep.get("worst_retention", []):
            print(f"   {Fore.RED}- {r['apv_percent']}%  {r['title']}")
        print(f"   {Fore.LIGHTBLACK_EX}'Stayed to watch vs swiped away' isn't in the API - check it in Studio > Content.")
    else:
        print(f"   {Fore.YELLOW}Not connected. Run --auth once (README) to see real average % viewed per Short.")

    head("7", "SIGNALS FOR THE NEXT SHORT (facts only - topics/scripts are checked separately)")
    if rep["pillars"]:
        p = rep["pillars"][0]
        print(f"   * Strongest pillar : {p['group']} (median {p['median_views']:,}, {p['shorts']} Shorts"
              f"{', weak signal' if p['weak_signal'] else ''})")
    styles = {g["group"]: g for g in rep["title_styles"]}
    if len(styles) == 2:
        h, e = styles["Hinglish"], styles["English"]
        better = "Hinglish" if h["median_views"] >= e["median_views"] else "English"
        print(f"   * Title style      : {better} titles lead (Hinglish {h['median_views']:,} vs English "
              f"{e['median_views']:,} median)")
    print(f"   * Top performers   : " + " | ".join(short_title(t, 36) for t in rep["top"]))
    if rep["bottom"]:
        print(f"   * Weakest          : " + " | ".join(short_title(t, 36) for t in rep["bottom"]))
    print(f"   * Don't repeat     : " + " | ".join(short_title(t, 30) for t in rep["recent_topics"]))

    r = rep["runway"]
    head("8", f"YPP RUNWAY (deadline {r['deadline']}, {r['days_left']} days left)")
    subs = r.get("subscribers")
    print(f"   * Subscribers       : {subs:,} / {r['subs_needed']:,}" if subs is not None else
          "   * Subscribers       : hidden")
    v90 = r.get("shorts_views_90d")
    print(f"   * Shorts views 90d  : " + (f"{Fore.YELLOW}{v90:,}{Style.RESET_ALL} / {r['shorts_views_90d_needed']:,}"
                                          if v90 is not None else "-- (needs --auth)"))
    wh = r.get("longform_watch_hours_365d")
    print(f"   * Watch hours 365d  : " + (f"{wh:,} / {r['watch_hours_needed']:,} (long-form only)"
                                          if wh is not None else "-- (needs --auth)"))
    print(f"   * Needed pace       : {r['required_daily_avg']:,} Shorts views/day, every day for 90 days")
    if r.get("daily_avg_last_7d") is not None:
        print(f"   * Current pace      : {r['daily_avg_last_7d']:,} views/day ({r['daily_source']})")
        gap = r.get("pace_gap_x", "--")
        print(f"   * Gap               : {Fore.RED}{gap}x{Style.RESET_ALL} faster needed")
    else:
        print("   * Current pace      : -- (shown after --auth, or from the second run via live snapshots)")
    print("=" * 92 + "\n")


def save_report(rep: Dict[str, Any], data: Dict[str, Any], source: str, private: Optional[Dict[str, Any]],
                live_hours: Optional[float]) -> None:
    def clean(v):
        return {k: val for k, val in v.items() if not k.startswith("_")}
    out = {
        "generated_at": datetime.now(IST).isoformat(timespec="seconds"),
        "source": source,
        "studio_metrics": bool(private),
        "studio_errors": (private or {}).get("errors", []),
        "live_hours_since_last_run": live_hours,
        "channel": {"id": data.get("channel_id"), "title": data.get("channel_title"),
                    "subscribers": data.get("subscribers")},
        **{k: val for k, val in rep.items() if k != "shorts"},
        "shorts": [clean(v) for v in rep["shorts"]],
    }
    REPORT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{Fore.LIGHTBLACK_EX}Report saved: {REPORT}")


# ------------------------------------------------------------------------------
# ENTRY POINT
# ------------------------------------------------------------------------------
def load_file(path: Path) -> Dict[str, Any]:
    """Demo / exported data: same row format as the live loader; never treated as the live channel."""
    if path.suffix == ".csv":
        import pandas as pd
        records = pd.read_csv(path).to_dict(orient="records")
    else:
        records = json.loads(path.read_text(encoding="utf-8"))
    videos = []
    for r in records:
        pub = datetime.strptime(str(r.get("upload_time")), "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
        tags = r.get("tags", [])
        videos.append({"video_id": r.get("video_id"), "title": r.get("title", ""),
                       "tags": tags.split(",") if isinstance(tags, str) else tags,
                       "published_ist": pub.strftime("%Y-%m-%d %H:%M"), "_published": pub,
                       "duration_s": int(r.get("duration_s", 0) or 0), "is_short": True,
                       "views": int(r.get("views", 0)), "likes": int(r.get("likes", 0)),
                       "comments": int(r.get("comments", 0)), "apv_percent": r.get("apv_percent")})
    videos.sort(key=lambda v: v["_published"])
    return {"channel_id": None, "channel_title": f"file: {path.name}", "subscribers": None, "videos": videos}


def main() -> None:
    ap = argparse.ArgumentParser(description="Real-data YouTube analytics advisor for 'Reality Shift'")
    ap.add_argument("--auth", action="store_true", help="one-time Google login for Studio metrics (Analytics API)")
    ap.add_argument("--mock", action="store_true", help="demo layout with made-up sample data (not your channel)")
    ap.add_argument("--data", type=str, help="analyze an exported JSON/CSV file instead of the live channel")
    ap.add_argument("--api-key", type=str, help="Data API v3 key (default: YOUTUBE_API_KEY in .env)")
    ap.add_argument("--channel-id", type=str, help="channel id (default: YOUTUBE_CHANNEL_ID in .env)")
    ap.add_argument("--max-videos", type=int, default=50, help="how many recent uploads to read (default 50)")
    ap.add_argument("--no-save", action="store_true", help="don't write the snapshot / advisor_report.json")
    args = ap.parse_args()

    now = datetime.now(IST)
    if args.mock or args.data:
        path = Path(args.data) if args.data else DEMO_FILE
        data = load_file(path)
        rep = analyze(data, None, now)
        render(rep, f"{'DEMO' if args.mock else 'FILE'}: {path.name}", True, False, None)
        return

    key = args.api_key or os.getenv("YOUTUBE_API_KEY")
    if not key or "your_" in key:
        raise SystemExit(f"{Fore.RED}[x] No YOUTUBE_API_KEY in .env. Live analysis needs it (see README). "
                         f"For a demo of the layout run with --mock.")
    channel = args.channel_id or os.getenv("YOUTUBE_CHANNEL_ID")
    if channel and "your_" in channel:
        channel = None
    try:
        data = fetch_public(key, channel, args.max_videos)
    except Exception as e:   # no silent fallback to fake data: say what failed
        raise SystemExit(f"{Fore.RED}[x] YouTube Data API failed: {e}\n    Nothing was analyzed. "
                         f"Check the key/quota and try again.")
    if not data["videos"]:
        raise SystemExit(f"{Fore.YELLOW}[!] The channel has no public uploads yet.")

    creds = credentials(interactive=args.auth)
    private = None
    if creds:   # Analytics only reports the channel the Google login belongs to: never mix two channels
        from googleapiclient.discovery import build
        mine = build("youtube", "v3", credentials=creds, cache_discovery=False).channels().list(
            part="id,snippet", mine=True).execute().get("items", [])
        mine_id = mine[0]["id"] if mine else None
        if mine_id != data["channel_id"]:
            name = mine[0]["snippet"]["title"] if mine else "unknown"
            print(f"{Fore.YELLOW}[!] Google login is for '{name}' ({mine_id}), not this channel - Studio metrics "
                  f"skipped. To add this channel, log in with its account: --auth (replaces token.json).")
            creds = None
    if creds:
        private = fetch_private(creds, [v["video_id"] for v in data["videos"]])
        for err in private["errors"]:
            print(f"{Fore.YELLOW}[!] Analytics API: {err}")

    prev = last_snapshot()
    live_hours = apply_live_delta(now, data["videos"], prev)
    rep = analyze(data, private, now)
    render(rep, f"YouTube Data API v3 - {data['channel_title']} ({data['channel_id']})", False, bool(private),
           live_hours)
    if not args.no_save:
        if prev is None or (now - datetime.fromisoformat(prev["t"])).total_seconds() >= 600:
            save_snapshot(now, data["videos"])   # runs <10 min apart keep the older baseline
        save_report(rep, data, "live", private, live_hours)


if __name__ == "__main__":
    main()
