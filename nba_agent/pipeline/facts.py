from __future__ import annotations

from collections import defaultdict

from nba_agent.models import ScoreGame


def build_fact_summary_text(recent_scores: list[ScoreGame]) -> str:
    if not recent_scores:
        return ""

    grouped: dict[str, list[ScoreGame]] = defaultdict(list)
    ordered_dates: list[str] = []
    for game in recent_scores:
        date_key = game.game_date.strftime("%Y-%m-%d")
        if date_key not in grouped:
            ordered_dates.append(date_key)
        grouped[date_key].append(game)

    latest_date = ordered_dates[0]
    latest_games = grouped[latest_date]
    total_games = len(recent_scores)
    total_dates = len(ordered_dates)
    winners = [_winner_text(game) for game in latest_games]
    biggest_margin_game = max(recent_scores, key=_margin)
    closest_game = min(recent_scores, key=_margin)
    series_updates = [
        _shorten(game.series_text, max_len=40)
        for game in latest_games
        if game.series_text.strip()
    ]

    lines = [
        f"- 官方比分源最近 {total_dates} 个比赛日共记录 {total_games} 场已完赛比赛。",
        f"- 最新比赛日 {latest_date} 共 {len(latest_games)} 场，胜者包括："
        + "、".join(winners[:3])
        + (" 等。" if len(winners) > 3 else "。"),
        f"- 最大分差比赛：{_winner_text(biggest_margin_game)}，分差 {_margin(biggest_margin_game)} 分。",
        f"- 最胶着比赛：{closest_game.away_team} {closest_game.away_score} : "
        f"{closest_game.home_score} {closest_game.home_team}，分差 {_margin(closest_game)} 分。",
    ]

    if series_updates:
        unique_updates: list[str] = []
        for update in series_updates:
            if update not in unique_updates:
                unique_updates.append(update)
        lines.append("- 系列赛进度：" + "；".join(unique_updates[:3]) + "。")

    lines.append("- 数据来源：NBA 官方赛程与比分接口。")
    return "\n".join(lines)


def _shorten(text: str, max_len: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1] + "…"


def _winner_text(game: ScoreGame) -> str:
    if game.away_score > game.home_score:
        return f"{game.away_team} 胜 {game.home_team}"
    if game.home_score > game.away_score:
        return f"{game.home_team} 胜 {game.away_team}"
    return f"{game.away_team} 战 {game.home_team}"


def _margin(game: ScoreGame) -> int:
    return abs(game.away_score - game.home_score)
