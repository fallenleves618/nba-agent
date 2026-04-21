from __future__ import annotations

import argparse
import time

from nba_agent.collectors import (
    DemoCollector,
    HupuCollector,
    OfficialInfoCollector,
    TiebaCollector,
)
from nba_agent.config import (
    load_agent_filter_settings,
    load_delivery_settings,
    load_hupu_settings,
    load_keyword_rules,
    load_report_settings,
    load_settings,
    load_tieba_settings,
)
from nba_agent.delivery.console import deliver_to_console
from nba_agent.delivery.webhook import deliver_to_webhooks
from nba_agent.models import (
    CollectedItem,
    DailyRunResult,
    DeliverySettings,
    HupuSettings,
    KeywordRules,
    ReportSettings,
    ScoreGame,
    TiebaSettings,
)
from nba_agent.pipeline.dedupe import dedupe_items
from nba_agent.pipeline.agent_filter import (
    filter_items_with_agent,
    generate_hot_news_summary,
    select_summary_candidates,
)
from nba_agent.pipeline.keywords import apply_keyword_rules
from nba_agent.pipeline.report import build_daily_report
from nba_agent.storage.sqlite_store import SQLiteStore


def _collect_items(
    demo: bool,
    rules: KeywordRules,
    *,
    hupu_settings: HupuSettings,
    tieba_settings: TiebaSettings,
    hupu_only: bool = False,
) -> tuple[list[CollectedItem], dict[str, float]]:
    if demo:
        collectors = [DemoCollector()]
    elif hupu_only:
        collectors = [HupuCollector(hupu_settings)]
    else:
        collectors = [HupuCollector(hupu_settings)]
        if tieba_settings.enabled:
            collectors.append(TiebaCollector(tieba_settings))

    items: list[CollectedItem] = []
    stage_timings: dict[str, float] = {}
    for collector in collectors:
        started_at = time.time()
        print(f"[progress] collecting {collector.name} ...", flush=True)
        try:
            collected_items = collector.collect(rules)
            items.extend(collected_items)
            elapsed = time.time() - started_at
            stage_timings[f"collect_{collector.name}"] = elapsed
            print(
                f"[progress] collected {collector.name}: {len(collected_items)} items "
                f"in {elapsed:.1f}s",
                flush=True,
            )
        except Exception as exc:
            print(f"collector failed: {collector.name}: {exc}")
            stage_timings[f"collect_{collector.name}"] = time.time() - started_at
    return items, stage_timings


def run_pipeline(demo: bool = False, *, hupu_only: bool = False) -> DailyRunResult:
    pipeline_started_at = time.time()
    settings = load_settings()
    rules = load_keyword_rules(settings.keywords_path)
    hupu_settings = load_hupu_settings(settings.hupu_path)
    tieba_settings = load_tieba_settings(settings.tieba_path)
    agent_filter_settings = load_agent_filter_settings(settings.agent_filter_path)
    delivery_settings = load_delivery_settings(settings.delivery_path)
    report_settings = load_report_settings(settings.report_path)
    store = SQLiteStore(settings.db_path)
    store.init_db()
    recent_scores: list[ScoreGame] = []
    diagnostics = _build_runtime_diagnostics(agent_filter_settings)
    stage_timings: dict[str, float] = {}

    if not demo and not hupu_only:
        print("[progress] fetching recent scores ...", flush=True)
        started_at = time.time()
        recent_scores = OfficialInfoCollector().collect_recent_scores(days=2)
        stage_timings["recent_scores"] = time.time() - started_at
        print(
            f"[progress] fetched recent scores: {len(recent_scores)} games "
            f"in {stage_timings['recent_scores']:.1f}s",
            flush=True,
        )

    collected, collect_timings = _collect_items(
        demo=demo,
        rules=rules,
        hupu_settings=hupu_settings,
        tieba_settings=tieba_settings,
        hupu_only=hupu_only,
    )
    stage_timings.update(collect_timings)
    print(f"[progress] keyword filtering {len(collected)} items ...", flush=True)
    started_at = time.time()
    filtered = apply_keyword_rules(collected, rules)
    stage_timings["keyword_filter"] = time.time() - started_at
    print(f"[progress] keyword kept {len(filtered)} items", flush=True)
    started_at = time.time()
    deduped = dedupe_items(filtered)
    stage_timings["dedupe"] = time.time() - started_at
    print(f"[progress] deduped to {len(deduped)} items", flush=True)
    print("[progress] model filtering ...", flush=True)
    started_at = time.time()
    agent_filtered = filter_items_with_agent(deduped, agent_filter_settings)
    stage_timings["model_filter"] = time.time() - started_at
    print(
        f"[progress] model kept {len(agent_filtered)} items "
        f"in {stage_timings['model_filter']:.1f}s",
        flush=True,
    )
    summary_inputs = select_summary_candidates(agent_filtered, agent_filter_settings)
    print("[progress] generating hot-news summary ...", flush=True)
    started_at = time.time()
    hot_news_summary = generate_hot_news_summary(agent_filtered, agent_filter_settings)
    stage_timings["hot_news_summary"] = time.time() - started_at
    print(
        f"[progress] summary length {len(hot_news_summary)} "
        f"in {stage_timings['hot_news_summary']:.1f}s",
        flush=True,
    )
    started_at = time.time()
    stored_count = store.save_items(agent_filtered)
    stage_timings["store"] = time.time() - started_at
    print(f"[progress] stored {stored_count} items", flush=True)
    stage_timings["total"] = time.time() - pipeline_started_at
    report = build_daily_report(
        agent_filtered,
        report_settings,
        recent_scores=recent_scores,
        hot_news_summary=hot_news_summary,
        summary_inputs=summary_inputs,
        stage_timings=stage_timings,
        diagnostics=diagnostics if not agent_filtered else [],
    )
    _deliver_report(report, delivery_settings)

    return DailyRunResult(
        collected_count=len(collected),
        kept_count=len(filtered),
        deduped_count=len(deduped),
        agent_kept_count=len(agent_filtered),
        stored_count=stored_count,
        report=report,
        diagnostics=diagnostics,
        stage_timings=stage_timings,
    )


def _build_runtime_diagnostics(
    settings,
) -> list[str]:
    diagnostics: list[str] = []
    model_text = (
        f"模型筛选开关={settings.enabled}, 热点总结开关={settings.summary_enabled}, "
        f"model={settings.model or '未配置'}, api_mode={settings.api_mode}, "
        f"base_url={settings.api_base_url or '未配置'}"
    )
    diagnostics.append(model_text)
    if not settings.api_base_url or not settings.api_key or not settings.model:
        diagnostics.append(
            "模型环境变量未完整加载。先执行 `source ~/.zshrc`，再运行命令。"
        )
    diagnostics.append(
        "如果要在任意目录运行，先执行 `pip3 install -e /Users/yizhou.wu/nba-agent`，之后可直接用 `nba-agent`。"
    )
    diagnostics.append(
        "如果持续 collected=0，优先检查当前网络是否能访问虎扑、贴吧和 NBA 官方源。"
    )
    return diagnostics


def _deliver_report(report: str, settings: DeliverySettings) -> None:
    if settings.console_enabled:
        deliver_to_console(report)
    deliver_to_webhooks(report, settings)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NBA daily info agent scaffold")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run pipeline with demo collector data",
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize SQLite schema and exit",
    )
    parser.add_argument(
        "--hupu-only",
        action="store_true",
        help="Run only the Hupu collector",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    store = SQLiteStore(settings.db_path)

    if args.init_db:
        store.init_db()
        print(f"initialized db at {settings.db_path}")
        return

    result = run_pipeline(demo=args.demo, hupu_only=args.hupu_only)
    print("")
    print(
        "summary: "
        f"collected={result.collected_count}, "
        f"kept={result.kept_count}, "
        f"deduped={result.deduped_count}, "
        f"agent_kept={result.agent_kept_count}, "
        f"stored={result.stored_count}"
    )


if __name__ == "__main__":
    main()
