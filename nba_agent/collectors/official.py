from __future__ import annotations

import json
from datetime import datetime

from nba_agent.collectors.base import BaseCollector
from nba_agent.http import fetch_text
from nba_agent.models import CollectedItem, KeywordRules, ScoreGame


NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"


class OfficialInfoCollector(BaseCollector):
    name = "official"

    def collect(self, rules: KeywordRules) -> list[CollectedItem]:
        return []

    def collect_recent_scores(self, days: int = 2) -> list[ScoreGame]:
        raw_text = fetch_text(
            NBA_SCHEDULE_URL,
            headers={"Accept": "application/json, text/plain, */*"},
        )
        if not raw_text:
            return []

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return []

        game_dates = payload.get("leagueSchedule", {}).get("gameDates", [])
        recent_games: list[ScoreGame] = []
        selected_days = 0

        for date_entry in reversed(game_dates):
            parsed_games = self._parse_scored_games(date_entry)
            if not parsed_games:
                continue
            recent_games.extend(parsed_games)
            selected_days += 1
            if selected_days >= max(1, days):
                break

        return recent_games

    def _parse_scored_games(self, date_entry: dict[str, object]) -> list[ScoreGame]:
        game_date_text = str(date_entry.get("gameDate", ""))
        if not game_date_text:
            return []

        try:
            game_date = datetime.strptime(game_date_text, "%m/%d/%Y %H:%M:%S")
        except ValueError:
            return []

        games: list[ScoreGame] = []
        for game in date_entry.get("games", []):
            if not isinstance(game, dict):
                continue

            game_status = int(game.get("gameStatus", 0) or 0)
            away_team = game.get("awayTeam", {})
            home_team = game.get("homeTeam", {})
            if not isinstance(away_team, dict) or not isinstance(home_team, dict):
                continue

            away_score = int(away_team.get("score", 0) or 0)
            home_score = int(home_team.get("score", 0) or 0)
            if game_status < 2 and away_score == 0 and home_score == 0:
                continue

            games.append(
                ScoreGame(
                    game_id=str(game.get("gameId", "")),
                    game_date=game_date,
                    game_status=game_status,
                    game_status_text=str(game.get("gameStatusText", "")),
                    away_team=str(away_team.get("teamTricode", "")),
                    away_score=away_score,
                    home_team=str(home_team.get("teamTricode", "")),
                    home_score=home_score,
                    series_text=str(game.get("seriesText", "")),
                )
            )

        return games
