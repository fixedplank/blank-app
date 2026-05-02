import streamlit as st
import requests
import pandas as pd
import math
import os
import numpy as np
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SETUP
# ─────────────────────────────────────────────────────────────────────────────

RAPIDAPI_KEY = "41a4c82369msha52a319dc9ed7fcp1dc251jsn822df539c4cd"
HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "sofascore.p.rapidapi.com",
    "Content-Type": "application/json"
}
BASE_URL = "https://sofascore.p.rapidapi.com"

# ── Cache file paths ──────────────────────────────────────────────────────────
CACHE_TEAM_STATS    = "team_stats_cache.csv"       # season stats per team
CACHE_TEAM_SEARCH   = "team_search_cache.csv"      # name → id lookups
CACHE_TEAM_LEAGUE   = "team_league_cache.csv"      # team_id → tournament/season
CACHE_STANDINGS     = "standings_cache.csv"        # standings per tournament/season
CACHE_H2H           = "h2h_cache.csv"              # h2h results per team pair
CACHE_LAST_MATCHES  = "last_matches_cache.csv"     # recent matches per team

# How many days before a cache entry expires (set high to save credits)
CACHE_TTL_DAYS = 3

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG & STYLES
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Pro Sports Analytics", page_icon="⚽", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');

html, body, [class*="css"]          { font-family: 'IBM Plex Mono', monospace; }
h1, h2, h3, h4                      { font-family: 'Barlow Condensed', sans-serif; letter-spacing: 0.02em; }

.stApp                               { background: #080c14; color: #c8d6e5; }

section[data-testid="stSidebar"]     { background: #050810 !important; border-right: 1px solid #151f30; }
section[data-testid="stSidebar"] *   { color: #90a8c0 !important; }
section[data-testid="stSidebar"] label { color: #6a8aaa !important; font-size: 0.72rem; }

.stButton > button                   { background: transparent; border: 1px solid #1e3050;
                                       color: #6ab0e8; font-family: 'IBM Plex Mono', monospace;
                                       font-size: 0.78rem; transition: all 0.15s; border-radius: 3px; }
.stButton > button:hover             { background: #0e1e30; border-color: #3a70b0; color: #b0d8ff; }
.stButton > button[kind="primary"]   { background: #0a2545; border: 1px solid #2a70c0;
                                       color: #d0eaff; font-weight: 700; font-size: 0.88rem;
                                       letter-spacing: 0.06em; }
.stButton > button[kind="primary"]:hover { background: #0e3060; }

div[data-testid="metric-container"]  { background: #0b1422; border: 1px solid #152030;
                                       border-radius: 3px; padding: 10px 14px; }
div[data-testid="metric-container"] label { color: #5a80a0 !important; font-size: 0.68rem; }

.math-box { background: #0b1828; border-left: 3px solid #2060a0; border-radius: 3px;
            padding: 14px 18px; margin: 10px 0; font-family: 'IBM Plex Mono', monospace;
            font-size: 0.82rem; color: #a8cce8; line-height: 1.7; }
.math-box b { color: #d0eaff; }
.math-box .result { color: #50d090; font-weight: 700; font-size: 0.95rem; }
.math-box .formula { color: #7aacda; font-style: italic; }

.cache-badge { background: #0a2010; border: 1px solid #1a5030; border-radius: 3px;
               padding: 2px 8px; font-size: 0.7rem; color: #40b060;
               font-family: 'IBM Plex Mono', monospace; }
.api-badge   { background: #201005; border: 1px solid #604010; border-radius: 3px;
               padding: 2px 8px; font-size: 0.7rem; color: #c07030;
               font-family: 'IBM Plex Mono', monospace; }

.section-header { font-family: 'Barlow Condensed', sans-serif; font-size: 1.6rem;
                  font-weight: 700; color: #d8eeff; border-bottom: 1px solid #152030;
                  padding-bottom: 4px; margin-top: 1.5rem; }

hr { border-color: #101a28; margin: 1.8rem 0; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# GENERIC CACHE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_csv(path: str) -> pd.DataFrame:
    """Load a cache CSV, return empty DataFrame if missing."""
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def _save_csv(df: pd.DataFrame, path: str):
    """Save DataFrame to CSV."""
    df.to_csv(path, index=False)


def _is_fresh(cached_date_str: str, ttl_days: int = CACHE_TTL_DAYS) -> bool:
    """Return True if the cached_date is within TTL."""
    try:
        cached_dt = datetime.strptime(str(cached_date_str), "%Y-%m-%d")
        return (datetime.today() - cached_dt).days <= ttl_days
    except Exception:
        return False


def _today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────────────────────
# TEAM STATS CACHE  (original behaviour preserved)
# ─────────────────────────────────────────────────────────────────────────────

def get_cached_team_stats(team_id, tournament_id, season_id):
    df = _load_csv(CACHE_TEAM_STATS)
    if df.empty:
        return None
    m = df[
        (df["team_id"]       == int(team_id)) &
        (df["tournament_id"] == int(tournament_id)) &
        (df["season_id"]     == int(season_id))
    ]
    if m.empty:
        return None
    row = m.iloc[0]
    if not _is_fresh(row.get("cached_date", "")):
        return None
    return row.to_dict()


def save_team_stats(stats_row: dict):
    df   = _load_csv(CACHE_TEAM_STATS)
    mask = (
        (df["team_id"]       == stats_row["team_id"]) &
        (df["tournament_id"] == stats_row["tournament_id"]) &
        (df["season_id"]     == stats_row["season_id"])
    ) if not df.empty else pd.Series([], dtype=bool)
    if not df.empty and mask.any():
        df.loc[mask, list(stats_row.keys())] = list(stats_row.values())
    else:
        df = pd.concat([df, pd.DataFrame([stats_row])], ignore_index=True)
    _save_csv(df, CACHE_TEAM_STATS)


# ─────────────────────────────────────────────────────────────────────────────
# TEAM SEARCH CACHE  — saves team name → id mapping
# ─────────────────────────────────────────────────────────────────────────────

def get_cached_team_search(team_name: str):
    """Return (team_id, team_name) from cache or None."""
    df = _load_csv(CACHE_TEAM_SEARCH)
    if df.empty:
        return None
    m = df[df["query"].str.lower() == team_name.strip().lower()]
    if m.empty:
        return None
    row = m.iloc[0]
    if not _is_fresh(row.get("cached_date", ""), ttl_days=30):  # search results stable for 30 days
        return None
    return int(row["team_id"]), str(row["team_name"])


def save_team_search(query: str, team_id: int, team_name: str):
    df   = _load_csv(CACHE_TEAM_SEARCH)
    mask = df["query"].str.lower() == query.strip().lower() if not df.empty else pd.Series([], dtype=bool)
    row  = {"query": query.strip().lower(), "team_id": team_id,
            "team_name": team_name, "cached_date": _today()}
    if not df.empty and mask.any():
        df.loc[mask, list(row.keys())] = list(row.values())
    else:
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save_csv(df, CACHE_TEAM_SEARCH)


# ─────────────────────────────────────────────────────────────────────────────
# TEAM LEAGUE CACHE  — saves team_id → tournament/season/league
# ─────────────────────────────────────────────────────────────────────────────

def get_cached_team_league(team_id: int):
    df = _load_csv(CACHE_TEAM_LEAGUE)
    if df.empty:
        return None
    m = df[df["team_id"] == int(team_id)]
    if m.empty:
        return None
    row = m.iloc[0]
    if not _is_fresh(row.get("cached_date", ""), ttl_days=7):
        return None
    return str(row["tournament_id"]), str(row["season_id"]), str(row["league_name"])


def save_team_league(team_id: int, tournament_id: str, season_id: str, league_name: str):
    df   = _load_csv(CACHE_TEAM_LEAGUE)
    mask = df["team_id"] == int(team_id) if not df.empty else pd.Series([], dtype=bool)
    row  = {"team_id": int(team_id), "tournament_id": tournament_id,
            "season_id": season_id, "league_name": league_name, "cached_date": _today()}
    if not df.empty and mask.any():
        df.loc[mask, list(row.keys())] = list(row.values())
    else:
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save_csv(df, CACHE_TEAM_LEAGUE)


# ─────────────────────────────────────────────────────────────────────────────
# STANDINGS CACHE
# ─────────────────────────────────────────────────────────────────────────────

def get_cached_standings(tournament_id: str, season_id: str):
    df = _load_csv(CACHE_STANDINGS)
    if df.empty:
        return None
    m = df[
        (df["tournament_id"].astype(str) == str(tournament_id)) &
        (df["season_id"].astype(str)     == str(season_id))
    ]
    if m.empty:
        return None
    # Check freshness on first row
    if not _is_fresh(m.iloc[0].get("cached_date", ""), ttl_days=1):
        return None
    return m.drop(columns=["tournament_id", "season_id", "cached_date"], errors="ignore")


def save_standings(tournament_id: str, season_id: str, standings_df: pd.DataFrame):
    if standings_df.empty:
        return
    df_to_save = standings_df.copy()
    df_to_save["tournament_id"] = tournament_id
    df_to_save["season_id"]     = season_id
    df_to_save["cached_date"]   = _today()

    existing = _load_csv(CACHE_STANDINGS)
    if not existing.empty:
        existing = existing[
            ~((existing["tournament_id"].astype(str) == str(tournament_id)) &
              (existing["season_id"].astype(str)     == str(season_id)))
        ]
    merged = pd.concat([existing, df_to_save], ignore_index=True)
    _save_csv(merged, CACHE_STANDINGS)


# ─────────────────────────────────────────────────────────────────────────────
# H2H CACHE
# ─────────────────────────────────────────────────────────────────────────────

def _h2h_key(id_a: int, id_b: int) -> str:
    """Canonical key regardless of order."""
    return f"{min(id_a, id_b)}_{max(id_a, id_b)}"


def get_cached_h2h(team_a_id: int, team_b_id: int):
    df = _load_csv(CACHE_H2H)
    if df.empty:
        return None
    key = _h2h_key(int(team_a_id), int(team_b_id))
    m   = df[df["h2h_key"] == key]
    if m.empty:
        return None
    if not _is_fresh(m.iloc[0].get("cached_date", ""), ttl_days=1):
        return None
    return m.drop(columns=["h2h_key", "cached_date"], errors="ignore")


def save_h2h(team_a_id: int, team_b_id: int, h2h_df: pd.DataFrame):
    if h2h_df.empty:
        return
    key        = _h2h_key(int(team_a_id), int(team_b_id))
    df_to_save = h2h_df.copy()
    df_to_save["h2h_key"]     = key
    df_to_save["cached_date"] = _today()

    existing = _load_csv(CACHE_H2H)
    if not existing.empty:
        existing = existing[existing["h2h_key"] != key]
    merged = pd.concat([existing, df_to_save], ignore_index=True)
    _save_csv(merged, CACHE_H2H)


# ─────────────────────────────────────────────────────────────────────────────
# LAST MATCHES CACHE  (used by shotmap / heatmap)
# ─────────────────────────────────────────────────────────────────────────────

def get_cached_last_matches(team_id: int):
    df = _load_csv(CACHE_LAST_MATCHES)
    if df.empty:
        return None
    m = df[df["team_id"] == int(team_id)]
    if m.empty:
        return None
    if not _is_fresh(m.iloc[0].get("cached_date", ""), ttl_days=1):
        return None
    return m.drop(columns=["team_id", "cached_date"], errors="ignore").to_dict("records")


def save_last_matches(team_id: int, events: list):
    """Store flattened event metadata (not full event dicts) for shotmap/heatmap selectors."""
    rows = []
    for e in events:
        if e.get("status", {}).get("type") != "finished":
            continue
        h     = e.get("homeScore", {}).get("display", "?")
        a     = e.get("awayScore", {}).get("display", "?")
        date  = pd.Timestamp(e["startTimestamp"], unit="s").strftime("%Y-%m-%d")
        rows.append({
            "team_id":    int(team_id),
            "match_id":   e["id"],
            "date":       date,
            "home_team":  e["homeTeam"]["name"],
            "away_team":  e["awayTeam"]["name"],
            "home_score": h,
            "away_score": a,
            "cached_date": _today(),
        })
    if not rows:
        return
    df_new  = pd.DataFrame(rows)
    existing = _load_csv(CACHE_LAST_MATCHES)
    if not existing.empty:
        existing = existing[existing["team_id"] != int(team_id)]
    merged = pd.concat([existing, df_new], ignore_index=True)
    _save_csv(merged, CACHE_LAST_MATCHES)


# ─────────────────────────────────────────────────────────────────────────────
# API FUNCTIONS  (each one checks cache first)
# ─────────────────────────────────────────────────────────────────────────────

def search_team(team_name: str, force=False):
    if not force:
        cached = get_cached_team_search(team_name)
        if cached:
            st.markdown('<span class="cache-badge">💾 CACHED — search</span>', unsafe_allow_html=True)
            return cached
    r    = requests.get(f"{BASE_URL}/teams/search", headers=HEADERS, params={"name": team_name})
    data = r.json()
    teams = data.get("teams", [])
    if not teams:
        return None, None
    team = teams[0]
    st.markdown('<span class="api-badge">🌐 API — search</span>', unsafe_allow_html=True)
    save_team_search(team_name, team["id"], team["name"])
    return team["id"], team["name"]


def get_team_league(team_id, team_name, force=False):
    if not force:
        cached = get_cached_team_league(int(team_id))
        if cached:
            st.markdown('<span class="cache-badge">💾 CACHED — league detect</span>', unsafe_allow_html=True)
            return cached
    r      = requests.get(f"{BASE_URL}/teams/get-last-matches", headers=HEADERS, params={"teamId": team_id})
    events = r.json().get("events", [])
    # Also cache the last-matches data while we have it
    save_last_matches(int(team_id), events)
    st.markdown('<span class="api-badge">🌐 API — league detect</span>', unsafe_allow_html=True)
    for e in events:
        ut     = e.get("tournament", {}).get("uniqueTournament", {})
        season = e.get("season", {})
        if ut.get("id") and season.get("id"):
            tid = str(ut["id"])
            sid = str(season["id"])
            lname = ut.get("name", "Unknown")
            save_team_league(int(team_id), tid, sid, lname)
            return tid, sid, lname
    return None, None, None


def get_league_standings(tournament_id, season_id, force=False):
    if not force:
        cached = get_cached_standings(tournament_id, season_id)
        if cached is not None:
            st.markdown('<span class="cache-badge">💾 CACHED — standings</span>', unsafe_allow_html=True)
            return cached
    r    = requests.get(f"{BASE_URL}/tournaments/get-standings", headers=HEADERS,
                        params={"tournamentId": tournament_id, "seasonId": season_id})
    rows = r.json().get("standings", [{}])[0].get("rows", [])
    st.markdown('<span class="api-badge">🌐 API — standings</span>', unsafe_allow_html=True)
    if not rows:
        return pd.DataFrame()
    table = []
    for row in rows:
        table.append({
            "Rank": row.get("position"), "Team": row.get("team", {}).get("name"),
            "W": row.get("wins"), "D": row.get("draws"), "L": row.get("losses"),
            "GF": row.get("scoresFor"), "GA": row.get("scoresAgainst"), "Pts": row.get("points")
        })
    df = pd.DataFrame(table)
    save_standings(tournament_id, season_id, df)
    return df


def fetch_team_stats_from_api(team_id, team_name, tournament_id, season_id):
    r    = requests.get(f"{BASE_URL}/teams/get-statistics", headers=HEADERS,
                        params={"teamId": team_id, "tournamentId": tournament_id, "seasonId": season_id})
    data = r.json().get("statistics", {})
    if not data:
        return None
    matches = data.get("matches", 1) or 1
    st.markdown('<span class="api-badge">🌐 API — team stats</span>', unsafe_allow_html=True)
    return {
        "team_id": int(team_id), "team_name": team_name,
        "tournament_id": int(tournament_id), "season_id": int(season_id),
        "matches": matches, "cached_date": _today(),
        "goals_scored":              data.get("goalsScored", 0),
        "goals_conceded":            data.get("goalsConceded", 0),
        "avg_scored":                round(data.get("goalsScored", 0)   / matches, 3),
        "avg_conceded":              round(data.get("goalsConceded", 0) / matches, 3),
        "corners_for":               data.get("corners", 0),
        "corners_against":           data.get("cornersAgainst", 0),
        "avg_corners_for":           round(data.get("corners", 0)        / matches, 3),
        "avg_corners_against":       round(data.get("cornersAgainst", 0) / matches, 3),
        "avg_total_corners":         round((data.get("corners", 0) + data.get("cornersAgainst", 0)) / matches, 3),
        "shots":                     data.get("shots", 0),
        "shots_on_target":           data.get("shotsOnTarget", 0),
        "shots_against":             data.get("shotsAgainst", 0),
        "shots_on_target_against":   data.get("shotsOnTargetAgainst", 0),
        "avg_possession":            data.get("averageBallPossession", 0),
        "yellow_cards":              data.get("yellowCards", 0),
        "red_cards":                 data.get("redCards", 0),
        "clean_sheets":              data.get("cleanSheets", 0),
    }


def get_team_stats(team_id, team_name, tournament_id, season_id, force_update=False):
    if not force_update:
        cached = get_cached_team_stats(team_id, tournament_id, season_id)
        if cached:
            st.markdown('<span class="cache-badge">💾 CACHED — team stats</span>', unsafe_allow_html=True)
            return cached
    stats = fetch_team_stats_from_api(team_id, team_name, tournament_id, season_id)
    if stats is None:
        return None
    save_team_stats(stats)
    return stats


def get_last_matches_for_team(team_id: int, force=False):
    """Fetch last finished matches for a team independently. Returns all cached rows."""
    if not force:
        cached = get_cached_last_matches(int(team_id))
        if cached:
            st.markdown('<span class="cache-badge">💾 CACHED — last matches</span>', unsafe_allow_html=True)
            return cached
    r      = requests.get(f"{BASE_URL}/teams/get-last-matches", headers=HEADERS, params={"teamId": team_id})
    events = [e for e in r.json().get("events", []) if e.get("status", {}).get("type") == "finished"]
    save_last_matches(int(team_id), events)
    st.markdown('<span class="api-badge">🌐 API — last matches</span>', unsafe_allow_html=True)
    rows = []
    for e in events:
        h    = e.get("homeScore", {}).get("display", "?")
        a    = e.get("awayScore", {}).get("display", "?")
        date = pd.Timestamp(e["startTimestamp"], unit="s").strftime("%Y-%m-%d")
        rows.append({
            "match_id":   e["id"],
            "date":       date,
            "home_team":  e["homeTeam"]["name"],
            "away_team":  e["awayTeam"]["name"],
            "home_score": h,
            "away_score": a,
        })
    return rows  # all rows — callers slice as needed


def get_h2h_matches(team_a_id, team_b_id, team_a_name, team_b_name, last_n=10, force=False):
    if not force:
        cached = get_cached_h2h(int(team_a_id), int(team_b_id))
        if cached is not None:
            st.markdown('<span class="cache-badge">💾 CACHED — H2H</span>', unsafe_allow_html=True)
            return cached

    # Fetch last matches for both teams (also cached individually)
    r        = requests.get(f"{BASE_URL}/teams/get-last-matches", headers=HEADERS, params={"teamId": team_a_id})
    events_a = {e["id"]: e for e in r.json().get("events", []) if e.get("status", {}).get("type") == "finished"}
    save_last_matches(int(team_a_id), list(events_a.values()))

    r        = requests.get(f"{BASE_URL}/teams/get-last-matches", headers=HEADERS, params={"teamId": team_b_id})
    events_b = {e["id"]: e for e in r.json().get("events", []) if e.get("status", {}).get("type") == "finished"}
    save_last_matches(int(team_b_id), list(events_b.values()))

    st.markdown('<span class="api-badge">🌐 API — H2H</span>', unsafe_allow_html=True)

    matches = []
    for match_id in set(events_a.keys()) & set(events_b.keys()):
        e    = events_a[match_id]
        home = e.get("homeScore", {}).get("display")
        away = e.get("awayScore", {}).get("display")
        if home is None or away is None:
            continue
        matches.append({
            "Date":  pd.Timestamp(e["startTimestamp"], unit="s").strftime("%Y-%m-%d"),
            "Home":  e["homeTeam"]["name"], "Away": e["awayTeam"]["name"],
            "Score": f"{home}-{away}", "Total": int(home) + int(away)
        })

    df = pd.DataFrame(matches)
    if df.empty:
        return df
    df = df.sort_values("Date", ascending=False).head(last_n)
    save_h2h(int(team_a_id), int(team_b_id), df)
    return df


def poisson_ou_probability(expected_goals, lines=[0.5, 1.5, 2.5, 3.5, 4, 5], max_goals=10):
    results = []
    for line in lines:
        probs      = [(math.e ** -expected_goals * expected_goals ** x) / math.factorial(x)
                      for x in range(max_goals + 1)]
        cutoff     = int(line)
        under_prob = sum(probs[:cutoff + 1])
        over_prob  = sum(probs[cutoff + 1:])
        results.append({
            "Line":    f"O/U {line}",
            "Over %":  f"{round(over_prob  * 100)}%",
            "Under %": f"{round(under_prob * 100)}%",
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# CACHE STATUS SIDEBAR WIDGET
# ─────────────────────────────────────────────────────────────────────────────

def show_cache_status():
    st.markdown("### 💾 Cache Status")
    files = [
        ("Team Stats",    CACHE_TEAM_STATS),
        ("Team Search",   CACHE_TEAM_SEARCH),
        ("League Detect", CACHE_TEAM_LEAGUE),
        ("Standings",     CACHE_STANDINGS),
        ("H2H History",   CACHE_H2H),
        ("Last Matches",  CACHE_LAST_MATCHES),
    ]
    total_rows = 0
    for label, path in files:
        df = _load_csv(path)
        rows = len(df) if not df.empty else 0
        total_rows += rows
        color = "#40b060" if rows > 0 else "#506070"
        st.markdown(
            f'<span style="color:{color};font-size:0.72rem">{"✅" if rows else "○"} {label}: {rows} rows</span>',
            unsafe_allow_html=True
        )
    st.markdown(f'<span style="color:#6090b0;font-size:0.70rem">Total cached rows: {total_rows}</span>',
                unsafe_allow_html=True)

    if st.button("🗑️ Clear All Caches", use_container_width=True):
        for _, path in files:
            if os.path.exists(path):
                os.remove(path)
        st.success("All caches cleared.")
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def show_team_comparison(stats_a, stats_b):
    st.markdown('<div class="section-header">⚖️ Team Comparison</div>', unsafe_allow_html=True)
    rows = [
        ("Matches Played",      stats_a["matches"],              stats_b["matches"]),
        ("Goals Scored",        stats_a["goals_scored"],         stats_b["goals_scored"]),
        ("Goals Conceded",      stats_a["goals_conceded"],       stats_b["goals_conceded"]),
        ("Avg Scored / Game",   stats_a["avg_scored"],           stats_b["avg_scored"]),
        ("Avg Conceded / Game", stats_a["avg_conceded"],         stats_b["avg_conceded"]),
        ("Clean Sheets",        stats_a["clean_sheets"],         stats_b["clean_sheets"]),
        ("Corners For",         stats_a["corners_for"],          stats_b["corners_for"]),
        ("Corners Against",     stats_a["corners_against"],      stats_b["corners_against"]),
        ("Avg Corners For",     stats_a["avg_corners_for"],      stats_b["avg_corners_for"]),
        ("Avg Corners Against", stats_a["avg_corners_against"],  stats_b["avg_corners_against"]),
        ("Avg Total Corners",   stats_a["avg_total_corners"],    stats_b["avg_total_corners"]),
        ("Shots",               stats_a["shots"],                stats_b["shots"]),
        ("Shots on Target",     stats_a["shots_on_target"],      stats_b["shots_on_target"]),
        ("Avg Possession %",    stats_a["avg_possession"],       stats_b["avg_possession"]),
        ("Yellow Cards",        stats_a["yellow_cards"],         stats_b["yellow_cards"]),
        ("Red Cards",           stats_a["red_cards"],            stats_b["red_cards"]),
    ]
    st.dataframe(
        pd.DataFrame(rows, columns=["Stat", stats_a["team_name"], stats_b["team_name"]]),
        use_container_width=True, hide_index=True
    )
    a_cf = float(stats_a["avg_corners_for"]);   a_ca = float(stats_a["avg_corners_against"])
    b_cf = float(stats_b["avg_corners_for"]);   b_ca = float(stats_b["avg_corners_against"])
    pred = round((a_cf + b_cf) / 2 + (a_ca + b_ca) / 2, 2)
    st.markdown(f"""
<div class="math-box">
<b>🔲 Corner Prediction Formula</b><br>
<span class="formula">Predicted Corners = (AvgFor_A + AvgFor_B) / 2 + (AvgAgainst_A + AvgAgainst_B) / 2</span><br><br>
= ({a_cf} + {b_cf}) / 2 + ({a_ca} + {b_ca}) / 2<br>
= {round((a_cf+b_cf)/2, 3)} + {round((a_ca+b_ca)/2, 3)}<br>
= <span class="result">~{pred} total corners predicted</span>
</div>
""", unsafe_allow_html=True)


def show_h2h(h2h_df, team_a_name, team_b_name):
    st.markdown('<div class="section-header">⚔️ Head-to-Head History</div>', unsafe_allow_html=True)
    if h2h_df.empty:
        st.info(f"No recent H2H matches found between {team_a_name} and {team_b_name}.")
        return
    st.dataframe(h2h_df, use_container_width=True, hide_index=True)
    avg = round(h2h_df["Total"].mean(), 2)
    mn  = int(h2h_df["Total"].min())
    mx  = int(h2h_df["Total"].max())
    st.markdown(f"""
<div class="math-box">
<b>H2H Goal Summary ({len(h2h_df)} games)</b><br>
Average goals per game: <span class="result">{avg}</span><br>
Min: {mn}  ·  Max: {mx}
</div>
""", unsafe_allow_html=True)


def show_ou_from_h2h(h2h_df, team_a_name, team_b_name):
    st.markdown('<div class="section-header">📊 Over / Under (H2H History)</div>', unsafe_allow_html=True)
    if h2h_df.empty:
        st.info("No H2H data — skipping O/U.")
        return
    df    = h2h_df.head(10)
    total = len(df)
    rows  = []
    for line in [1.5, 2.5, 3.5]:
        over  = int((df["Total"] > line).sum())
        under = int((df["Total"] < line).sum())
        rows.append({
            "Line": f"O/U {line}", "Over": over, "Under": under,
            "Over %": f"{round(over/total*100)}%", "Under %": f"{round(under/total*100)}%",
            "Avg Goals": round(df["Total"].mean(), 2), "Games Sampled": total,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    avg_goals = round(df["Total"].mean(), 2)
    st.markdown(f"""
<div class="math-box">
<b>O/U Math ({team_a_name} vs {team_b_name})</b><br>
<span class="formula">Over % = (games where Total > Line) / total games × 100</span><br><br>
Games sampled: {total}  ·  Avg goals: {avg_goals}<br>
Example (O/U 2.5): games over = {int((df["Total"] > 2.5).sum())} / {total}
= <span class="result">{round(int((df["Total"] > 2.5).sum()) / total * 100)}% Over 2.5</span>
</div>
""", unsafe_allow_html=True)


def show_poisson(stats_a, stats_b):
    st.markdown('<div class="section-header">📐 Poisson Over / Under Model</div>', unsafe_allow_html=True)
    a_scored   = float(stats_a["avg_scored"]);   a_conceded = float(stats_a["avg_conceded"])
    b_scored   = float(stats_b["avg_scored"]);   b_conceded = float(stats_b["avg_conceded"])
    team_a_xg  = round((a_scored + b_conceded) / 2, 3)
    team_b_xg  = round((b_scored + a_conceded) / 2, 3)
    blended    = round(team_a_xg + team_b_xg, 3)
    an = stats_a["team_name"];  bn = stats_b["team_name"]
    st.markdown(f"""
<div class="math-box">
<b>Expected Goals (xG) Derivation</b><br>
<span class="formula">xG_A = (AvgScored_A + AvgConceded_B) / 2</span><br>
<span class="formula">xG_B = (AvgScored_B + AvgConceded_A) / 2</span><br><br>
<b>{an}:</b> ({a_scored} + {b_conceded}) / 2 = <span class="result">{team_a_xg}</span><br>
<b>{bn}:</b> ({b_scored} + {a_conceded}) / 2 = <span class="result">{team_b_xg}</span><br>
<b>Blended Total xG:</b> {team_a_xg} + {team_b_xg} = <span class="result">{blended}</span>
</div>
""", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric(f"{an} xG", team_a_xg)
    c2.metric(f"{bn} xG", team_b_xg)
    c3.metric("Blended Total xG", blended)
    st.markdown(f"""
<div class="math-box">
<b>Poisson Formula</b><br>
<span class="formula">P(X = k) = (e^-μ × μ^k) / k!</span><br>
where μ = expected goals (xG), k = number of goals<br><br>
<b>Under probability:</b> sum P(X=0) + P(X=1) + ... + P(X=cutoff)<br>
<b>Over probability:</b> 1 - Under probability
</div>
""", unsafe_allow_html=True)
    rows = []
    for label, xg in [(f"{an} only", team_a_xg), (f"{bn} only", team_b_xg), ("Blended Total", blended)]:
        for entry in poisson_ou_probability(xg):
            rows.append({"Model": label, **entry, "xG Used": xg})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with st.expander("🔬 Show full Poisson probability breakdown (Blended xG)"):
        mu   = blended
        data = []
        cumulative = 0
        for k in range(11):
            p = (math.e ** -mu * mu ** k) / math.factorial(k)
            cumulative += p
            data.append({
                "Goals (k)": k, "Formula": f"(e^-{mu} × {mu}^{k}) / {k}!",
                "P(X=k)": f"{p:.4f}", "P(X=k) %": f"{round(p*100,2)}%",
                "Cumulative P(≤k)": f"{round(cumulative*100,2)}%",
            })
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)


def show_score_matrix(stats_a, stats_b):
    st.markdown('<div class="section-header">🎲 Score Probability Matrix</div>', unsafe_allow_html=True)
    an = stats_a["team_name"];  bn = stats_b["team_name"]
    xg_a = round((float(stats_a["avg_scored"]) + float(stats_b["avg_conceded"])) / 2, 3)
    xg_b = round((float(stats_b["avg_scored"]) + float(stats_a["avg_conceded"])) / 2, 3)
    max_g = 6
    grid  = np.zeros((max_g+1, max_g+1))
    for i in range(max_g+1):
        for j in range(max_g+1):
            grid[i][j] = (
                (math.e**-xg_a * xg_a**i / math.factorial(i)) *
                (math.e**-xg_b * xg_b**j / math.factorial(j))
            )
    home_win = float(np.sum(np.tril(grid, -1)))
    draw     = float(np.sum(np.diag(grid)))
    away_win = float(np.sum(np.triu(grid, 1)))
    st.markdown(f"""
<div class="math-box">
<b>Score Matrix Formula</b><br>
<span class="formula">P(Home={"{i}"}, Away={"{j}"}) = P_poisson(xG_A, i) × P_poisson(xG_B, j)</span><br><br>
Each cell = probability of that exact scoreline<br>
<b>Home Win</b>  = sum of all cells where Home goals > Away goals<br>
<b>Draw</b>      = sum of diagonal (equal goals)<br>
<b>Away Win</b>  = sum of all cells where Away goals > Home goals
</div>
""", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric(f"{an} Win", f"{home_win:.1%}")
    c2.metric("Draw",      f"{draw:.1%}")
    c3.metric(f"{bn} Win", f"{away_win:.1%}")
    labels  = [str(i) for i in range(max_g+1)]
    df_grid = pd.DataFrame(grid*100, index=labels, columns=labels).round(2)
    df_grid.index.name   = f"← {an} goals"
    df_grid.columns.name = f"{bn} goals →"
    st.markdown("**Score Probability Grid (%) — rows = home goals, cols = away goals**")
    st.dataframe(df_grid, use_container_width=True)
    flat = [(grid[i][j], i, j) for i in range(max_g+1) for j in range(max_g+1)]
    flat.sort(reverse=True)
    top5 = [{"Score": f"{an} {i}-{j} {bn}", "Probability": f"{round(p*100,2)}%"} for p, i, j in flat[:8]]
    st.markdown("**Top 8 Most Likely Scorelines**")
    st.dataframe(pd.DataFrame(top5), use_container_width=True, hide_index=True)


def show_btts(stats_a, stats_b):
    st.markdown('<div class="section-header">🔥 Both Teams to Score (BTTS)</div>', unsafe_allow_html=True)
    an = stats_a["team_name"];  bn = stats_b["team_name"]
    xg_a   = round((float(stats_a["avg_scored"]) + float(stats_b["avg_conceded"])) / 2, 3)
    xg_b   = round((float(stats_b["avg_scored"]) + float(stats_a["avg_conceded"])) / 2, 3)
    p_a    = 1 - math.exp(-xg_a)
    p_b    = 1 - math.exp(-xg_b)
    btts   = round(p_a * p_b * 100, 2)
    no_btts = round((1 - p_a * p_b) * 100, 2)
    st.markdown(f"""
<div class="math-box">
<b>BTTS Formula</b><br>
<span class="formula">P(score ≥ 1) = 1 - P(score 0) = 1 - e^-xG</span><br>
<span class="formula">P(BTTS) = P(A scores) × P(B scores)</span><br><br>
<b>{an}</b>  xG = {xg_a}  →  P(scores) = 1 - e^-{xg_a} = <span class="result">{round(p_a*100,2)}%</span><br>
<b>{bn}</b>  xG = {xg_b}  →  P(scores) = 1 - e^-{xg_b} = <span class="result">{round(p_b*100,2)}%</span><br><br>
P(BTTS) = {round(p_a*100,2)}% × {round(p_b*100,2)}% = <span class="result">{btts}%</span><br>
P(No BTTS) = <span class="result">{no_btts}%</span>
</div>
""", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"{an} xG", xg_a);  c2.metric(f"{bn} xG", xg_b)
    c3.metric("BTTS %", f"{btts}%");  c4.metric("No BTTS %", f"{no_btts}%")


def show_shotmap(team_id, team_name, team_key, force=False):
    st.markdown(f"**🗺️ Shotmap — {team_name}**")
    events = get_last_matches_for_team(int(team_id), force=force)
    if not events:
        st.info("No recent matches found.")
        return
    opts = {}
    for e in events[:10]:
        label = f"{e['date']}  {e['home_team']} {e['home_score']}-{e['away_score']} {e['away_team']}"
        opts[label] = e["match_id"]
    chosen   = st.selectbox("Select match:", list(opts.keys()), key=f"shot_{team_key}")
    match_id = opts[chosen]
    if st.button("Fetch Shotmap", key=f"shotbtn_{team_key}"):
        with st.spinner("Fetching..."):
            res  = requests.get(f"{BASE_URL}/matches/get-shotmap", headers=HEADERS, params={"matchId": match_id})
            data = res.json().get("shotmap", [])
        if not data:
            st.warning("No shotmap data for this match.")
            return
        df = pd.DataFrame(data)
        st.success(f"✅ {len(df)} shot events loaded")
        if "isGoal" in df.columns:
            goals  = int(df["isGoal"].sum())
            total  = len(df)
            on_tgt = int(df.get("onTarget", pd.Series([False]*total)).sum())
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Shots", total);  c2.metric("Goals", goals)
            c3.metric("On Target", on_tgt)
            c4.metric("Conversion %", f"{round(goals/total*100,1)}%" if total else "—")
            st.markdown(f"""
<div class="math-box">
<b>Shot Conversion Math</b><br>
Conversion rate = Goals / Total Shots × 100<br>
= {goals} / {total} × 100 = <span class="result">{round(goals/total*100,1) if total else 0}%</span><br>
On Target rate = {on_tgt} / {total} × 100 = <span class="result">{round(on_tgt/total*100,1) if total else 0}%</span>
</div>
""", unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True, hide_index=True)
        x_col = next((c for c in df.columns if c.lower() in ("x","xcoordinate","xpos")), None)
        y_col = next((c for c in df.columns if c.lower() in ("y","ycoordinate","ypos")), None)
        if x_col and y_col:
            st.scatter_chart(df[[x_col, y_col]].dropna(), x=x_col, y=y_col)


def show_heatmap(team_id, team_name, team_key, force=False):
    st.markdown(f"**🌡️ Heatmap — {team_name}**")
    events = get_last_matches_for_team(int(team_id), force=force)
    if not events:
        st.info("No recent matches found.")
        return
    opts = {}
    for e in events[:10]:
        label = f"{e['date']}  {e['home_team']} {e['home_score']}-{e['away_score']} {e['away_team']}"
        opts[label] = e["match_id"]
    chosen   = st.selectbox("Select match:", list(opts.keys()), key=f"heat_{team_key}")
    match_id = opts[chosen]
    if st.button("Fetch Heatmap", key=f"heatbtn_{team_key}"):
        with st.spinner("Fetching..."):
            res  = requests.get(f"{BASE_URL}/matches/get-team-heatmap", headers=HEADERS,
                                params={"matchId": match_id, "teamId": team_id})
            data = res.json().get("heatmap", [])
        if not data:
            st.warning("No heatmap data for this match.")
            return
        df = pd.DataFrame(data)
        st.success(f"✅ {len(df)} coordinate points")
        st.dataframe(df, use_container_width=True, hide_index=True)
        x_col = next((c for c in df.columns if "x" in c.lower()), None)
        y_col = next((c for c in df.columns if "y" in c.lower()), None)
        if x_col and y_col:
            st.scatter_chart(df[[x_col, y_col]].dropna(), x=x_col, y=y_col, size=2)


# ─────────────────────────────────────────────────────────────────────────────
# LAST 10 GAMES DISPLAY
# ─────────────────────────────────────────────────────────────────────────────

def _result_badge(team_name: str, home_team: str, away_team: str,
                  home_score, away_score) -> str:
    """Return W / D / L coloured HTML for a team given a match row."""
    try:
        hs = int(home_score)
        as_ = int(away_score)
    except (ValueError, TypeError):
        return '<span style="color:#607080">?</span>'

    is_home = team_name.strip().lower() == home_team.strip().lower()
    if hs == as_:
        label, color = "D", "#c0a030"
    elif (is_home and hs > as_) or (not is_home and as_ > hs):
        label, color = "W", "#30b060"
    else:
        label, color = "L", "#c03040"
    return f'<span style="color:{color};font-weight:700">{label}</span>'


def show_last_10_games(team_a_id, team_b_id, team_a_name, team_b_name, force=False):
    st.markdown('<div class="section-header">📅 Last 10 Games</div>', unsafe_allow_html=True)

    matches_a = get_last_matches_for_team(int(team_a_id), force=force)
    matches_b = get_last_matches_for_team(int(team_b_id), force=force)

    tab_a, tab_b = st.tabs([f"🏠 {team_a_name}", f"✈️ {team_b_name}"])

    for tab, team_name, matches in [
        (tab_a, team_a_name, matches_a),
        (tab_b, team_b_name, matches_b),
    ]:
        with tab:
            if not matches:
                st.info(f"No recent match data found for {team_name}.")
                continue

            rows = []
            for m in matches[:10]:
                hs  = m.get("home_score", "?")
                as_ = m.get("away_score", "?")
                badge = _result_badge(team_name, m["home_team"], m["away_team"], hs, as_)
                # Opponent
                if m["home_team"].strip().lower() == team_name.strip().lower():
                    venue    = "H"
                    opponent = m["away_team"]
                else:
                    venue    = "A"
                    opponent = m["home_team"]
                rows.append({
                    "Date":     m["date"],
                    "H/A":      venue,
                    "Opponent": opponent,
                    "Score":    f"{hs}–{as_}",
                    "Result":   badge,
                })

            if not rows:
                st.info("No finished matches available.")
                continue

            df = pd.DataFrame(rows)

            # Render with HTML for coloured Result column
            html_rows = ""
            for _, r in df.iterrows():
                venue_color = "#4090c0" if r["H/A"] == "H" else "#a06040"
                html_rows += (
                    f"<tr>"
                    f"<td style='padding:5px 10px;color:#8aa0b8'>{r['Date']}</td>"
                    f"<td style='padding:5px 10px;color:{venue_color};font-weight:700'>{r['H/A']}</td>"
                    f"<td style='padding:5px 10px;color:#c8d6e5'>{r['Opponent']}</td>"
                    f"<td style='padding:5px 10px;font-family:IBM Plex Mono,monospace;color:#d0eaff'>{r['Score']}</td>"
                    f"<td style='padding:5px 10px;text-align:center'>{r['Result']}</td>"
                    f"</tr>"
                )

            st.markdown(f"""
<table style="width:100%;border-collapse:collapse;font-family:IBM Plex Mono,monospace;font-size:0.82rem;
              background:#0b1422;border:1px solid #152030;border-radius:3px">
  <thead>
    <tr style="border-bottom:1px solid #1e3050">
      <th style="padding:6px 10px;color:#5a80a0;text-align:left">Date</th>
      <th style="padding:6px 10px;color:#5a80a0;text-align:left">H/A</th>
      <th style="padding:6px 10px;color:#5a80a0;text-align:left">Opponent</th>
      <th style="padding:6px 10px;color:#5a80a0;text-align:left">Score</th>
      <th style="padding:6px 10px;color:#5a80a0;text-align:center">Result</th>
    </tr>
  </thead>
  <tbody>{html_rows}</tbody>
</table>
""", unsafe_allow_html=True)

            # Quick form summary
            results = []
            for m in matches[:10]:
                hs  = m.get("home_score", "?")
                as_ = m.get("away_score", "?")
                try:
                    hs_i, as_i = int(hs), int(as_)
                    is_home = m["home_team"].strip().lower() == team_name.strip().lower()
                    if hs_i == as_i:
                        results.append("D")
                    elif (is_home and hs_i > as_i) or (not is_home and as_i > hs_i):
                        results.append("W")
                    else:
                        results.append("L")
                except (ValueError, TypeError):
                    pass

            if results:
                w = results.count("W"); d = results.count("D"); l = results.count("L")
                gf_list, ga_list = [], []
                for m in matches[:10]:
                    try:
                        hs_i = int(m.get("home_score", 0))
                        as_i = int(m.get("away_score", 0))
                        is_home = m["home_team"].strip().lower() == team_name.strip().lower()
                        gf_list.append(hs_i if is_home else as_i)
                        ga_list.append(as_i if is_home else hs_i)
                    except (ValueError, TypeError):
                        pass
                avg_gf = round(sum(gf_list) / len(gf_list), 2) if gf_list else "—"
                avg_ga = round(sum(ga_list) / len(ga_list), 2) if ga_list else "—"
                form_str = " ".join(
                    f'<span style="color:{"#30b060" if r=="W" else "#c0a030" if r=="D" else "#c03040"}'
                    f';font-weight:700">{r}</span>'
                    for r in results
                )
                st.markdown(f"""
<div class="math-box" style="margin-top:10px">
<b>Form (last {len(results)} games):</b> {form_str}<br>
W {w} · D {d} · L {l} &nbsp;|&nbsp; Avg scored: <span class="result">{avg_gf}</span> &nbsp;·&nbsp; Avg conceded: <span class="result">{avg_ga}</span>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# MASTER ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def smart_analyze(team_a_input, team_b_input, show_shotmap_flag, show_heatmap_flag, force_update=False):

    # ── 1. Search teams ───────────────────────────────────────────────────────
    with st.spinner(f"Searching for '{team_a_input}'..."):
        team_a_id, team_a_name = search_team(team_a_input, force=force_update)
    with st.spinner(f"Searching for '{team_b_input}'..."):
        team_b_id, team_b_name = search_team(team_b_input, force=force_update)

    if not team_a_id:
        st.error(f"❌ Team not found: **{team_a_input}**")
        r = requests.get(f"{BASE_URL}/teams/search", headers=HEADERS, params={"name": team_a_input})
        st.json(r.json())
        return
    if not team_b_id:
        st.error(f"❌ Team not found: **{team_b_input}**")
        r = requests.get(f"{BASE_URL}/teams/search", headers=HEADERS, params={"name": team_b_input})
        st.json(r.json())
        return

    st.success(f"✅ Found: **{team_a_name}** (ID {team_a_id})  ·  **{team_b_name}** (ID {team_b_id})")

    # ── 2. Detect league ──────────────────────────────────────────────────────
    with st.spinner("Detecting league..."):
        tournament_id, season_id, league_name = get_team_league(team_a_id, team_a_name, force=force_update)

    if not tournament_id:
        st.error("Could not detect league.")
        return
    st.caption(f"🏟️ League detected: **{league_name}**  (tournament={tournament_id}, season={season_id})")

    # ── 3. Standings ──────────────────────────────────────────────────────────
    with st.spinner("Loading standings..."):
        standings_df = get_league_standings(tournament_id, season_id, force=force_update)
    if not standings_df.empty:
        with st.expander(f"📋 {league_name} Standings"):
            st.dataframe(standings_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── 4. Team stats ─────────────────────────────────────────────────────────
    with st.spinner("Loading team stats..."):
        stats_a = get_team_stats(team_a_id, team_a_name, tournament_id, season_id, force_update)
        stats_b = get_team_stats(team_b_id, team_b_name, tournament_id, season_id, force_update)

    if not stats_a or not stats_b:
        st.error("Could not retrieve season stats for one or both teams.")
        return

    # ── 5. Analysis sections ──────────────────────────────────────────────────
    show_team_comparison(stats_a, stats_b)
    st.divider()

    # Explicitly fetch each team's own last matches before display (independent of H2H)
    with st.spinner("Loading recent match history..."):
        get_last_matches_for_team(int(team_a_id), force=force_update)
        get_last_matches_for_team(int(team_b_id), force=force_update)

    show_last_10_games(team_a_id, team_b_id, team_a_name, team_b_name, force=False)
    st.divider()

    with st.spinner("Loading H2H matches..."):
        h2h_df = get_h2h_matches(team_a_id, team_b_id, team_a_name, team_b_name, force=force_update)

    show_h2h(h2h_df, team_a_name, team_b_name)
    st.divider()
    show_ou_from_h2h(h2h_df, team_a_name, team_b_name)
    st.divider()
    show_poisson(stats_a, stats_b)
    st.divider()
    show_score_matrix(stats_a, stats_b)
    st.divider()
    show_btts(stats_a, stats_b)

    # ── 6. Optional spatial data ──────────────────────────────────────────────
    if show_shotmap_flag:
        st.divider()
        st.markdown('<div class="section-header">🗺️ Shotmap Explorer</div>', unsafe_allow_html=True)
        t1, t2 = st.tabs([team_a_name, team_b_name])
        with t1: show_shotmap(team_a_id, team_a_name, "a", force=force_update)
        with t2: show_shotmap(team_b_id, team_b_name, "b", force=force_update)

    if show_heatmap_flag:
        st.divider()
        st.markdown('<div class="section-header">🌡️ Heatmap Explorer</div>', unsafe_allow_html=True)
        t1, t2 = st.tabs([team_a_name, team_b_name])
        with t1: show_heatmap(team_a_id, team_a_name, "a", force=force_update)
        with t2: show_heatmap(team_b_id, team_b_name, "b", force=force_update)


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR + MAIN UI
# ─────────────────────────────────────────────────────────────────────────────

if "triggered" not in st.session_state:
    st.session_state.triggered = False

with st.sidebar:
    st.markdown("## ⚙️ Match Setup")
    team_a_input = st.text_input("🏠 Home Team", "Liverpool",
                                 help="Type exactly as it appears on SofaScore")
    team_b_input = st.text_input("✈️ Away Team", "Arsenal")
    st.divider()
    st.markdown("### 📦 Options")
    show_shotmap_flag = st.checkbox("Include Shotmap Explorer")
    show_heatmap_flag = st.checkbox("Include Heatmap Explorer")
    force_update      = st.checkbox("♻️ Force API Refresh (bypass cache)")
    st.divider()
    if st.button("🚀 Analyse Matchup", type="primary", use_container_width=True):
        st.session_state.triggered = True
        st.session_state.team_a    = team_a_input
        st.session_state.team_b    = team_b_input
        st.session_state.shotmap   = show_shotmap_flag
        st.session_state.heatmap   = show_heatmap_flag
        st.session_state.force     = force_update
    st.divider()
    show_cache_status()
    st.divider()
    st.markdown("""
<small style="color:#405060">
<b>What's shown:</b><br>
• Team stat comparison<br>
• H2H history<br>
• Over/Under (H2H & Poisson)<br>
• Score probability matrix<br>
• BTTS probability<br>
• Full working math for every model<br>
• Shotmap & Heatmap (optional)<br><br>
<b>Cache TTL:</b> Stats 3d · Search 30d<br>
League 7d · Standings 1d · H2H 1d
</small>
""", unsafe_allow_html=True)


if not st.session_state.triggered:
    st.title("⚽ Pro Sports Analytics")
    st.markdown("""
Type two team names in the sidebar and hit **Analyse Matchup**.

Every model shows its **full working math**: formulas, substituted values, and results.

All API results are **cached to CSV** — repeated lookups for the same teams cost zero API credits.
Green 💾 badges = served from cache. Orange 🌐 badges = live API call.
""")
else:
    st.title(f"⚽  {st.session_state.team_a}  vs  {st.session_state.team_b}")
    st.caption(f"Analysis run: {datetime.today().strftime('%d %b %Y %H:%M')}")
    smart_analyze(
        st.session_state.team_a,
        st.session_state.team_b,
        st.session_state.shotmap,
        st.session_state.heatmap,
        st.session_state.force,
    )
