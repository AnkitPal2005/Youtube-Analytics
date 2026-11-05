# YouTube Analytics Review & Next-Topic/Time Prediction Engine (`yt_analytics_advisor.py`)

Specialized automated YouTube analytics advisor engineered for the channel **"Reality Shift"** (high-impact Hindi/Hinglish explainer shorts covering Geopolitics, Indigenous Defense & Tech, Consumer Manipulation, and High-Impact Tech).

---

## 🚀 Key Capabilities

1. **Initial Velocity Correlation & Predictive Upload Window:**
   - Evaluates initial 30–60 minute view velocities grouped across hour-of-day slots.
   - Computes day-of-week context (weekday commute surges vs. weekend leisure browsing) to predict the single optimal 60-minute upload window.
2. **Pillar Resonance & Outlier Benchmark:**
   - Categorizes past Shorts into the 4 channel core pillars:
     - *Indigenous Defense & Tech* (e.g., S-400 vs Kusha, BrahMos, Pinaka, Tejas)
     - *Geopolitics & Strategic Diplomacy* (e.g., Chabahar Port, CPEC, Malacca Choke)
     - *Consumer Manipulation / Business Case Studies* (e.g., Meesho, Movie Popcorn Scam, Dark Stores)
     - *High-Impact Tech* (e.g., UPI Hegemony, Dead Internet Theory, AI Deepfake Scams)
   - Computes channel median views and benchmarks performance multipliers (`1.5x`, `2.5x+` viral outliers).
   - Generates an audience affinity score (0–100) per pillar.
3. **Retention & Swipe-Leak Detection:**
   - Flags viral hook lock-in (`Stayed Watch % >= 70%`) vs. critical drop-off points (`Stayed Watch % < 50%`).
   - Analyzes Average Percentage Viewed (APV %) to maximize Shorts feed algorithmic distribution.
4. **Predictive Next-Topic & High-Retention Script Generation:**
   - Recommends the Top 2 highest-probability topics from top-performing pillars.
   - Provides a **32-second high-retention hook in authentic Devanagari phonetics** pre-tuned for Microsoft Edge-TTS voice `hi-IN-MadhurNeural`.
   - Generates exact **UI Safe Zone Coordinates** (`Y: 1150px - 1250px`, centered) to avoid UI overlap from Shorts overlays.
5. **YPP Compliance & Repetitive Content Guard:**
   - Validates metadata hygiene (strictly 3–4 hashtags; protects against keyword stuffing).
   - Enforces a repetitive content guard against the last 2 uploads to avoid algorithmic cannibalization.

---

## 🛠️ Usage & CLI Commands

### 1. Run in Mock Demo Mode
```bash
python yt_analytics_advisor.py --mock
```

### 2. Run with Local Storage (Default Fallback)
Automatically searches for `analytics_data.json` or `studio_export.csv` in the current folder:
```bash
python yt_analytics_advisor.py
```

### 3. Run with Custom JSON / CSV Data Export
```bash
python yt_analytics_advisor.py --data studio_export.csv
```

### 4. Run with Live YouTube Data API v3
Set your Google Cloud YouTube Data API v3 key as an environment variable or pass via flag:
```bash
# Via environment variable
set YOUTUBE_API_KEY=your_api_key_here
python yt_analytics_advisor.py

# Or via CLI flag
python yt_analytics_advisor.py --api-key YOUR_API_KEY --channel-id YOUR_CHANNEL_ID
```
*(If the API key is absent or quota is exceeded, the engine gracefully falls back to local export data without crashing).*

---

## 📦 Installed Dependencies
- `pandas`: Vectorized statistical aggregation, median calculations, and datetime grouping.
- `tabulate`: Formatted ASCII grid dashboards.
- `colorama`: Cross-platform ANSI terminal coloring.
- `google-api-python-client`: YouTube Data API v3 client.

