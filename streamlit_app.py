import streamlit as st
import requests
import pandas as pd
import math
import os
import numpy as np
import time
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SETUP  —  API-Football v3 via RapidAPI
# ─────────────────────────────────────────────────────────────────────────────

API_KEY = "66d8a9250fd21dd31b4cf58b37dd4bd6"
HEADERS = {
    "x-apisports-key": API_KEY,
}
BASE_URL = "https://v3.football.api-sports.io"

CURRENT_SEASON = 2024   # 2024 = 2024/25 season in API-Football

# ── Cache files ───────────────────────────────────────────────────────────────
CACHE_TEAM_SEARCH  = "team_search_cache.csv"
CACHE_TEAM_STATS   = "team_stats_cache.csv"
CACHE_STANDINGS    = "standings_cache.csv"
CACHE_H2H          = "h2h_cache.csv"
CACHE_LAST_MATCHES = "last_matches_cache.csv"

CACHE_TTL = {"search": 30, "stats": 3, "standings": 1, "h2h": 1, "matches": 1}

# ── Rate limiter ──────────────────────────────────────────────────────────────
_last_req  = 0.0
MIN_GAP    = 1.5
MAX_RETRY  = 3

def _api_get(endpoint: str, params: dict = None) -> dict:
    """Throttled + retry wrapper for API-Football v3."""
    global _last_req
    elapsed = time.time() - _last_req
    if elapsed < MIN_GAP:
        time.sleep(MIN_GAP - elapsed)
    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(MAX_RETRY + 1):
        try:
            r = requests.get(url, headers=HEADERS, params=params or {}, timeout=15)
            _last_req = time.time()
            data = r.json()
            msg = str(data.get("message", "")).lower()
            if r.status_code == 429 or "too many" in msg or "rate limit" in msg:
                wait = 5 * (2 ** attempt)
                st.warning(f"⏳ Rate limited — waiting {wait}s (retry {attempt+1}/{MAX_RETRY})...")
                time.sleep(wait)
                continue
            return data
        except Exception:
            _last_req = time.time()
            if attempt < MAX_RETRY:
                time.sleep(3)
    return {}

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG & STYLES
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Pro Sports Analytics", page_icon="⚽", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');
html,body,[class*="css"]            { font-family:'IBM Plex Mono',monospace; }
h1,h2,h3,h4                        { font-family:'Barlow Condensed',sans-serif; letter-spacing:.02em; }
.stApp                              { background:#080c14; color:#c8d6e5; }
section[data-testid="stSidebar"]    { background:#050810 !important; border-right:1px solid #151f30; }
section[data-testid="stSidebar"] *  { color:#90a8c0 !important; }
section[data-testid="stSidebar"] label { color:#6a8aaa !important; font-size:.72rem; }
.stButton>button                    { background:transparent; border:1px solid #1e3050; color:#6ab0e8;
                                      font-family:'IBM Plex Mono',monospace; font-size:.78rem;
                                      transition:all .15s; border-radius:3px; }
.stButton>button:hover              { background:#0e1e30; border-color:#3a70b0; color:#b0d8ff; }
.stButton>button[kind="primary"]    { background:#0a2545; border:1px solid #2a70c0; color:#d0eaff;
                                      font-weight:700; font-size:.88rem; letter-spacing:.06em; }
div[data-testid="metric-container"] { background:#0b1422; border:1px solid #152030;
                                      border-radius:3px; padding:10px 14px; }
div[data-testid="metric-container"] label { color:#5a80a0 !important; font-size:.68rem; }
.math-box { background:#0b1828; border-left:3px solid #2060a0; border-radius:3px;
            padding:14px 18px; margin:10px 0; font-family:'IBM Plex Mono',monospace;
            font-size:.82rem; color:#a8cce8; line-height:1.7; }
.math-box b { color:#d0eaff; }
.math-box .result { color:#50d090; font-weight:700; font-size:.95rem; }
.math-box .formula { color:#7aacda; font-style:italic; }
.cache-badge { background:#0a2010; border:1px solid #1a5030; border-radius:3px;
               padding:2px 8px; font-size:.7rem; color:#40b060; font-family:'IBM Plex Mono',monospace; }
.api-badge   { background:#201005; border:1px solid #604010; border-radius:3px;
               padding:2px 8px; font-size:.7rem; color:#c07030; font-family:'IBM Plex Mono',monospace; }
.section-header { font-family:'Barlow Condensed',sans-serif; font-size:1.6rem; font-weight:700;
                  color:#d8eeff; border-bottom:1px solid #152030; padding-bottom:4px; margin-top:1.5rem; }
hr { border-color:#101a28; margin:1.8rem 0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# GENERIC CACHE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load(path):
    if os.path.exists(path):
        try: return pd.read_csv(path)
        except: pass
    return pd.DataFrame()

def _save(df, path):
    df.to_csv(path, index=False)

def _today():
    return datetime.today().strftime("%Y-%m-%d")

def _fresh(date_str, ttl):
    try:
        return (datetime.today() - datetime.strptime(str(date_str), "%Y-%m-%d")).days <= ttl
    except: return False

# ─────────────────────────────────────────────────────────────────────────────
# TEAM SEARCH CACHE
# ─────────────────────────────────────────────────────────────────────────────

def _cached_search(name):
    df = _load(CACHE_TEAM_SEARCH)
    if df.empty: return None
    m = df[df["query"].str.lower() == name.strip().lower()]
    if m.empty: return None
    row = m.iloc[0]
    if not _fresh(row["cached_date"], CACHE_TTL["search"]): return None
    return int(row["team_id"]), str(row["team_name"]), int(row["league_id"]), int(row["season"])

def _save_search(query, team_id, team_name, league_id, season):
    df = _load(CACHE_TEAM_SEARCH)
    if not df.empty:
        df = df[df["query"].str.lower() != query.strip().lower()]
    row = {"query": query.strip().lower(), "team_id": int(team_id), "team_name": str(team_name),
           "league_id": int(league_id), "season": int(season), "cached_date": _today()}
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save(df, CACHE_TEAM_SEARCH)

# ─────────────────────────────────────────────────────────────────────────────
# TEAM STATS CACHE
# ─────────────────────────────────────────────────────────────────────────────

def _cached_stats(team_id, league_id, season):
    df = _load(CACHE_TEAM_STATS)
    if df.empty: return None
    m = df[(df["team_id"].astype(str)==str(team_id)) &
           (df["league_id"].astype(str)==str(league_id)) &
           (df["season"].astype(str)==str(season))]
    if m.empty: return None
    if not _fresh(m.iloc[0]["cached_date"], CACHE_TTL["stats"]): return None
    return m.iloc[0].to_dict()

def _save_stats(row):
    df = _load(CACHE_TEAM_STATS)
    if not df.empty:
        df = df[~((df["team_id"].astype(str)==str(row["team_id"])) &
                  (df["league_id"].astype(str)==str(row["league_id"])) &
                  (df["season"].astype(str)==str(row["season"])))]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save(df, CACHE_TEAM_STATS)

# ─────────────────────────────────────────────────────────────────────────────
# STANDINGS CACHE
# ─────────────────────────────────────────────────────────────────────────────

def _cached_standings(league_id, season):
    df = _load(CACHE_STANDINGS)
    if df.empty: return None
    m = df[(df["league_id"].astype(str)==str(league_id)) &
           (df["season"].astype(str)==str(season))]
    if m.empty: return None
    if not _fresh(m.iloc[0]["cached_date"], CACHE_TTL["standings"]): return None
    return m.drop(columns=["league_id","season","cached_date"], errors="ignore")

def _save_standings(league_id, season, sdf):
    if sdf.empty: return
    df = _load(CACHE_STANDINGS)
    if not df.empty:
        df = df[~((df["league_id"].astype(str)==str(league_id)) &
                  (df["season"].astype(str)==str(season)))]
    tmp = sdf.copy()
    tmp["league_id"]=league_id; tmp["season"]=season; tmp["cached_date"]=_today()
    df = pd.concat([df, tmp], ignore_index=True)
    _save(df, CACHE_STANDINGS)

# ─────────────────────────────────────────────────────────────────────────────
# H2H CACHE
# ─────────────────────────────────────────────────────────────────────────────

def _h2h_key(a, b): return f"{min(int(a),int(b))}_{max(int(a),int(b))}"

def _cached_h2h(a, b):
    df = _load(CACHE_H2H)
    if df.empty: return None
    key = _h2h_key(a, b)
    m = df[df["h2h_key"]==key]
    if m.empty: return None
    if not _fresh(m.iloc[0]["cached_date"], CACHE_TTL["h2h"]): return None
    return m.drop(columns=["h2h_key","cached_date"], errors="ignore")

def _save_h2h(a, b, hdf):
    if hdf.empty: return
    key = _h2h_key(a, b)
    df = _load(CACHE_H2H)
    if not df.empty: df = df[df["h2h_key"]!=key]
    tmp = hdf.copy(); tmp["h2h_key"]=key; tmp["cached_date"]=_today()
    df = pd.concat([df, tmp], ignore_index=True)
    _save(df, CACHE_H2H)

# ─────────────────────────────────────────────────────────────────────────────
# LAST MATCHES CACHE
# ─────────────────────────────────────────────────────────────────────────────

def _cached_matches(team_id):
    df = _load(CACHE_LAST_MATCHES)
    if df.empty: return None
    m = df[df["team_id"]==int(team_id)].copy()
    if m.empty: return None
    if not _fresh(m.iloc[0]["cached_date"], CACHE_TTL["matches"]): return None
    if "timestamp" in m.columns:
        m = m.sort_values("timestamp", ascending=False)
    return m.drop(columns=["team_id","cached_date"], errors="ignore").to_dict("records")

def _save_matches(team_id, rows):
    if not rows: return
    df_new = pd.DataFrame(rows)
    df_new["team_id"]=int(team_id); df_new["cached_date"]=_today()
    df = _load(CACHE_LAST_MATCHES)
    if not df.empty: df = df[df["team_id"]!=int(team_id)]
    df = pd.concat([df, df_new], ignore_index=True)
    _save(df, CACHE_LAST_MATCHES)

# ─────────────────────────────────────────────────────────────────────────────
# API-FOOTBALL V3  FETCH FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def search_team(name: str, force=False):
    """Returns (team_id, team_name, league_id, season) or (None,None,None,None).
    Uses cascading fallback searches and fuzzy string matching to fix spelling errors."""
    if not force:
        cached = _cached_search(name)
        if cached:
            st.markdown('<span class="cache-badge">💾 CACHED — team search</span>', unsafe_allow_html=True)
            return cached

    low = name.lower().strip()
    aliases = {
        "man united": "Manchester United", "man utd": "Manchester United",
        "man city": "Manchester City", "spurs": "Tottenham",
        "barca": "Barcelona", "betis": "Real Betis", "wolves": "Wolverhampton",
        "nottm": "Nottingham Forest", "psg": "Paris Saint Germain",
        "juve": "Juventus"
    }

    # Build a list of search strategies from most specific to broadest fallback
    search_queries = []
    if low in aliases:
        search_queries.append(aliases[low])

    search_queries.append(name) # 1. Try exact input

    words = name.split()
    longest_word = max(words, key=len) if words else name

    if len(longest_word) > 4:
        search_queries.append(longest_word) # 2. Try longest word

    if len(longest_word) >= 4:
        search_queries.append(longest_word[:4]) # 3. Try first 4 letters of longest word

    # 4. Ultimate fallback: First 3 letters of the name (ignoring spaces)
    clean_name = name.replace(" ", "")
    if len(clean_name) >= 3:
        search_queries.append(clean_name[:3])

    # Remove duplicates while keeping the order of priority
    seen = set()
    search_queries = [x for x in search_queries if not (x in seen or seen.add(x))]

    results = []
    for attempt_name in search_queries:
        if len(attempt_name) < 3:
            continue
        data = _api_get("teams", {"search": attempt_name})
        results = data.get("response", [])
        if results:
            st.markdown(f'<span class="api-badge">🌐 API — search: "{attempt_name}"</span>', unsafe_allow_html=True)
            break # Stop hitting the API as soon as we get a batch of results

    if not results:
        st.error(f"No results found for **{name}**. We tried searching for: {', '.join(search_queries)}.")
        return None, None, None, None

    # --- THE MAGIC TRICK: FUZZY SORTING ---
    # Sort the returned API results by how similar they are to the user's original typo
    results.sort(
        key=lambda x: difflib.SequenceMatcher(None, low, x['team']['name'].lower()).ratio(),
        reverse=True
    )

    # Let user pick, showing the most mathematically similar team at the very top
    if len(results) > 1:
        # Show up to 8 closest matches
        options = {f"{r['team']['name']} ({r['team'].get('country','')})": r for r in results[:8]}
        
        # We append a timestamp to the key to prevent Streamlit duplicate widget ID errors 
        # if the same team is searched in both boxes
        chosen_label = st.selectbox(
            f"Matches found for '{name}'. Pick the correct team:", 
            list(options.keys()), 
            key=f"pick_{low}_{time.time()}"
        )
        chosen = options[chosen_label]
    else:
        chosen = results[0]

    team_id   = chosen["team"]["id"]
    team_name = chosen["team"]["name"]

    # Find current domestic league
    lg_data = _api_get("leagues", {"team": team_id, "current": "true", "season": CURRENT_SEASON})
    st.markdown('<span class="api-badge">🌐 API — league lookup</span>', unsafe_allow_html=True)
    leagues = lg_data.get("response", [])

    league_id = None
    for entry in leagues:
        if entry.get("league", {}).get("type") == "League":
            league_id = entry["league"]["id"]
            break
            
    if league_id is None and leagues:
        league_id = leagues[0]["league"]["id"]
        
    if league_id is None:
        st.warning(f"Found team **{team_name}** but could not detect their current league.")
        return team_id, team_name, None, None

    _save_search(name, team_id, team_name, league_id, CURRENT_SEASON)
    return team_id, team_name, league_id, CURRENT_SEASON


def get_standings(league_id, season, force=False):
    if not force:
        cached = _cached_standings(league_id, season)
        if cached is not None:
            st.markdown('<span class="cache-badge">💾 CACHED — standings</span>', unsafe_allow_html=True)
            return cached

    data = _api_get("standings", {"league": league_id, "season": season})
    st.markdown('<span class="api-badge">🌐 API — standings</span>', unsafe_allow_html=True)
    try:
        rows = data["response"][0]["league"]["standings"][0]
    except (KeyError, IndexError):
        return pd.DataFrame()

    table = []
    for r in rows:
        table.append({
            "Rank": r.get("rank"),
            "Team": r["team"]["name"],
            "P":    r["all"]["played"],
            "W":    r["all"]["win"],
            "D":    r["all"]["draw"],
            "L":    r["all"]["lose"],
            "GF":   r["all"]["goals"]["for"],
            "GA":   r["all"]["goals"]["against"],
            "GD":   r.get("goalsDiff"),
            "Pts":  r.get("points"),
            "Form": r.get("form", ""),
        })
    df = pd.DataFrame(table)
    _save_standings(league_id, season, df)
    return df


def get_team_stats(team_id, team_name, league_id, season, force=False):
    if not force:
        cached = _cached_stats(team_id, league_id, season)
        if cached:
            st.markdown('<span class="cache-badge">💾 CACHED — team stats</span>', unsafe_allow_html=True)
            return cached

    data = _api_get("teams/statistics", {"team": team_id, "league": league_id, "season": season})
    st.markdown('<span class="api-badge">🌐 API — team stats</span>', unsafe_allow_html=True)
    s = data.get("response", {})
    if not s:
        return None

    played = s.get("fixtures", {}).get("played", {}).get("total", 1) or 1
    gf     = s.get("goals", {}).get("for",      {}).get("total", {}).get("total", 0) or 0
    ga     = s.get("goals", {}).get("against",   {}).get("total", {}).get("total", 0) or 0
    cs     = s.get("clean_sheet", {}).get("total", 0) or 0
    ft_w   = s.get("fixtures", {}).get("wins",   {}).get("total", 0) or 0
    ft_d   = s.get("fixtures", {}).get("draws",  {}).get("total", 0) or 0
    ft_l   = s.get("fixtures", {}).get("loses",  {}).get("total", 0) or 0
    shots  = s.get("shots", {}).get("total", {}).get("total", 0) or 0
    shots_on = s.get("shots", {}).get("on",    {}).get("total", 0) or 0
    yellows  = sum(v.get("total", 0) or 0 for v in s.get("cards", {}).get("yellow", {}).values())
    reds     = sum(v.get("total", 0) or 0 for v in s.get("cards", {}).get("red",    {}).values())

    row = {
        "team_id": int(team_id), "team_name": str(team_name),
        "league_id": int(league_id), "season": int(season),
        "matches": played, "cached_date": _today(),
        "goals_scored":    gf,   "goals_conceded":   ga,
        "avg_scored":      round(gf/played, 3),
        "avg_conceded":    round(ga/played, 3),
        "clean_sheets":    cs,
        "wins": ft_w, "draws": ft_d, "losses": ft_l,
        "shots":           shots, "shots_on_target": shots_on,
        "yellow_cards":    yellows, "red_cards": reds,
        "avg_possession":  0,
    }
    _save_stats(row)
    return row


def get_last_matches(team_id, force=False):
    """GET /fixtures?team=id&last=10 — returns list of flat dicts, sorted recent-first."""
    if not force:
        cached = _cached_matches(team_id)
        if cached:
            st.markdown('<span class="cache-badge">💾 CACHED — last matches</span>', unsafe_allow_html=True)
            return cached

    data = _api_get("fixtures", {"team": team_id, "last": 10})
    st.markdown('<span class="api-badge">🌐 API — last matches</span>', unsafe_allow_html=True)
    rows = []
    for f in data.get("response", []):
        fx   = f.get("fixture", {})
        sc   = f.get("goals",   {})
        rows.append({
            "match_id":   fx.get("id"),
            "timestamp":  fx.get("timestamp", 0),
            "date":       fx.get("date", "")[:10],
            "home_team":  f.get("teams", {}).get("home", {}).get("name", ""),
            "away_team":  f.get("teams", {}).get("away", {}).get("name", ""),
            "home_score": sc.get("home", "?"),
            "away_score": sc.get("away", "?"),
            "league":     f.get("league", {}).get("name", ""),
        })
    rows.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    _save_matches(team_id, rows)
    return rows


def get_h2h(team_a_id, team_b_id, force=False):
    """GET /fixtures/headtohead?h2h=A-B&last=10"""
    if not force:
        cached = _cached_h2h(team_a_id, team_b_id)
        if cached is not None:
            st.markdown('<span class="cache-badge">💾 CACHED — H2H</span>', unsafe_allow_html=True)
            return cached

    data = _api_get("fixtures/headtohead", {"h2h": f"{team_a_id}-{team_b_id}", "last": 10})
    st.markdown('<span class="api-badge">🌐 API — H2H</span>', unsafe_allow_html=True)
    rows = []
    for f in data.get("response", []):
        sc = f.get("goals", {})
        h  = sc.get("home", "?"); a = sc.get("away", "?")
        try: total = int(h) + int(a)
        except: total = 0
        rows.append({
            "Date":  f["fixture"].get("date", "")[:10],
            "Home":  f["teams"]["home"]["name"],
            "Away":  f["teams"]["away"]["name"],
            "Score": f"{h}-{a}", "Total": total,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Date", ascending=False).head(10).reset_index(drop=True)
    _save_h2h(team_a_id, team_b_id, df)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# MATHS
# ─────────────────────────────────────────────────────────────────────────────

def poisson_ou(xg, lines=[0.5,1.5,2.5,3.5,4.0,5.0], max_g=10):
    out = []
    for line in lines:
        probs = [(math.e**-xg * xg**k)/math.factorial(k) for k in range(max_g+1)]
        u = sum(probs[:int(line)+1])
        out.append({"Line": f"O/U {line}", "Over %": f"{round((1-u)*100)}%", "Under %": f"{round(u*100)}%"})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def show_team_comparison(sa, sb):
    st.markdown('<div class="section-header">⚖️ Team Comparison</div>', unsafe_allow_html=True)
    rows = [
        ("Matches Played",    sa["matches"],         sb["matches"]),
        ("Wins",              sa["wins"],             sb["wins"]),
        ("Draws",             sa["draws"],            sb["draws"]),
        ("Losses",            sa["losses"],           sb["losses"]),
        ("Goals Scored",      sa["goals_scored"],     sb["goals_scored"]),
        ("Goals Conceded",    sa["goals_conceded"],   sb["goals_conceded"]),
        ("Avg Scored/Game",   sa["avg_scored"],       sb["avg_scored"]),
        ("Avg Conceded/Game", sa["avg_conceded"],     sb["avg_conceded"]),
        ("Clean Sheets",      sa["clean_sheets"],     sb["clean_sheets"]),
        ("Shots",             sa["shots"],            sb["shots"]),
        ("Shots on Target",   sa["shots_on_target"],  sb["shots_on_target"]),
        ("Yellow Cards",      sa["yellow_cards"],     sb["yellow_cards"]),
        ("Red Cards",         sa["red_cards"],        sb["red_cards"]),
    ]
    st.dataframe(
        pd.DataFrame(rows, columns=["Stat", sa["team_name"], sb["team_name"]]),
        use_container_width=True, hide_index=True
    )


def show_last_10(team_a_id, team_b_id, team_a_name, team_b_name, force=False):
    st.markdown('<div class="section-header">📅 Last 10 Games</div>', unsafe_allow_html=True)
    matches_a = get_last_matches(int(team_a_id), force=force)
    matches_b = get_last_matches(int(team_b_id), force=force)

    tab_a, tab_b = st.tabs([f"🏠 {team_a_name}", f"✈️ {team_b_name}"])

    for tab, team_name, matches in [(tab_a, team_a_name, matches_a), (tab_b, team_b_name, matches_b)]:
        with tab:
            if not matches:
                st.info(f"No recent match data for {team_name}.")
                continue

            html_rows = ""
            results = []
            gf_list, ga_list = [], []

            for m in matches[:10]:
                hs  = m.get("home_score", "?")
                as_ = m.get("away_score", "?")
                is_home = str(m.get("home_team","")).strip().lower() == team_name.strip().lower()
                venue   = "H" if is_home else "A"
                opponent = m.get("away_team","") if is_home else m.get("home_team","")
                vc = "#4090c0" if is_home else "#a06040"

                try:
                    hi, ai = int(hs), int(as_)
                    if hi == ai:
                        r, rc = "D", "#c0a030"
                    elif (is_home and hi > ai) or (not is_home and ai > hi):
                        r, rc = "W", "#30b060"
                    else:
                        r, rc = "L", "#c03040"
                    results.append(r)
                    gf_list.append(hi if is_home else ai)
                    ga_list.append(ai if is_home else hi)
                except:
                    r, rc = "?", "#607080"

                html_rows += (
                    f"<tr>"
                    f"<td style='padding:5px 10px;color:#8aa0b8'>{m.get('date','')}</td>"
                    f"<td style='padding:5px 10px;color:{vc};font-weight:700'>{venue}</td>"
                    f"<td style='padding:5px 10px;color:#c8d6e5'>{opponent}</td>"
                    f"<td style='padding:5px 10px;color:#607080;font-size:.75rem'>{m.get('league','')}</td>"
                    f"<td style='padding:5px 10px;font-family:IBM Plex Mono,monospace;color:#d0eaff'>{hs}–{as_}</td>"
                    f"<td style='padding:5px 10px;text-align:center;color:{rc};font-weight:700'>{r}</td>"
                    f"</tr>"
                )

            st.markdown(f"""
<table style="width:100%;border-collapse:collapse;font-family:IBM Plex Mono,monospace;
              font-size:.82rem;background:#0b1422;border:1px solid #152030;border-radius:3px">
  <thead><tr style="border-bottom:1px solid #1e3050">
    <th style="padding:6px 10px;color:#5a80a0;text-align:left">Date</th>
    <th style="padding:6px 10px;color:#5a80a0;text-align:left">H/A</th>
    <th style="padding:6px 10px;color:#5a80a0;text-align:left">Opponent</th>
    <th style="padding:6px 10px;color:#5a80a0;text-align:left">Competition</th>
    <th style="padding:6px 10px;color:#5a80a0;text-align:left">Score</th>
    <th style="padding:6px 10px;color:#5a80a0;text-align:center">Result</th>
  </tr></thead>
  <tbody>{html_rows}</tbody>
</table>""", unsafe_allow_html=True)

            if results:
                w = results.count("W"); d = results.count("D"); l = results.count("L")
                avg_gf = round(sum(gf_list)/len(gf_list), 2) if gf_list else "—"
                avg_ga = round(sum(ga_list)/len(ga_list), 2) if ga_list else "—"
                form_html = " ".join(
                    f'<span style="color:{"#30b060" if r=="W" else "#c0a030" if r=="D" else "#c03040"}'
                    f';font-weight:700">{r}</span>'
                    for r in results
                )
                st.markdown(f"""
<div class="math-box" style="margin-top:10px">
<b>Form (last {len(results)} games):</b> {form_html}<br>
W {w} · D {d} · L {l} &nbsp;|&nbsp;
Avg scored: <span class="result">{avg_gf}</span> &nbsp;·&nbsp;
Avg conceded: <span class="result">{avg_ga}</span>
</div>""", unsafe_allow_html=True)


def show_h2h_section(h2h_df, an, bn):
    st.markdown('<div class="section-header">⚔️ Head-to-Head History</div>', unsafe_allow_html=True)
    if h2h_df.empty:
        st.info(f"No H2H matches found for {an} vs {bn}."); return
    st.dataframe(h2h_df, use_container_width=True, hide_index=True)
    avg = round(h2h_df["Total"].mean(), 2)
    st.markdown(f"""
<div class="math-box">
<b>H2H Summary ({len(h2h_df)} games)</b><br>
Avg goals/game: <span class="result">{avg}</span> &nbsp;·&nbsp;
Min: {int(h2h_df["Total"].min())} &nbsp;·&nbsp;
Max: {int(h2h_df["Total"].max())}
</div>""", unsafe_allow_html=True)


def show_ou_h2h(h2h_df, an, bn):
    st.markdown('<div class="section-header">📊 Over / Under — H2H</div>', unsafe_allow_html=True)
    if h2h_df.empty:
        st.info("No H2H data available."); return
    df = h2h_df.head(10); total = len(df)
    rows = []
    for line in [1.5, 2.5, 3.5]:
        ov = int((df["Total"] > line).sum()); un = int((df["Total"] < line).sum())
        rows.append({"Line": f"O/U {line}", "Over": ov, "Under": un,
                     "Over %": f"{round(ov/total*100)}%", "Under %": f"{round(un/total*100)}%",
                     "Avg Goals": round(df["Total"].mean(), 2), "Games": total})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    avg_g = round(df["Total"].mean(), 2)
    ex_o  = int((df["Total"] > 2.5).sum())
    st.markdown(f"""
<div class="math-box">
<b>O/U Math ({an} vs {bn})</b><br>
<span class="formula">Over % = games where Total > Line / total × 100</span><br>
Games: {total} · Avg goals: {avg_g}<br>
O/U 2.5 over count: {ex_o}/{total} = <span class="result">{round(ex_o/total*100)}%</span>
</div>""", unsafe_allow_html=True)


def show_poisson(sa, sb):
    st.markdown('<div class="section-header">📐 Poisson Over / Under Model</div>', unsafe_allow_html=True)
    a_s=float(sa["avg_scored"]); a_c=float(sa["avg_conceded"])
    b_s=float(sb["avg_scored"]); b_c=float(sb["avg_conceded"])
    xg_a=round((a_s+b_c)/2, 3); xg_b=round((b_s+a_c)/2, 3); blend=round(xg_a+xg_b, 3)
    an=sa["team_name"]; bn=sb["team_name"]

    st.markdown(f"""
<div class="math-box">
<b>xG Derivation</b><br>
<span class="formula">xG_A = (AvgScored_A + AvgConceded_B) / 2</span><br>
<span class="formula">xG_B = (AvgScored_B + AvgConceded_A) / 2</span><br><br>
<b>{an}:</b> ({a_s} + {b_c}) / 2 = <span class="result">{xg_a}</span><br>
<b>{bn}:</b> ({b_s} + {a_c}) / 2 = <span class="result">{xg_b}</span><br>
<b>Blended:</b> {xg_a} + {xg_b} = <span class="result">{blend}</span>
</div>""", unsafe_allow_html=True)

    c1,c2,c3 = st.columns(3)
    c1.metric(f"{an} xG", xg_a); c2.metric(f"{bn} xG", xg_b); c3.metric("Blended xG", blend)

    rows = []
    for label, xg in [(an, xg_a), (bn, xg_b), ("Blended", blend)]:
        for e in poisson_ou(xg):
            rows.append({"Model": label, **e, "xG": xg})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("🔬 Full Poisson breakdown (Blended xG)"):
        mu=blend; data=[]; cum=0
        for k in range(11):
            p=(math.e**-mu * mu**k)/math.factorial(k); cum+=p
            data.append({"k":k, "P(X=k)":f"{p:.4f}", "P%":f"{round(p*100,2)}%",
                         "Cumulative":f"{round(cum*100,2)}%"})
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)


def show_score_matrix(sa, sb):
    st.markdown('<div class="section-header">🎲 Score Probability Matrix</div>', unsafe_allow_html=True)
    an=sa["team_name"]; bn=sb["team_name"]
    xg_a=round((float(sa["avg_scored"])+float(sb["avg_conceded"]))/2, 3)
    xg_b=round((float(sb["avg_scored"])+float(sa["avg_conceded"]))/2, 3)
    G=6; grid=np.zeros((G+1,G+1))
    for i in range(G+1):
        for j in range(G+1):
            grid[i][j] = ((math.e**-xg_a * xg_a**i / math.factorial(i)) *
                          (math.e**-xg_b * xg_b**j / math.factorial(j)))
    hw=float(np.sum(np.tril(grid,-1))); dr=float(np.sum(np.diag(grid))); aw=float(np.sum(np.triu(grid,1)))
    c1,c2,c3 = st.columns(3)
    c1.metric(f"{an} Win", f"{hw:.1%}"); c2.metric("Draw", f"{dr:.1%}"); c3.metric(f"{bn} Win", f"{aw:.1%}")
    labels=[str(i) for i in range(G+1)]
    df_g=pd.DataFrame(grid*100, index=labels, columns=labels).round(2)
    df_g.index.name=f"← {an}"; df_g.columns.name=f"{bn} →"
    st.markdown("**Score Probability Grid (%) — rows = home goals, cols = away goals**")
    st.dataframe(df_g, use_container_width=True)
    flat=sorted([(grid[i][j],i,j) for i in range(G+1) for j in range(G+1)], reverse=True)
    st.markdown("**Top 8 Most Likely Scorelines**")
    st.dataframe(pd.DataFrame([{"Score":f"{an} {i}-{j} {bn}","Prob":f"{round(p*100,2)}%"}
                                for p,i,j in flat[:8]]),
                 use_container_width=True, hide_index=True)


def show_btts(sa, sb):
    st.markdown('<div class="section-header">🔥 Both Teams to Score (BTTS)</div>', unsafe_allow_html=True)
    an=sa["team_name"]; bn=sb["team_name"]
    xg_a=round((float(sa["avg_scored"])+float(sb["avg_conceded"]))/2, 3)
    xg_b=round((float(sb["avg_scored"])+float(sa["avg_conceded"]))/2, 3)
    pa=1-math.exp(-xg_a); pb=1-math.exp(-xg_b)
    btts=round(pa*pb*100, 2); no=round((1-pa*pb)*100, 2)
    st.markdown(f"""
<div class="math-box">
<b>BTTS Formula</b><br>
<span class="formula">P(score≥1) = 1 - e^-xG</span><br>
<span class="formula">P(BTTS) = P(A scores) × P(B scores)</span><br><br>
<b>{an}</b> xG={xg_a} → P(scores)=<span class="result">{round(pa*100,2)}%</span><br>
<b>{bn}</b> xG={xg_b} → P(scores)=<span class="result">{round(pb*100,2)}%</span><br>
P(BTTS) = <span class="result">{btts}%</span> &nbsp;·&nbsp;
P(No BTTS) = <span class="result">{no}%</span>
</div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric(f"{an} xG", xg_a); c2.metric(f"{bn} xG", xg_b)
    c3.metric("BTTS %", f"{btts}%"); c4.metric("No BTTS %", f"{no}%")


# ─────────────────────────────────────────────────────────────────────────────
# CACHE STATUS SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

def show_cache_status():
    st.markdown("### 💾 Cache Status")
    files = [("Team Search", CACHE_TEAM_SEARCH), ("Team Stats", CACHE_TEAM_STATS),
             ("Standings",   CACHE_STANDINGS),   ("H2H",        CACHE_H2H),
             ("Last Matches",CACHE_LAST_MATCHES)]
    total = 0
    for label, path in files:
        df=_load(path); n=len(df) if not df.empty else 0; total+=n
        c = "#40b060" if n > 0 else "#506070"
        st.markdown(f'<span style="color:{c};font-size:.72rem">{"✅" if n else "○"} {label}: {n} rows</span>',
                    unsafe_allow_html=True)
    st.markdown(f'<span style="color:#6090b0;font-size:.70rem">Total: {total} cached rows</span>',
                unsafe_allow_html=True)
    if st.button("🗑️ Clear All Caches", use_container_width=True):
        for _, p in files:
            if os.path.exists(p): os.remove(p)
        st.success("All caches cleared."); st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# MASTER ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def smart_analyze(team_a_input, team_b_input, force=False):

    # 1. Search both teams
    with st.spinner(f"Finding '{team_a_input}'..."):
        a_id, a_name, a_league, a_season = search_team(team_a_input, force=force)
    with st.spinner(f"Finding '{team_b_input}'..."):
        b_id, b_name, b_league, b_season = search_team(team_b_input, force=force)

    if not a_id:
        st.error(f"❌ Team not found: **{team_a_input}**"); return
    if not b_id:
        st.error(f"❌ Team not found: **{team_b_input}**"); return

    st.success(f"✅ **{a_name}** (ID {a_id})  ·  **{b_name}** (ID {b_id})")

    league_id = a_league or b_league
    season    = a_season or b_season or CURRENT_SEASON

    if not league_id:
        st.error("Could not detect league for these teams."); return

    st.caption(f"🏟️ League ID: {league_id}  ·  Season: {season}")

    # 2. Standings
    with st.spinner("Loading standings..."):
        sdf = get_standings(league_id, season, force=force)
    if not sdf.empty:
        with st.expander("📋 League Standings"):
            st.dataframe(sdf, use_container_width=True, hide_index=True)
    st.divider()

    # 3. Team stats
    with st.spinner("Loading team stats..."):
        sa = get_team_stats(a_id, a_name, league_id, season, force=force)
        sb = get_team_stats(b_id, b_name, league_id, season, force=force)

    if not sa or not sb:
        st.error("Could not load season stats for one or both teams."); return

    # 4. Render all sections
    show_team_comparison(sa, sb)
    st.divider()

    with st.spinner("Loading last 10 matches..."):
        show_last_10(a_id, b_id, a_name, b_name, force=force)
    st.divider()

    with st.spinner("Loading H2H..."):
        h2h_df = get_h2h(a_id, b_id, force=force)

    show_h2h_section(h2h_df, a_name, b_name)
    st.divider()
    show_ou_h2h(h2h_df, a_name, b_name)
    st.divider()
    show_poisson(sa, sb)
    st.divider()
    show_score_matrix(sa, sb)
    st.divider()
    show_btts(sa, sb)


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR + MAIN UI
# ─────────────────────────────────────────────────────────────────────────────

if "triggered" not in st.session_state:
    st.session_state.triggered = False

with st.sidebar:
    st.markdown("## ⚙️ Match Setup")
    team_a_input = st.text_input("🏠 Home Team", "Liverpool")
    team_b_input = st.text_input("✈️ Away Team", "Arsenal")
    st.divider()
    force_update = st.checkbox("♻️ Force API Refresh (bypass cache)")
    st.divider()
    if st.button("🚀 Analyse Matchup", type="primary", use_container_width=True):
        st.session_state.triggered = True
        st.session_state.team_a  = team_a_input
        st.session_state.team_b  = team_b_input
        st.session_state.force   = force_update
    st.divider()
    show_cache_status()
    st.divider()
    st.markdown("""
<small style="color:#405060">
<b>Powered by API-Football v3</b><br>
• Team comparison<br>
• Last 10 games per team (with competition)<br>
• H2H history (last 10 meetings)<br>
• Over/Under — H2H + Poisson<br>
• Score probability matrix<br>
• BTTS probability<br>
• Full maths shown for every model<br><br>
Cache TTL:<br>
Search 30d · Stats 3d<br>
Standings/H2H/Matches 1d
</small>
""", unsafe_allow_html=True)

if not st.session_state.triggered:
    st.title("⚽ Pro Sports Analytics")
    st.markdown("""
Enter two team names in the sidebar and click **Analyse Matchup**.

Powered by **API-Football v3** — 1,200+ leagues, real stats, proper H2H.
All results are cached to CSV so the same lookup never costs a second API call.

🟢 Green badge = served from cache · 🟠 Orange badge = live API call
""")
else:
    st.title(f"⚽  {st.session_state.team_a}  vs  {st.session_state.team_b}")
    st.caption(f"Analysis: {datetime.today().strftime('%d %b %Y %H:%M')}")
    smart_analyze(st.session_state.team_a, st.session_state.team_b, st.session_state.force)
