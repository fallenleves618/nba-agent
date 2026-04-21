from __future__ import annotations

from collections import Counter, defaultdict

from nba_agent.models import CollectedItem, ReportSettings, ScoreGame


CATEGORY_PRIORITY = ["team", "player", "topic", "generic"]
CATEGORY_LABELS = {
    "team": "球队",
    "player": "球员",
    "topic": "主题",
    "generic": "其他",
}


def _shorten(text: str, max_len: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1] + "…"


def _primary_category(item: CollectedItem) -> str:
    if not item.matched_categories:
        return "generic"

    for category in CATEGORY_PRIORITY:
        if category in item.matched_categories:
            return category
    return item.matched_categories[0]


def _ranked_items(items: list[CollectedItem]) -> list[CollectedItem]:
    return sorted(
        items,
        key=lambda item: (item.score, item.publish_time is not None, item.publish_time),
        reverse=True,
    )


def _limit_items_by_source(
    items: list[CollectedItem], per_source_top_n: int | None
) -> list[CollectedItem]:
    if per_source_top_n is None:
        return items

    kept: list[CollectedItem] = []
    source_counter: Counter[str] = Counter()
    for item in items:
        if source_counter[item.source] >= per_source_top_n:
            continue
        kept.append(item)
        source_counter[item.source] += 1
    return kept


def _append_item_lines(
    lines: list[str], items: list[CollectedItem], *, include_category_line: bool
) -> None:
    for idx, item in enumerate(items, start=1):
        matched = ", ".join(item.matched_keywords) if item.matched_keywords else "无"
        lines.append(f"{idx}. [{item.source}] {item.title}")
        if include_category_line and item.matched_categories:
            lines.append(f"   命中分类: {', '.join(item.matched_categories)}")
        lines.append(f"   命中关键词: {matched}")
        if item.agent_score is not None:
            lines.append(f"   Agent评分: {item.agent_score}")
        if item.agent_reason:
            lines.append(f"   Agent理由: {_shorten(item.agent_reason, max_len=160)}")
        if item.content_excerpt:
            lines.append(f"   摘要: {_shorten(item.content_excerpt)}")
        lines.append(f"   链接: {item.url}")
        lines.append("")


def _append_recent_scores(lines: list[str], recent_scores: list[ScoreGame]) -> None:
    if not recent_scores:
        return

    grouped: dict[str, list[ScoreGame]] = defaultdict(list)
    ordered_dates: list[str] = []
    for game in recent_scores:
        date_key = game.game_date.strftime("%Y-%m-%d")
        if date_key not in grouped:
            ordered_dates.append(date_key)
        grouped[date_key].append(game)

    lines.append("最近两天比赛比分")
    lines.append("")
    for date_key in ordered_dates:
        lines.append(date_key)
        for game in grouped[date_key]:
            line = (
                f"- {game.away_team} {game.away_score} : {game.home_score} "
                f"{game.home_team}"
            )
            if game.game_status_text:
                line += f" ({game.game_status_text})"
            lines.append(line)
            if game.series_text:
                lines.append(f"  系列赛: {game.series_text}")
        lines.append("")


def _append_hot_news_summary(lines: list[str], hot_news_summary: str) -> None:
    summary = hot_news_summary.strip()
    if not summary:
        return

    lines.append("今日高热度新闻总结")
    lines.append("")
    for line in summary.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lines.append(stripped)
    lines.append("")


def _append_summary_inputs(lines: list[str], summary_inputs: list[CollectedItem]) -> None:
    if not summary_inputs:
        return

    lines.append("总结输入 Top")
    lines.append("")
    for idx, item in enumerate(summary_inputs, start=1):
        score_text = (
            str(item.agent_score) if item.agent_score is not None else str(item.score)
        )
        matched = ", ".join(item.matched_keywords[:3]) if item.matched_keywords else "无"
        lines.append(
            f"{idx}. [{item.source}] {item.title} (score={score_text}, 关键词={matched})"
        )
    lines.append("")


def _append_stage_timings(lines: list[str], stage_timings: dict[str, float]) -> None:
    if not stage_timings:
        return

    lines.append("运行耗时")
    lines.append("")
    for stage_name, elapsed in stage_timings.items():
        lines.append(f"- {stage_name}: {elapsed:.1f}s")
    lines.append("")


def _append_diagnostics(lines: list[str], diagnostics: list[str]) -> None:
    if not diagnostics:
        return

    lines.append("运行诊断")
    lines.append("")
    for item in diagnostics:
        text = item.strip()
        if not text:
            continue
        lines.append(f"- {text}")
    lines.append("")


def build_daily_report(
    items: list[CollectedItem],
    settings: ReportSettings | None = None,
    recent_scores: list[ScoreGame] | None = None,
    hot_news_summary: str = "",
    summary_inputs: list[CollectedItem] | None = None,
    stage_timings: dict[str, float] | None = None,
    diagnostics: list[str] | None = None,
) -> str:
    if not items:
        lines = ["今日 NBA 日报", ""]
        _append_recent_scores(lines, recent_scores or [])
        _append_hot_news_summary(lines, hot_news_summary)
        _append_summary_inputs(lines, summary_inputs or [])
        _append_stage_timings(lines, stage_timings or {})
        lines.append("今日没有命中关键词的 NBA 内容。")
        lines.append("")
        _append_diagnostics(lines, diagnostics or [])
        return "\n".join(lines).rstrip()
    report_settings = settings or ReportSettings()

    source_counter = Counter(item.source for item in items)
    lines = ["今日 NBA 日报", ""]
    _append_recent_scores(lines, recent_scores or [])
    _append_hot_news_summary(lines, hot_news_summary)
    _append_summary_inputs(lines, summary_inputs or [])
    _append_stage_timings(lines, stage_timings or {})
    lines.append(
        "来源概览: "
        + ", ".join(
            f"{source} {count} 条" for source, count in sorted(source_counter.items())
        )
    )
    if report_settings.per_source_top_n is not None:
        lines.append(
            f"来源限流: 每个区段每个来源最多保留 {report_settings.per_source_top_n} 条"
        )
    lines.append("")

    ranked = _ranked_items(items)
    overview_items = _limit_items_by_source(ranked, report_settings.per_source_top_n)
    lines.append("总览")
    lines.append("")
    _append_item_lines(
        lines,
        overview_items[: report_settings.overview_top_n],
        include_category_line=True,
    )

    grouped: dict[str, list[CollectedItem]] = defaultdict(list)
    for item in ranked:
        grouped[_primary_category(item)].append(item)

    for category in CATEGORY_PRIORITY:
        section_items = grouped.get(category)
        if not section_items:
            continue
        limited_section_items = _limit_items_by_source(
            section_items, report_settings.per_source_top_n
        )
        lines.append(f"{CATEGORY_LABELS.get(category, category)}")
        lines.append("")
        _append_item_lines(
            lines,
            limited_section_items[: report_settings.category_top_n],
            include_category_line=False,
        )

    _append_diagnostics(lines, diagnostics or [])
    return "\n".join(lines).rstrip()
