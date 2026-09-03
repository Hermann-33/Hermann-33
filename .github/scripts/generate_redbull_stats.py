import json
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

API_URL = "https://api.github.com/graphql"

TOKEN = os.environ["GH_TOKEN"]
USERNAME = os.environ["USERNAME"]

HEADERS = {
    "Authorization": f"bearer {TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "github-stats-card-generator",
}


def graphql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(API_URL, data=payload, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def iso_start(d: date) -> str:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def iso_end(d: date) -> str:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def fmt_date(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def fmt_short_range(start: date, end: date) -> str:
    if start == end:
        return f"{start.strftime('%b')} {start.day}, {start.year}"
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.strftime('%b')} {start.day} - {end.day}, {start.year}"
        return f"{start.strftime('%b')} {start.day} - {end.strftime('%b')} {end.day}, {start.year}"
    return f"{fmt_date(start)} - {fmt_date(end)}"


USER_QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    name
    createdAt
  }
}
"""

CAL_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch_user():
    data = graphql(USER_QUERY, {"login": USERNAME})
    return data["user"]


def fetch_all_contributions(created_at: date, today: date):
    total = 0
    day_counts = {}

    for year in range(created_at.year, today.year + 1):
        start = max(created_at, date(year, 1, 1))
        end = min(today, date(year, 12, 31))
        if start > end:
            continue

        data = graphql(
            CAL_QUERY,
            {
                "login": USERNAME,
                "from": iso_start(start),
                "to": iso_end(end),
            },
        )

        cal = data["user"]["contributionsCollection"]["contributionCalendar"]
        total += cal["totalContributions"]

        for week in cal["weeks"]:
            for item in week["contributionDays"]:
                d = date.fromisoformat(item["date"])
                if start <= d <= end:
                    day_counts[d] = item["contributionCount"]

    return total, day_counts


def compute_streaks(day_counts: dict, today: date):
    sorted_days = sorted(day_counts.items())

    nonzero_days = [d for d, c in sorted_days if c > 0]
    first_contribution = nonzero_days[0] if nonzero_days else today

    current_streak = 0
    current_start = None
    current_end = None

    if day_counts.get(today, 0) > 0:
        d = today
        while day_counts.get(d, 0) > 0:
            current_streak += 1
            current_start = d
            current_end = today
            d -= timedelta(days=1)

    longest_streak = 0
    longest_start = None
    longest_end = None

    run_len = 0
    run_start = None
    run_end = None

    if sorted_days:
        start_scan = sorted_days[0][0]
        end_scan = sorted_days[-1][0]
        d = start_scan
        while d <= end_scan:
            count = day_counts.get(d, 0)
            if count > 0:
                if run_len == 0:
                    run_start = d
                run_end = d
                run_len += 1
            else:
                if run_len > longest_streak:
                    longest_streak = run_len
                    longest_start = run_start
                    longest_end = run_end
                run_len = 0
                run_start = None
                run_end = None
            d += timedelta(days=1)

        if run_len > longest_streak:
            longest_streak = run_len
            longest_start = run_start
            longest_end = run_end

    return {
        "first_contribution": first_contribution,
        "current_streak": current_streak,
        "current_start": current_start,
        "current_end": current_end,
        "longest_streak": longest_streak,
        "longest_start": longest_start,
        "longest_end": longest_end,
    }


def make_svg(display_name, total_contributions, streaks):
    total_text = f"{total_contributions:,}"
    total_range = f"{fmt_date(streaks['first_contribution'])} - Present"

    if streaks["current_streak"] > 0:
        current_num = str(streaks["current_streak"])
        current_range = fmt_short_range(streaks["current_start"], streaks["current_end"])
    else:
        current_num = "0"
        current_range = "No streak today"

    if streaks["longest_streak"] > 0:
        longest_num = str(streaks["longest_streak"])
        longest_range = fmt_short_range(streaks["longest_start"], streaks["longest_end"])
    else:
        longest_num = "0"
        longest_range = "No streak yet"

    title = escape(f"{display_name} • All-Repo GitHub Stats")
    subtitle = escape("Public + private contributions included")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="980" height="320" viewBox="0 0 980 320" role="img" aria-label="All-repo GitHub stats">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#06162f"/>
      <stop offset="58%" stop-color="#0a2454"/>
      <stop offset="100%" stop-color="#07101f"/>
    </linearGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#e21b2d"/>
      <stop offset="48%" stop-color="#ff233b"/>
      <stop offset="100%" stop-color="#ffd21e"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#143d8d"/>
      <stop offset="50%" stop-color="#e21b2d"/>
      <stop offset="100%" stop-color="#ffd21e"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#000000" flood-opacity="0.38"/>
    </filter>
  </defs>

  <rect width="980" height="320" rx="24" fill="url(#bg)"/>
  <rect x="18" y="18" width="944" height="284" rx="20" fill="#08152b" stroke="#173b78" stroke-width="2" filter="url(#shadow)"/>
  <rect x="40" y="88" width="900" height="3" rx="1.5" fill="url(#accent)" opacity="0.95"/>

  <text x="40" y="52" fill="#f7f9ff" font-size="28" font-family="Segoe UI, Arial, sans-serif" font-weight="700">{title}</text>
  <text x="40" y="78" fill="#aebbd3" font-size="15" font-family="Segoe UI, Arial, sans-serif">{subtitle}</text>

  <line x1="326" y1="111" x2="326" y2="258" stroke="#274878" stroke-width="2"/>
  <line x1="653" y1="111" x2="653" y2="258" stroke="#274878" stroke-width="2"/>

  <text x="163" y="162" text-anchor="middle" fill="#ffffff" font-size="58" font-family="Segoe UI, Arial, sans-serif" font-weight="800">{total_text}</text>
  <text x="163" y="198" text-anchor="middle" fill="#e7ecf7" font-size="25" font-family="Segoe UI, Arial, sans-serif" font-weight="600">Total Contributions</text>
  <text x="163" y="230" text-anchor="middle" fill="#9fb0cd" font-size="18" font-family="Segoe UI, Arial, sans-serif">{escape(total_range)}</text>

  <circle cx="490" cy="150" r="54" fill="none" stroke="#17335f" stroke-width="10"/>
  <circle cx="490" cy="150" r="54" fill="none" stroke="url(#ring)" stroke-width="10" stroke-linecap="round"/>
  <text x="490" y="161" text-anchor="middle" fill="#ffffff" font-size="50" font-family="Segoe UI, Arial, sans-serif" font-weight="800">{current_num}</text>
  <text x="490" y="222" text-anchor="middle" fill="#ffd21e" font-size="25" font-family="Segoe UI, Arial, sans-serif" font-weight="700">Current Streak</text>
  <text x="490" y="254" text-anchor="middle" fill="#9fb0cd" font-size="18" font-family="Segoe UI, Arial, sans-serif">{escape(current_range)}</text>

  <text x="816" y="162" text-anchor="middle" fill="#ffffff" font-size="58" font-family="Segoe UI, Arial, sans-serif" font-weight="800">{longest_num}</text>
  <text x="816" y="198" text-anchor="middle" fill="#e7ecf7" font-size="25" font-family="Segoe UI, Arial, sans-serif" font-weight="600">Longest Streak</text>
  <text x="816" y="230" text-anchor="middle" fill="#9fb0cd" font-size="18" font-family="Segoe UI, Arial, sans-serif">{escape(longest_range)}</text>

  <text x="490" y="287" text-anchor="middle" fill="#7187aa" font-size="15" font-family="Segoe UI, Arial, sans-serif">Private repository names remain hidden • generated from GitHub GraphQL</text>
</svg>
"""


def main():
    user = fetch_user()
    created_at = datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00")).date()
    today = datetime.now(timezone.utc).date()

    total_contributions, day_counts = fetch_all_contributions(created_at, today)
    streaks = compute_streaks(day_counts, today)

    display_name = user["name"] or user["login"]
    svg = make_svg(display_name, total_contributions, streaks)

    out_path = Path("assets/redbull-all-repo-stats.svg")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Total contributions: {total_contributions}")
    print(f"Current streak: {streaks['current_streak']}")
    print(f"Longest streak: {streaks['longest_streak']}")


if __name__ == "__main__":
    main()
