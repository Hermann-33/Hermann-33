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
        d = sorted_days[0][0]
        end_scan = sorted_days[-1][0]
        while d <= end_scan:
            if day_counts.get(d, 0) > 0:
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


def make_svg(total_contributions, streaks):
    total_text = f"{total_contributions:,}"
    total_range = f"Since {fmt_date(streaks['first_contribution'])}"

    if streaks["current_streak"] > 0:
        current_num = str(streaks["current_streak"])
        current_range = fmt_short_range(streaks["current_start"], streaks["current_end"])
    else:
        current_num = "0"
        current_range = "No active streak"

    if streaks["longest_streak"] > 0:
        longest_num = str(streaks["longest_streak"])
        longest_range = fmt_short_range(streaks["longest_start"], streaks["longest_end"])
    else:
        longest_num = "0"
        longest_range = "No streak yet"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="700" height="190" viewBox="0 0 700 190" role="img" aria-label="GitHub contribution and streak stats">
  <defs>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#e21b2d"/>
      <stop offset="72%" stop-color="#e21b2d"/>
      <stop offset="100%" stop-color="#ffd21e"/>
    </linearGradient>
  </defs>

  <rect x="0.75" y="0.75" width="698.5" height="188.5" rx="10" fill="#071426" stroke="#20324b" stroke-width="1.5"/>
  <rect x="22" y="16" width="656" height="2" rx="1" fill="url(#accent)"/>

  <line x1="233" y1="38" x2="233" y2="154" stroke="#223753" stroke-width="1"/>
  <line x1="467" y1="38" x2="467" y2="154" stroke="#223753" stroke-width="1"/>

  <g font-family="Segoe UI, Ubuntu, Helvetica Neue, Arial, sans-serif">
    <text x="116.5" y="78" text-anchor="middle" fill="#f7f9fc" font-size="38" font-weight="700">{total_text}</text>
    <text x="116.5" y="108" text-anchor="middle" fill="#d9e1ec" font-size="15" font-weight="600">Total Contributions</text>
    <text x="116.5" y="133" text-anchor="middle" fill="#8496ae" font-size="11">{escape(total_range)}</text>

    <circle cx="350" cy="72" r="35" fill="none" stroke="#1e3552" stroke-width="6"/>
    <circle cx="350" cy="72" r="35" fill="none" stroke="#e21b2d" stroke-width="6" stroke-linecap="round"/>
    <circle cx="378" cy="51" r="3.5" fill="#ffd21e"/>
    <text x="350" y="83" text-anchor="middle" fill="#ffffff" font-size="32" font-weight="700">{current_num}</text>
    <text x="350" y="128" text-anchor="middle" fill="#ffd21e" font-size="15" font-weight="600">Current Streak</text>
    <text x="350" y="151" text-anchor="middle" fill="#8496ae" font-size="11">{escape(current_range)}</text>

    <text x="583.5" y="78" text-anchor="middle" fill="#f7f9fc" font-size="38" font-weight="700">{longest_num}</text>
    <text x="583.5" y="108" text-anchor="middle" fill="#d9e1ec" font-size="15" font-weight="600">Longest Streak</text>
    <text x="583.5" y="133" text-anchor="middle" fill="#8496ae" font-size="11">{escape(longest_range)}</text>
  </g>
</svg>
"""


def main():
    user = fetch_user()
    created_at = datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00")).date()
    today = datetime.now(timezone.utc).date()

    total_contributions, day_counts = fetch_all_contributions(created_at, today)
    streaks = compute_streaks(day_counts, today)
    svg = make_svg(total_contributions, streaks)

    out_path = Path("assets/redbull-all-repo-stats.svg")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Total contributions: {total_contributions}")
    print(f"Current streak: {streaks['current_streak']}")
    print(f"Longest streak: {streaks['longest_streak']}")


if __name__ == "__main__":
    main()
