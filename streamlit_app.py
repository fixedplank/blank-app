import streamlit as st
import requests
import pandas as pd
import math
import os
import numpy as np
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SETUP  — identical to original
# ─────────────────────────────────────────────────────────────────────────────

RAPIDAPI_KEY = ""
HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "sofascore.p.rapidapi.com",
    "Content-Type": "application/json"
}
BASE_URL   = "https://sofascore.p.rapidapi.com"
CACHE_FILE = "team_stats_cache.csv"

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

.section-header { font-family: 'Barlow Condensed', sans-serif; font-size: 1.6rem;
                  font-weight: 700; color: #d8eeff; border-bottom: 1px solid #152030;
                  padding-bottom: 4px; margin-top: 1.5rem; }

hr { border-color: #101a28; margin: 1.8rem 0; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# CACHE SYSTEM  — original unchanged
# ─────────────────────────────────────────────────────────────────────────────

def load_cache():
    if os.path.exists(CACHE_FILE):
        return pd.read_csv(CACHE_FILE)
    return pd.DataFrame()

def save_cache(df):
    df.to_csv(CACHE_FILE, index=False)

def get_cached_team(cache_df, team_id, tournament_id, season_id):
    if cache_df.empty:
        return None
    m = cache_df[
        (cache_df["team_id"] == int(team_id)) &
        (cache_df["tournament_id"] == int(tournament_id)) &
        (cache_df["season_id"] == int(season_id))
    ]
    return m.iloc[0] if not m.empty else None

def update_cache(cache_df, stats_row):
    mask = (
        (cache_df["team_id"] == stats_row["team_id"]) &
        (cache_df["tournament_id"] == stats_row["tournament_id"]) &
        (cache_df["season_id"] == stats_row["season_id"])
    ) if not cache_df.empty else pd.Series([], dtype=bool)
    if not cache_df.empty and mask.any():
        cache_df.loc[mask, list(stats_row.keys())] = list(stats_row.values())
    else:
        cache_df = pd.concat([cache_df, pd.DataFrame([stats_row])], ignore_index=True)
    return cache_df


# ─────────────────────────────────────────────────────────────────────────────
# API FUNCTIONS  — original unchanged (search_team is IDENTICAL to original)
# ─────────────────────────────────────────────────────────────────────────────

def search_team(team_name):
    """Find team ID and name by search. — original logic, zero changes."""
    r    = requests.get(f"{BASE_URL}/teams/search", headers=HEADERS, params={"name": team_name})
    data = r.json()
    teams = data.get("teams", [])
    if not teams:
        return None, None
    team = teams[0]
    return team["id"], team["name"]


def get_team_league(team_id, team_name):
    """Auto-detect league from team's last match. — original logic."""
    r      = requests.get(f"{BASE_URL}/teams/get-last-matches", headers=HEADERS, params={"teamId": team_id})
    events = r.json().get("events", [])
    for e in events:
        ut     = e.get("tournament", {}).get("uniqueTournament", {})
        season = e.get("season", {})
        if ut.get("id") and season.get("id"):
            return str(ut["id"]), str(season["id"]), ut.get("name", "Unknown")
    return None, None, None


def get_league_standings(tournament_id, season_id):
    r    = requests.get(f"{BASE_URL}/tournaments/get-standings", headers=HEADERS,
                        params={"tournamentId": tournament_id, "seasonId": season_id})
    rows = r.json().get("standings", [{}])[0].get("rows", [])
    if not rows:
        return pd.DataFrame()
    table = []
    for row in rows:
        table.append({
            "Rank": row.get("position"), "Team": row.get("team", {}).get("name"),
            "W": row.get("wins"), "D": row.get("draws"), "L": row.get("losses"),
            "GF": row.get("scoresFor"), "GA": row.get("scoresAgainst"), "Pts": row.get("points")
        })
    return pd.DataFrame(table)


def fetch_team_stats_from_api(team_id, team_name, tournament_id, season_id):
    """Fetch full stats — original logic."""
    r    = requests.get(f"{BASE_URL}/teams/get-statistics", headers=HEADERS,
                        params={"teamId": team_id, "tournamentId": tournament_id, "seasonId": season_id})
    data = r.json().get("statistics", {})
    if not data:
        return None
    matches = data.get("matches", 1) or 1
    return {
        "team_id": int(team_id), "team_name": team_name,
        "tournament_id": int(tournament_id), "season_id": int(season_id),
        "matches": matches, "cached_date": datetime.today().strftime("%Y-%m-%d"),
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


def get_team_stats(cache_df, team_id, team_name, tournament_id, season_id, force_update=False):
    if not force_update:
        cached = get_cached_team(cache_df, team_id, tournament_id, season_id)
        if cached is not None:
            return cached.to_dict(), cache_df
    stats = fetch_team_stats_from_api(team_id, team_name, tournament_id, season_id)
    if stats is None:
        return None, cache_df
    cache_df = update_cache(cache_df, stats)
    save_cache(cache_df)
    return stats, cache_df


def get_h2h_matches(team_a_id, team_b_id, team_a_name, team_b_name, last_n=5-10):
    """Original H2H logic."""
    r        = requests.get(f"{BASE_URL}/teams/get-last-matches", headers=HEADERS, params={"teamId": team_a_id})
    events_a = {e["id"]: e for e in r.json().get("events", []) if e.get("status", {}).get("type") == "finished"}

    r        = requests.get(f"{BASE_URL}/teams/get-last-matches", headers=HEADERS, params={"teamId": team_b_id})
    events_b = {e["id"]: e for e in r.json().get("events", []) if e.get("status", {}).get("type") == "finished"}

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
    return df.sort_values("Date", ascending=False).head(last_n)


def poisson_ou_probability(expected_goals, lines=[0.5,1.5, 2.5, 3.5,4,5], max_goals=10):
    """Original Poisson formula."""
    results = []
    for line in lines:
        probs      = [(math.e ** -expected_goals * expected_goals ** x) / math.factorial(x)
                      for x in range(max_goals + 1)]
        cutoff     = int(line)
        under_prob = sum(probs[:cutoff + 1])
        over_prob  = sum(probs[cutoff + 1:])
        results.append({
            "Line": f"O/U {line}",
            "Over %":  f"{round(over_prob  * 100)}%",
            "Under %": f"{round(under_prob * 100)}%",
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY FUNCTIONS WITH FULL MATH
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

    # Corner prediction math
    a_cf  = float(stats_a["avg_corners_for"])
    a_ca  = float(stats_a["avg_corners_against"])
    b_cf  = float(stats_b["avg_corners_for"])
    b_ca  = float(stats_b["avg_corners_against"])
    pred  = round((a_cf + b_cf) / 2 + (a_ca + b_ca) / 2, 2)

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
            "Line":         f"O/U {line}",
            "Over":         over,
            "Under":        under,
            "Over %":       f"{round(over  / total * 100)}%",
            "Under %":      f"{round(under / total * 100)}%",
            "Avg Goals":    round(df["Total"].mean(), 2),
            "Games Sampled": total,
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

    a_scored   = float(stats_a["avg_scored"])
    a_conceded = float(stats_a["avg_conceded"])
    b_scored   = float(stats_b["avg_scored"])
    b_conceded = float(stats_b["avg_conceded"])
    team_a_xg  = round((a_scored   + b_conceded) / 2, 3)
    team_b_xg  = round((b_scored   + a_conceded) / 2, 3)
    blended    = round(team_a_xg   + team_b_xg,  3)

    an = stats_a["team_name"]
    bn = stats_b["team_name"]

    # xG derivation math box
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

    # Poisson formula explanation
    st.markdown(f"""
<div class="math-box">
<b>Poisson Formula</b><br>
<span class="formula">P(X = k) = (e^-μ × μ^k) / k!</span><br>
where μ = expected goals (xG), k = number of goals<br><br>
<b>Under probability:</b> sum P(X=0) + P(X=1) + ... + P(X=cutoff)<br>
<b>Over probability:</b> 1 - Under probability
</div>
""", unsafe_allow_html=True)

    # Build full table with math detail
    rows = []
    for label, xg in [(f"{an} only", team_a_xg), (f"{bn} only", team_b_xg), ("Blended Total", blended)]:
        for entry in poisson_ou_probability(xg):
            rows.append({"Model": label, **entry, "xG Used": xg})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Show worked example for blended
    with st.expander("🔬 Show full Poisson probability breakdown (Blended xG)"):
        mu   = blended
        data = []
        cumulative = 0
        for k in range(11):
            p = (math.e ** -mu * mu ** k) / math.factorial(k)
            cumulative += p
            data.append({
                "Goals (k)": k,
                "Formula":   f"(e^-{mu} × {mu}^{k}) / {k}! ",
                "P(X=k)":    f"{p:.4f}",
                "P(X=k) %":  f"{round(p*100,2)}%",
                "Cumulative P(≤k)": f"{round(cumulative*100,2)}%",
            })
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)


def show_score_matrix(stats_a, stats_b):
    st.markdown('<div class="section-header">🎲 Score Probability Matrix</div>', unsafe_allow_html=True)

    an = stats_a["team_name"]
    bn = stats_b["team_name"]

    a_scored   = float(stats_a["avg_scored"])
    a_conceded = float(stats_a["avg_conceded"])
    b_scored   = float(stats_b["avg_scored"])
    b_conceded = float(stats_b["avg_conceded"])
    xg_a = round((a_scored + b_conceded) / 2, 3)
    xg_b = round((b_scored + a_conceded) / 2, 3)

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

    # Most likely scores
    flat = [(grid[i][j], i, j) for i in range(max_g+1) for j in range(max_g+1)]
    flat.sort(reverse=True)
    top5 = [{"Score": f"{an} {i}-{j} {bn}", "Probability": f"{round(p*100,2)}%"}
            for p, i, j in flat[:8]]
    st.markdown("**Top 8 Most Likely Scorelines**")
    st.dataframe(pd.DataFrame(top5), use_container_width=True, hide_index=True)


def show_btts(stats_a, stats_b):
    st.markdown('<div class="section-header">🔥 Both Teams to Score (BTTS)</div>', unsafe_allow_html=True)

    an = stats_a["team_name"]
    bn = stats_b["team_name"]

    xg_a   = round((float(stats_a["avg_scored"]) + float(stats_b["avg_conceded"])) / 2, 3)
    xg_b   = round((float(stats_b["avg_scored"]) + float(stats_a["avg_conceded"])) / 2, 3)
    p_a    = 1 - math.exp(-xg_a)   # P(team A scores at least 1)
    p_b    = 1 - math.exp(-xg_b)   # P(team B scores at least 1)
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
    c1.metric(f"{an} xG", xg_a)
    c2.metric(f"{bn} xG", xg_b)
    c3.metric("BTTS %",   f"{btts}%")
    c4.metric("No BTTS %", f"{no_btts}%")


def show_shotmap(team_id, team_name, team_key):
    st.markdown(f"**🗺️ Shotmap — {team_name}**")

    r      = requests.get(f"{BASE_URL}/teams/get-last-matches", headers=HEADERS, params={"teamId": team_id})
    events = [e for e in r.json().get("events", []) if e.get("status", {}).get("type") == "finished"][:10]
    if not events:
        st.info("No recent matches found.")
        return

    opts = {}
    for e in events:
        h    = e.get("homeScore", {}).get("display", "?")
        a    = e.get("awayScore", {}).get("display", "?")
        date = pd.Timestamp(e["startTimestamp"], unit="s").strftime("%Y-%m-%d")
        label = f"{date}  {e['homeTeam']['name']} {h}-{a} {e['awayTeam']['name']}"
        opts[label] = e["id"]

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
            c1.metric("Total Shots", total)
            c2.metric("Goals", goals)
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


def show_heatmap(team_id, team_name, team_key):
    st.markdown(f"**🌡️ Heatmap — {team_name}**")

    r      = requests.get(f"{BASE_URL}/teams/get-last-matches", headers=HEADERS, params={"teamId": team_id})
    events = [e for e in r.json().get("events", []) if e.get("status", {}).get("type") == "finished"][:10]
    if not events:
        st.info("No recent matches found.")
        return

    opts = {}
    for e in events:
        h    = e.get("homeScore", {}).get("display", "?")
        a    = e.get("awayScore", {}).get("display", "?")
        date = pd.Timestamp(e["startTimestamp"], unit="s").strftime("%Y-%m-%d")
        label = f"{date}  {e['homeTeam']['name']} {h}-{a} {e['awayTeam']['name']}"
        opts[label] = e["id"]

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
# MASTER ANALYSIS  — mirrors original smart_analyze() flow
# ─────────────────────────────────────────────────────────────────────────────

def smart_analyze(team_a_input, team_b_input, show_shotmap_flag, show_heatmap_flag, force_update=False):

    cache_df = load_cache()

    # ── 1. Search teams (original function, zero changes) ────────────────────
    with st.spinner(f"Searching for '{team_a_input}'..."):
        team_a_id, team_a_name = search_team(team_a_input)
    with st.spinner(f"Searching for '{team_b_input}'..."):
        team_b_id, team_b_name = search_team(team_b_input)

    if not team_a_id:
        st.error(f"❌ Team not found: **{team_a_input}**\n\nRaw API response:")
        r = requests.get(f"{BASE_URL}/teams/search", headers=HEADERS, params={"name": team_a_input})
        st.json(r.json())
        return
    if not team_b_id:
        st.error(f"❌ Team not found: **{team_b_input}**\n\nRaw API response:")
        r = requests.get(f"{BASE_URL}/teams/search", headers=HEADERS, params={"name": team_b_input})
        st.json(r.json())
        return

    st.success(f"✅ Found: **{team_a_name}** (ID {team_a_id})  ·  **{team_b_name}** (ID {team_b_id})")

    # ── 2. Detect league ─────────────────────────────────────────────────────
    with st.spinner("Detecting league..."):
        tournament_id, season_id, league_name = get_team_league(team_a_id, team_a_name)

    if not tournament_id:
        st.error("Could not detect league. The team may have no recent matches on SofaScore.")
        return

    st.caption(f"🏟️ League detected: **{league_name}**  (tournament={tournament_id}, season={season_id})")

    # ── 3. Standings ─────────────────────────────────────────────────────────
    with st.spinner("Loading standings..."):
        standings_df = get_league_standings(tournament_id, season_id)

    if not standings_df.empty:
        with st.expander(f"📋 {league_name} Standings"):
            st.dataframe(standings_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── 4. Team stats ─────────────────────────────────────────────────────────
    with st.spinner("Loading team stats..."):
        stats_a, cache_df = get_team_stats(cache_df, team_a_id, team_a_name,
                                           tournament_id, season_id, force_update)
        stats_b, cache_df = get_team_stats(cache_df, team_b_id, team_b_name,
                                           tournament_id, season_id, force_update)

    if not stats_a or not stats_b:
        st.error("Could not retrieve season stats for one or both teams.")
        return

    # ── 5. All analysis sections ──────────────────────────────────────────────
    show_team_comparison(stats_a, stats_b)
    st.divider()

    with st.spinner("Loading H2H matches..."):
        h2h_df = get_h2h_matches(team_a_id, team_b_id, team_a_name, team_b_name)

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
        with t1: show_shotmap(team_a_id, team_a_name, "a")
        with t2: show_shotmap(team_b_id, team_b_name, "b")

    if show_heatmap_flag:
        st.divider()
        st.markdown('<div class="section-header">🌡️ Heatmap Explorer</div>', unsafe_allow_html=True)
        t1, t2 = st.tabs([team_a_name, team_b_name])
        with t1: show_heatmap(team_a_id, team_a_name, "a")
        with t2: show_heatmap(team_b_id, team_b_name, "b")


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
    st.markdown("""
<small style="color:#405060">
<b>What's shown:</b><br>
• Team stat comparison<br>
• H2H history<br>
• Over/Under (H2H & Poisson)<br>
• Score probability matrix<br>
• BTTS probability<br>
• Full working math for every model<br>
• Shotmap & Heatmap (optional)
</small>
""", unsafe_allow_html=True)


if not st.session_state.triggered:
    st.title("⚽ Pro Sports Analytics")
    st.markdown("""
Type two team names in the sidebar and hit **Analyse Matchup**.

The app uses the **exact same search logic** as the original working script —
type the team name as you would on SofaScore (e.g. `Liverpool`, `Real Madrid`, `PSG`).

Every model shows its **full working math**: formulas, substituted values, and results.
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
