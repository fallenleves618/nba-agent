from __future__ import annotations

import json
from dataclasses import dataclass

from nba_agent.http import post_json
from nba_agent.models import AgentFilterSettings, CollectedItem


SYSTEM_PROMPT = """你是一个 NBA 中文日报筛选器。
目标：从候选内容里只保留真正值得进入日报的内容。

保留标准：
1. 与 NBA 明确相关，而不是泛体育或无关噪声。
2. 对今天的读者有信息价值，例如比赛、伤病、交易、赛后分析、重点讨论。
3. 去掉重复表达、纯水贴、标题党、信息密度极低的内容。
4. 如果是贴吧社区发现类内容，除非它本身是高相关入口且有明显价值，否则倾向丢弃。

输出要求：
1. 只返回 JSON。
2. JSON 结构必须是 {"decisions":[...]}。
3. 每个 decision 必须包含 id、keep、score、reason。
4. score 取 1 到 10 的整数。
"""

SUMMARY_SYSTEM_PROMPT = """你是一个 NBA 中文日报编辑。
你的任务是根据候选内容，总结当天最值得读者关注的高热度新闻。

要求：
1. 只总结输入里明确出现的信息，不要补充外部事实。
2. 输出中文简报，3 到 5 条，每条一行，以 '- ' 开头。
3. 优先总结比赛结果、伤病、交易、重大赛后讨论、热度最高的话题。
4. 避免重复，避免空话，句子短一些。
"""


@dataclass
class AgentDecision:
    item_id: str
    keep: bool
    score: int
    reason: str


def filter_items_with_agent(
    items: list[CollectedItem], settings: AgentFilterSettings
) -> list[CollectedItem]:
    if not items or not _is_filter_enabled(settings):
        return items

    kept: list[CollectedItem] = []
    for start in range(0, len(items), settings.batch_size):
        batch = items[start : start + settings.batch_size]
        decisions = _request_batch_decisions(batch, settings)
        decision_map = {decision.item_id: decision for decision in decisions}

        for idx, item in enumerate(batch, start=1):
            batch_item_id = str(idx)
            decision = decision_map.get(batch_item_id)
            if decision is None:
                kept.append(item)
                continue

            item.agent_score = decision.score
            item.agent_reason = decision.reason
            if decision.keep and decision.score >= settings.min_score:
                kept.append(item)

    return kept


def _is_filter_enabled(settings: AgentFilterSettings) -> bool:
    return bool(settings.enabled and _is_model_configured(settings))


def _is_summary_enabled(settings: AgentFilterSettings) -> bool:
    return bool(settings.summary_enabled and _is_model_configured(settings))


def _is_model_configured(settings: AgentFilterSettings) -> bool:
    return bool(
        settings.api_base_url.strip()
        and settings.api_key.strip()
        and settings.model.strip()
    )


def generate_hot_news_summary(
    items: list[CollectedItem], settings: AgentFilterSettings
) -> str:
    summary_candidates = select_summary_candidates(items, settings)
    if not summary_candidates:
        return ""
    if not _is_summary_enabled(settings):
        return _fallback_hot_news_summary(summary_candidates)

    summary_text = _request_summary_text(summary_candidates, settings)
    if summary_text.strip():
        return summary_text
    return _fallback_hot_news_summary(summary_candidates)


def select_summary_candidates(
    items: list[CollectedItem], settings: AgentFilterSettings
) -> list[CollectedItem]:
    if not items:
        return []

    ranked_items = sorted(
        items,
        key=lambda item: (
            item.agent_score is not None,
            item.agent_score if item.agent_score is not None else item.score,
            item.score,
            item.publish_time is not None,
            item.publish_time,
        ),
        reverse=True,
    )
    return ranked_items[: settings.summary_top_n]


def _fallback_hot_news_summary(items: list[CollectedItem]) -> str:
    ranked_items = sorted(
        items,
        key=lambda item: (
            item.agent_score is not None,
            item.agent_score if item.agent_score is not None else item.score,
            item.score,
            item.publish_time is not None,
            item.publish_time,
        ),
        reverse=True,
    )
    lines: list[str] = []
    for item in ranked_items[:3]:
        keywords = "、".join(item.matched_keywords[:3]) if item.matched_keywords else item.source
        lines.append(f"- {item.title}。关键词：{keywords}。")
    return "\n".join(lines)


def _request_batch_decisions(
    items: list[CollectedItem], settings: AgentFilterSettings
) -> list[AgentDecision]:
    response_text = _request_chat_completion(
        settings=settings,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_build_user_prompt(items),
    )
    if not response_text:
        return []

    try:
        return _parse_decisions(response_text)
    except (TypeError, json.JSONDecodeError):
        return []


def _request_summary_text(
    items: list[CollectedItem], settings: AgentFilterSettings
) -> str:
    response_text = _request_chat_completion(
        settings=settings,
        system_prompt=SUMMARY_SYSTEM_PROMPT,
        user_prompt=_build_summary_prompt(items),
    )
    return _strip_code_fences(response_text)


def _request_chat_completion(
    *,
    settings: AgentFilterSettings,
    system_prompt: str,
    user_prompt: str,
) -> str:
    if settings.api_mode == "responses":
        return _request_responses_api(
            settings=settings,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    return _request_chat_completions_api(
        settings=settings,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


def _request_chat_completions_api(
    *,
    settings: AgentFilterSettings,
    system_prompt: str,
    user_prompt: str,
) -> str:
    payload = {
        "model": settings.model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    ok, response_text = post_json(
        _chat_completions_url(settings.api_base_url),
        payload,
        timeout=settings.timeout_seconds,
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Accept": "application/json",
        },
    )
    if not ok:
        return ""

    try:
        response = json.loads(response_text)
        return (
            response["choices"][0]["message"]["content"]
            if response.get("choices")
            else ""
        )
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return ""


def _request_responses_api(
    *,
    settings: AgentFilterSettings,
    system_prompt: str,
    user_prompt: str,
) -> str:
    payload: dict[str, object] = {
        "model": settings.model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
    }
    if settings.reasoning_effort:
        payload["reasoning"] = {"effort": settings.reasoning_effort}

    ok, response_text = post_json(
        _responses_url(settings.api_base_url),
        payload,
        timeout=settings.timeout_seconds,
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Accept": "application/json",
        },
    )
    if not ok:
        return ""

    try:
        response = json.loads(response_text)
    except json.JSONDecodeError:
        return ""

    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = response.get("output", [])
    if not isinstance(output, list):
        return ""

    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def _chat_completions_url(api_base_url: str) -> str:
    return api_base_url.rstrip("/") + "/chat/completions"


def _responses_url(api_base_url: str) -> str:
    return api_base_url.rstrip("/") + "/responses"


def _build_user_prompt(items: list[CollectedItem]) -> str:
    candidates = []
    for idx, item in enumerate(items, start=1):
        candidates.append(
            {
                "id": str(idx),
                "source": item.source,
                "title": item.title,
                "excerpt": item.content_excerpt,
                "matched_keywords": item.matched_keywords,
                "matched_categories": item.matched_categories,
                "rule_score": item.score,
                "url": item.url,
            }
        )
    return (
        "请逐条判断以下候选内容是否保留到 NBA 日报。\n"
        "返回 JSON: {\"decisions\":[{\"id\":\"1\",\"keep\":true,\"score\":8,"
        "\"reason\":\"...\"}]}\n\n"
        f"{json.dumps(candidates, ensure_ascii=False, indent=2)}"
    )


def _build_summary_prompt(items: list[CollectedItem]) -> str:
    candidates = []
    for idx, item in enumerate(items, start=1):
        candidates.append(
            {
                "rank": idx,
                "source": item.source,
                "title": item.title,
                "excerpt": item.content_excerpt,
                "matched_keywords": item.matched_keywords,
                "agent_score": item.agent_score,
                "rule_score": item.score,
            }
        )
    return (
        "请总结以下候选内容中当天最值得关注的高热度新闻。\n"
        "输出 3 到 5 条中文要点，每条以 '- ' 开头。\n\n"
        f"{json.dumps(candidates, ensure_ascii=False, indent=2)}"
    )


def _parse_decisions(content: str) -> list[AgentDecision]:
    cleaned = _strip_code_fences(content)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return []

    raw_decisions = payload.get("decisions", [])
    decisions: list[AgentDecision] = []
    for item in raw_decisions:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            continue
        score_raw = item.get("score", 0)
        try:
            score = int(score_raw)
        except (TypeError, ValueError):
            score = 0
        decisions.append(
            AgentDecision(
                item_id=item_id,
                keep=bool(item.get("keep", False)),
                score=max(0, min(10, score)),
                reason=str(item.get("reason", "")).strip(),
            )
        )
    return decisions


def _strip_code_fences(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned
