import requests
import pandas as pd
import math
import os
from datetime import datetime

# --- SECTION 1: GLOBAL SETUP ---
RAPIDAPI_KEY = "e937b8311emsh0e6fea678cf971ep1239d5jsn59ef35110fcd"
HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "sofascore.p.rapidapi.com",
    "Content-Type": "application/json"
}
BASE_URL = "https://sofascore.p.rapidapi.com"
CACHE_FILE = "team_stats_cache.csv"


# --- SECTION 2: CACHE SYSTEM ---

def load_cache():
    """Load existing cache or return empty DataFrame."""
    if os.path.exists(CACHE_FILE):
        df = pd.read_csv(CACHE_FILE)
        print(f"  📦 Cache loaded: {len(df)} teams")
        return df
    return pd.DataFrame()


def save_cache(df):
    """Save cache to CSV."""
    df.to_csv(CACHE_FILE, index=False)
    print(f"  💾 Cache saved: {len(df)} teams")


def get_cached_team(cache_df, team_id, tournament_id, season_id):
    """Check if team stats exist in cache for this season."""
    if cache_df.empty:
        return None
    match = cache_df[
        (cache_df["team_id"] == int(team_id)) &
        (cache_df["tournament_id"] == int(tournament_id)) &
        (cache_df["season_id"] == int(season_id))
    ]
    if not match.empty:
        cached_date = match.iloc[0]["cached_date"]
        print(f"  ✅ Cache hit for team {team_id} — last updated {cached_date}")
        return match.iloc[0]
    return None


def update_cache(cache_df, stats_row):
    """Add or update a team's stats in the cache."""
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


# --- SECTION 3: API FUNCTIONS ---

def search_team(team_name):
    """Find team ID and name by search."""
    r = requests.get(f"{BASE_URL}/teams/search", headers=HEADERS, params={"name": team_name})
    data = r.json()
    teams = data.get("teams", [])
    if not teams:
        print(f"  Team not found: {team_name}")
        return None, None
    team = teams[0]
    print(f"  Found: {team['name']} (ID: {team['id']})")
    return team["id"], team["name"]


def get_team_league(team_id, team_name):
    """Auto-detect league from team's last match."""
    r = requests.get(f"{BASE_URL}/teams/get-last-matches",
                     headers=HEADERS, params={"teamId": team_id})
    data = r.json()
    events = data.get("events", [])
    for e in events:
        ut = e.get("tournament", {}).get("uniqueTournament", {})
        season = e.get("season", {})
        if ut.get("id") and season.get("id"):
            league_name = ut.get("name", "Unknown")
            print(f"  League: {league_name} (tournament={ut['id']}, season={season['id']})")
            return str(ut["id"]), str(season["id"]), league_name
    print(f"  Could not detect league for {team_name}")
    return None, None, None


def get_league_standings(tournament_id, season_id, league_name):
    """Pull and display league standings."""
    r = requests.get(f"{BASE_URL}/tournaments/get-standings",
                     headers=HEADERS,
                     params={"tournamentId": tournament_id, "seasonId": season_id})
    data = r.json()
    standings = data.get("standings", [])
    if not standings:
        print(f"  No standings for {league_name}")
        return
    rows = standings[0].get("rows", [])
    table = []
    for row in rows:
        table.append({
            "Rank": row.get("position"),
            "Team": row.get("team", {}).get("name"),
            "W": row.get("wins"),
            "D": row.get("draws"),
            "L": row.get("losses"),
            "GF": row.get("scoresFor"),
            "GA": row.get("scoresAgainst"),
            "Pts": row.get("points")
        })
    df = pd.DataFrame(table)
    print(f"\n--- STANDINGS: {league_name} ---")
    print(df.to_string(index=False))
    df.to_csv(f"standings_{league_name.replace(' ', '_')}.csv", index=False)


def fetch_team_stats_from_api(team_id, team_name, tournament_id, season_id):
    """Fetch full stats from API and return as a dict."""
    r = requests.get(f"{BASE_URL}/teams/get-statistics",
                     headers=HEADERS,
                     params={"teamId": team_id,
                             "tournamentId": tournament_id,
                             "seasonId": season_id})
    data = r.json().get("statistics", {})
    if not data:
        print(f"  No stats for {team_name}")
        return None

    matches = data.get("matches", 1) or 1

    stats = {
        "team_id": int(team_id),
        "team_name": team_name,
        "tournament_id": int(tournament_id),
        "season_id": int(season_id),
        "matches": matches,
        "cached_date": datetime.today().strftime("%Y-%m-%d"),

        # Goals
        "goals_scored": data.get("goalsScored", 0),
        "goals_conceded": data.get("goalsConceded", 0),
        "avg_scored": round(data.get("goalsScored", 0) / matches, 3),
        "avg_conceded": round(data.get("goalsConceded", 0) / matches, 3),

        # Corners
        "corners_for": data.get("corners", 0),
        "corners_against": data.get("cornersAgainst", 0),
        "avg_corners_for": round(data.get("corners", 0) / matches, 3),
        "avg_corners_against": round(data.get("cornersAgainst", 0) / matches, 3),
        "avg_total_corners": round(
            (data.get("corners", 0) + data.get("cornersAgainst", 0)) / matches, 3),

        # Shots
        "shots": data.get("shots", 0),
        "shots_on_target": data.get("shotsOnTarget", 0),
        "shots_against": data.get("shotsAgainst", 0),
        "shots_on_target_against": data.get("shotsOnTargetAgainst", 0),

        # Possession
        "avg_possession": data.get("averageBallPossession", 0),

        # Cards
        "yellow_cards": data.get("yellowCards", 0),
        "red_cards": data.get("redCards", 0),

        # Clean sheets
        "clean_sheets": data.get("cleanSheets", 0),
    }

    print(f"  🌐 Fetched from API: {team_name} ({matches} matches)")
    return stats


def get_team_stats(cache_df, team_id, team_name, tournament_id, season_id, force_update=False):
    """Get stats from cache if available, otherwise fetch from API."""
    if not force_update:
        cached = get_cached_team(cache_df, team_id, tournament_id, season_id)
        if cached is not None:
            return cached.to_dict(), cache_df

    # Fetch fresh from API
    stats = fetch_team_stats_from_api(team_id, team_name, tournament_id, season_id)
    if stats is None:
        return None, cache_df

    cache_df = update_cache(cache_df, stats)
    save_cache(cache_df)
    return stats, cache_df


def get_h2h_matches(team_a_id, team_b_id, team_a_name, team_b_name, last_n=10):
    """Get H2H by cross-referencing both teams' last matches."""
    r = requests.get(f"{BASE_URL}/teams/get-last-matches",
                     headers=HEADERS, params={"teamId": team_a_id})
    events_a = {e["id"]: e for e in r.json().get("events", [])
                if e.get("status", {}).get("type") == "finished"}

    r = requests.get(f"{BASE_URL}/teams/get-last-matches",
                     headers=HEADERS, params={"teamId": team_b_id})
    events_b = {e["id"]: e for e in r.json().get("events", [])
                if e.get("status", {}).get("type") == "finished"}

    common_ids = set(events_a.keys()) & set(events_b.keys())
    matches = []
    for match_id in common_ids:
        e = events_a[match_id]
        home = e.get("homeScore", {}).get("display")
        away = e.get("awayScore", {}).get("display")
        if home is None or away is None:
            continue
        matches.append({
            "Date": pd.Timestamp(e["startTimestamp"], unit="s").strftime("%Y-%m-%d"),
            "Home": e["homeTeam"]["name"],
            "Away": e["awayTeam"]["name"],
            "Score": f"{home}-{away}",
            "Total": int(home) + int(away)
        })

    df = pd.DataFrame(matches)
    if df.empty:
        print(f"  No recent H2H found for {team_a_name} vs {team_b_name}")
        return df
    df = df.sort_values("Date", ascending=False).head(last_n)
    print(f"\n--- H2H: {team_a_name} vs {team_b_name} (last {len(df)} games) ---")
    print(df.to_string(index=False))
    df.to_csv(f"h2h_{team_a_id}_{team_b_id}.csv", index=False)
    return df


def predict_over_under(team_a_name, team_b_name, team_a_id, team_b_id, h2h_df):
    """O/U probabilities from H2H history."""
    if h2h_df.empty:
        print("  Skipping O/U — no H2H data.")
        return
    df = h2h_df.head(10)
    total_games = len(df)
    lines = [1.5, 2.5, 3.5]
    results = []
    for line in lines:
        over = (df["Total"] > line).sum()
        under = (df["Total"] < line).sum()
        results.append({
            "Line": f"O/U {line}",
            "Over": over,
            "Under": under,
            "Over %": f"{round((over / total_games) * 100)}%",
            "Under %": f"{round((under / total_games) * 100)}%",
            "Avg Goals": round(df["Total"].mean(), 2),
            "Games Sampled": total_games
        })
    result_df = pd.DataFrame(results)
    print(f"\n--- OVER/UNDER PREDICTION: {team_a_name} vs {team_b_name} ---")
    print(result_df.to_string(index=False))
    result_df.to_csv(f"ou_{team_a_id}_{team_b_id}.csv", index=False)
    print(f"Saved ou_{team_a_id}_{team_b_id}.csv")


def poisson_ou_probability(expected_goals, lines=[1.5, 2.5, 3.5], max_goals=10):
    """P(x; mu) = (e^-mu * mu^x) / x!"""
    results = []
    for line in lines:
        probs = [(math.e ** -expected_goals * expected_goals ** x) / math.factorial(x)
                 for x in range(max_goals + 1)]
        cutoff = int(line)
        under_prob = sum(probs[:cutoff + 1])
        over_prob = sum(probs[cutoff + 1:])
        results.append({
            "Line": f"O/U {line}",
            "Over %": f"{round(over_prob * 100)}%",
            "Under %": f"{round(under_prob * 100)}%",
        })
    return results


def display_team_comparison(stats_a, stats_b):
    """Display side-by-side goals and corners comparison."""
    rows = [
        ("Matches Played",    stats_a["matches"],           stats_b["matches"]),
        ("Goals Scored",      stats_a["goals_scored"],      stats_b["goals_scored"]),
        ("Goals Conceded",    stats_a["goals_conceded"],     stats_b["goals_conceded"]),
        ("Avg Scored/Game",   stats_a["avg_scored"],         stats_b["avg_scored"]),
        ("Avg Conceded/Game", stats_a["avg_conceded"],       stats_b["avg_conceded"]),
        ("Clean Sheets",      stats_a["clean_sheets"],       stats_b["clean_sheets"]),
        ("Corners For",       stats_a["corners_for"],        stats_b["corners_for"]),
        ("Corners Against",   stats_a["corners_against"],    stats_b["corners_against"]),
        ("Avg Corners For",   stats_a["avg_corners_for"],    stats_b["avg_corners_for"]),
        ("Avg Corners Agnst", stats_a["avg_corners_against"],stats_b["avg_corners_against"]),
        ("Avg Total Corners", stats_a["avg_total_corners"],  stats_b["avg_total_corners"]),
        ("Shots",             stats_a["shots"],              stats_b["shots"]),
        ("Shots on Target",   stats_a["shots_on_target"],    stats_b["shots_on_target"]),
        ("Avg Possession %",  stats_a["avg_possession"],     stats_b["avg_possession"]),
        ("Yellow Cards",      stats_a["yellow_cards"],       stats_b["yellow_cards"]),
        ("Red Cards",         stats_a["red_cards"],          stats_b["red_cards"]),
    ]
    df = pd.DataFrame(rows, columns=["Stat", stats_a["team_name"], stats_b["team_name"]])
    print(f"\n--- TEAM COMPARISON ---")
    print(df.to_string(index=False))
    df.to_csv(f"comparison_{stats_a['team_id']}_{stats_b['team_id']}.csv", index=False)
    print(f"Saved comparison_{stats_a['team_id']}_{stats_b['team_id']}.csv")

    # Corner O/U prediction
    avg_corners_match = round(
        (stats_a["avg_corners_for"] + stats_b["avg_corners_for"]) / 2 +
        (stats_a["avg_corners_against"] + stats_b["avg_corners_against"]) / 2, 2
    )
    print(f"\n  🔲 Predicted Total Corners This Match: ~{avg_corners_match}")
    print(f"  (Based on avg corners for + against per game for both teams)")


def predict_over_under_poisson(stats_a, stats_b, team_a_id, team_b_id):
    """Poisson O/U model using cached season stats."""
    team_a_name = stats_a["team_name"]
    team_b_name = stats_b["team_name"]
    print(f"\n📐 Poisson O/U Model: {team_a_name} vs {team_b_name}")

    a_scored = float(stats_a["avg_scored"])
    a_conceded = float(stats_a["avg_conceded"])
    b_scored = float(stats_b["avg_scored"])
    b_conceded = float(stats_b["avg_conceded"])

    team_a_xg = round((a_scored + b_conceded) / 2, 3)
    team_b_xg = round((b_scored + a_conceded) / 2, 3)
    blended_total = round(team_a_xg + team_b_xg, 3)

    print(f"\n  Expected Goals → {team_a_name}: {team_a_xg} | {team_b_name}: {team_b_xg}")
    print(f"  Blended Total xG: {blended_total}")

    rows = []
    for label, xg in [(f"{team_a_name} only", team_a_xg),
                      (f"{team_b_name} only", team_b_xg),
                      ("Blended Total", blended_total)]:
        for entry in poisson_ou_probability(xg):
            rows.append({"Model": label, **entry, "xG Used": xg})
    df = pd.DataFrame(rows)
    print(f"\n--- POISSON O/U PREDICTIONS: {team_a_name} vs {team_b_name} ---")
    print(df.to_string(index=False))
    df.to_csv(f"poisson_ou_{team_a_id}_{team_b_id}.csv", index=False)
    print(f"Saved poisson_ou_{team_a_id}_{team_b_id}.csv")


# --- SECTION 4: THE SMART EXECUTION ---

def smart_analyze(team_a_name_input, team_b_name_input, force_update=False):
    """Master function — search, cache, analyze."""
    print(f"\n🔍 Investigating Matchup: {team_a_name_input} vs {team_b_name_input}...")

    cache_df = load_cache()

    team_a_id, team_a_name = search_team(team_a_name_input)
    team_b_id, team_b_name = search_team(team_b_name_input)
    if not team_a_id or not team_b_id:
        print("  Could not find one or both teams. Skipping.")
        return

    tournament_id, season_id, league_name = get_team_league(team_a_id, team_a_name)
    if not tournament_id:
        print("  Could not detect league. Skipping.")
        return

    get_league_standings(tournament_id, season_id, league_name)

    stats_a, cache_df = get_team_stats(
        cache_df, team_a_id, team_a_name, tournament_id, season_id, force_update)
    stats_b, cache_df = get_team_stats(
        cache_df, team_b_id, team_b_name, tournament_id, season_id, force_update)

    if not stats_a or not stats_b:
        print("  Could not get stats for one or both teams.")
        return

    display_team_comparison(stats_a, stats_b)
    h2h_df = get_h2h_matches(team_a_id, team_b_id, team_a_name, team_b_name)
    predict_over_under(team_a_name, team_b_name, team_a_id, team_b_id, h2h_df)
    predict_over_under_poisson(stats_a, stats_b, team_a_id, team_b_id)


if __name__ == "__main__":
    picks = [
        ("Bayern Munich", "Borussia Dortmund"),
        ("PSG", "Marseille"),
        ("Real Madrid", "Barcelona"),
    ]

    # Set force_update=True to refresh all cached stats from API
    for team_a, team_b in picks:
        smart_analyze(team_a, team_b, force_update=False)
