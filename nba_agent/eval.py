from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from nba_agent.models import AgentFilterSettings, AgentPromptSettings, CollectedItem
from nba_agent.pipeline.agent_filter import filter_items_with_agent, generate_hot_news_summary


def run_local_eval(
    dataset_path: Path,
    *,
    filter_settings: AgentFilterSettings,
    prompt_settings: AgentPromptSettings,
) -> str:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    filter_report = _evaluate_filter_cases(
        dataset.get("filter_cases", []),
        filter_settings=filter_settings,
        prompt_settings=prompt_settings,
    )
    summary_report = _evaluate_summary_cases(
        dataset.get("summary_cases", []),
        filter_settings=filter_settings,
        prompt_settings=prompt_settings,
    )

    lines = [
        "NBA Agent Eval",
        "",
        f"筛选Prompt: {prompt_settings.filter_version}",
        f"总结Prompt: {prompt_settings.summary_version}",
        "",
        "筛选评估",
        "",
        f"- 样本数: {filter_report['total']}",
        f"- 命中数: {filter_report['correct']}",
        f"- 准确率: {filter_report['accuracy']:.1%}",
        "",
    ]

    if filter_report["mismatch_buckets"]:
        lines.append("筛选误判分类")
        lines.append("")
        for bucket in filter_report["mismatch_buckets"]:
            lines.append(f"- {bucket['label']}: {bucket['count']}")
        lines.append("")

    if filter_report["mismatches"]:
        lines.append("筛选误差样本")
        lines.append("")
        for mismatch in filter_report["mismatches"]:
            lines.append(
                f"- [{mismatch['bucket_label']}] {mismatch['id']}: expected={mismatch['expected']} "
                f"actual={mismatch['actual']} title={mismatch['title']}"
            )
            if mismatch["reason"]:
                lines.append(f"  reason: {mismatch['reason']}")
        lines.append("")

    lines.extend(
        [
            "总结评估",
            "",
            f"- 样本数: {summary_report['total']}",
            f"- 主题覆盖率: {summary_report['coverage']:.1%}",
            "",
        ]
    )

    if summary_report["details"]:
        lines.append("总结样本详情")
        lines.append("")
        for detail in summary_report["details"]:
            lines.append(
                f"- {detail['id']}: topics={detail['covered']}/{detail['expected']} covered"
            )
            lines.append(f"  summary: {detail['summary']}")
        lines.append("")

    return "\n".join(lines).rstrip()


def run_prompt_comparison_eval(
    dataset_path: Path,
    *,
    filter_settings: AgentFilterSettings,
    prompts_dir: Path,
    filter_versions: list[str],
    summary_versions: list[str],
) -> str:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    lines = ["NBA Agent Prompt Compare", ""]

    if filter_versions:
        lines.extend(["筛选 Prompt 对比", ""])
        filter_rows = []
        for version in filter_versions:
            prompt_settings = _build_prompt_settings(
                prompts_dir=prompts_dir,
                filter_version=version,
                summary_version="summary_v1",
            )
            report = _evaluate_filter_cases(
                dataset.get("filter_cases", []),
                filter_settings=filter_settings,
                prompt_settings=prompt_settings,
            )
            filter_rows.append((version, report))

        filter_rows.sort(key=lambda row: row[1]["accuracy"], reverse=True)
        for version, report in filter_rows:
            top_bucket = _top_mismatch_bucket_summary(report["mismatch_buckets"])
            lines.append(
                f"- {version}: accuracy={report['accuracy']:.1%} "
                f"correct={report['correct']}/{report['total']} "
                f"mismatches={len(report['mismatches'])} "
                f"top_error={top_bucket}"
            )
        lines.append("")

    if summary_versions:
        lines.extend(["总结 Prompt 对比", ""])
        summary_rows = []
        for version in summary_versions:
            prompt_settings = _build_prompt_settings(
                prompts_dir=prompts_dir,
                filter_version="filter_v1",
                summary_version=version,
            )
            report = _evaluate_summary_cases(
                dataset.get("summary_cases", []),
                filter_settings=filter_settings,
                prompt_settings=prompt_settings,
            )
            summary_rows.append((version, report))

        summary_rows.sort(key=lambda row: row[1]["coverage"], reverse=True)
        for version, report in summary_rows:
            lines.append(
                f"- {version}: coverage={report['coverage']:.1%} "
                f"cases={report['total']}"
            )
        lines.append("")

    return "\n".join(lines).rstrip()


def _evaluate_filter_cases(
    raw_cases: list[object],
    *,
    filter_settings: AgentFilterSettings,
    prompt_settings: AgentPromptSettings,
) -> dict[str, object]:
    cases = [case for case in raw_cases if isinstance(case, dict)]
    if not cases:
        return {
            "total": 0,
            "correct": 0,
            "accuracy": 0.0,
            "mismatches": [],
            "mismatch_buckets": [],
        }

    forced_settings = replace(filter_settings, enabled=True)
    items = [_item_from_case(case) for case in cases]
    expected_keep_map = {
        _case_url(case): bool(case.get("expected_keep", False)) for case in cases
    }
    filtered_items = filter_items_with_agent(items, forced_settings, prompt_settings)
    actual_keep_urls = {item.url for item in filtered_items}

    correct = 0
    mismatches: list[dict[str, object]] = []
    mismatch_counter: Counter[str] = Counter()
    for item, case in zip(items, cases):
        actual_keep = item.url in actual_keep_urls
        expected_keep = expected_keep_map[item.url]
        if actual_keep == expected_keep:
            correct += 1
            continue
        bucket_key, bucket_label = _classify_filter_mismatch(
            case,
            actual_keep=actual_keep,
            expected_keep=expected_keep,
        )
        mismatch_counter[bucket_key] += 1
        mismatches.append(
            {
                "id": str(case.get("id", "")),
                "title": item.title,
                "expected": expected_keep,
                "actual": actual_keep,
                "reason": item.agent_reason,
                "bucket_key": bucket_key,
                "bucket_label": bucket_label,
            }
        )

    total = len(cases)
    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "mismatches": mismatches,
        "mismatch_buckets": [
            {"key": key, "label": _bucket_label(key), "count": count}
            for key, count in mismatch_counter.most_common()
        ],
    }


def _evaluate_summary_cases(
    raw_cases: list[object],
    *,
    filter_settings: AgentFilterSettings,
    prompt_settings: AgentPromptSettings,
) -> dict[str, object]:
    cases = [case for case in raw_cases if isinstance(case, dict)]
    if not cases:
        return {"total": 0, "coverage": 0.0, "details": []}

    forced_settings = replace(filter_settings, summary_enabled=True)
    total_topics = 0
    covered_topics = 0
    details: list[dict[str, object]] = []

    for case in cases:
        items = [
            _item_from_case(item_case)
            for item_case in case.get("items", [])
            if isinstance(item_case, dict)
        ]
        summary = generate_hot_news_summary(items, forced_settings, prompt_settings)
        expected_topics = [
            str(topic).strip()
            for topic in case.get("expected_topics", [])
            if str(topic).strip()
        ]
        covered = sum(1 for topic in expected_topics if topic in summary)
        total_topics += len(expected_topics)
        covered_topics += covered
        details.append(
            {
                "id": str(case.get("id", "")),
                "covered": covered,
                "expected": len(expected_topics),
                "summary": " ".join(summary.split()),
            }
        )

    return {
        "total": len(cases),
        "coverage": covered_topics / total_topics if total_topics else 0.0,
        "details": details,
    }


def _item_from_case(case: dict[str, object]) -> CollectedItem:
    return CollectedItem(
        source=str(case.get("source", "eval")),
        title=str(case.get("title", "")),
        url=_case_url(case),
        content_excerpt=str(case.get("content_excerpt", "")),
        matched_keywords=[
            str(keyword) for keyword in case.get("matched_keywords", []) if str(keyword)
        ],
        matched_categories=[
            str(category)
            for category in case.get("matched_categories", [])
            if str(category)
        ],
        score=int(case.get("score", 0) or 0),
    )


def _case_url(case: dict[str, object]) -> str:
    return str(case.get("url", f"https://example.com/eval/{case.get('id', 'item')}"))


def _build_prompt_settings(
    *,
    prompts_dir: Path,
    filter_version: str,
    summary_version: str,
) -> AgentPromptSettings:
    return AgentPromptSettings(
        filter_version=filter_version,
        summary_version=summary_version,
        filter_system_prompt=(prompts_dir / "filter" / f"{filter_version}.txt").read_text(
            encoding="utf-8"
        ).strip(),
        summary_system_prompt=(prompts_dir / "summary" / f"{summary_version}.txt").read_text(
            encoding="utf-8"
        ).strip(),
    )


def _classify_filter_mismatch(
    case: dict[str, object],
    *,
    actual_keep: bool,
    expected_keep: bool,
) -> tuple[str, str]:
    source = str(case.get("source", "")).strip().lower()
    title = str(case.get("title", "")).strip()
    excerpt = str(case.get("content_excerpt", "")).strip()
    text = f"{title} {excerpt}".lower()
    matched_keywords = {
        str(keyword).strip().lower()
        for keyword in case.get("matched_keywords", [])
        if str(keyword).strip()
    }
    matched_categories = {
        str(category).strip().lower()
        for category in case.get("matched_categories", [])
        if str(category).strip()
    }

    if not expected_keep and actual_keep:
        if source == "tieba" or "贴吧社区" in title or "吧简介" in excerpt:
            return _bucket("community_entry_false_positive")
        if "交易" in matched_keywords and _contains_any(
            text,
            ["如果", "假设", "猜想", "会怎样", "大计", "名单", "应该", "讨论"],
        ):
            return _bucket("speculative_trade_false_positive")
        if _contains_any(
            text,
            ["回顾", "回忆", "经典", "名场面", "新秀年", "生涯", "历史地位", "队史最佳"],
        ):
            return _bucket("nostalgia_false_positive")
        if _contains_any(
            text,
            ["票选", "阵容怎么排", "还能靠", "未来建队方向", "主观", "讨论帖", "猜想"],
        ):
            return _bucket("subjective_discussion_false_positive")
        if _contains_any(text, ["海报", "二创", "老婆晒", "合集", "场外", "科切拉"]):
            return _bucket("offcourt_noise_false_positive")
        return _bucket("other_false_positive")

    if expected_keep and not actual_keep:
        if "topic" in matched_categories and _contains_any(
            text,
            ["伤", "复出", "出战", "缺席", "恢复", "g2", "系列赛"],
        ):
            return _bucket("injury_update_false_negative")
        if _contains_any(
            text,
            ["赢球", "取胜", "掌控比赛", "g1", "纪录", "季后赛", "助攻", "比赛"],
        ):
            return _bucket("game_news_false_negative")
        if _contains_any(
            text,
            ["称", "表示", "采访", "赛后", "名记", "更新", "电台", "节目", "数据", "命中率"],
        ):
            return _bucket("quote_or_stat_false_negative")
        return _bucket("other_false_negative")

    return _bucket("other_false_negative")


def _contains_any(text: str, patterns: list[str]) -> bool:
    return any(pattern.lower() in text for pattern in patterns)


def _bucket(key: str) -> tuple[str, str]:
    return key, _bucket_label(key)


def _bucket_label(key: str) -> str:
    labels = {
        "community_entry_false_positive": "贴吧社区入口误保留",
        "speculative_trade_false_positive": "假设交易帖误保留",
        "nostalgia_false_positive": "情怀回顾帖误保留",
        "subjective_discussion_false_positive": "主观讨论帖误保留",
        "offcourt_noise_false_positive": "场外噪声误保留",
        "other_false_positive": "其他噪声误保留",
        "injury_update_false_negative": "伤病复出新闻漏保留",
        "game_news_false_negative": "比赛结果新闻漏保留",
        "quote_or_stat_false_negative": "采访数据类新闻漏保留",
        "other_false_negative": "其他新闻漏保留",
    }
    return labels.get(key, key)


def _top_mismatch_bucket_summary(buckets: list[dict[str, object]]) -> str:
    if not buckets:
        return "none"
    top_bucket = buckets[0]
    return f"{top_bucket['label']}({top_bucket['count']})"
