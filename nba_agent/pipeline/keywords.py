from __future__ import annotations

from nba_agent.models import CollectedItem, KeywordRules, KeywordTerm


def _normalize_text(text: str) -> str:
    return text.lower()


def _iter_terms(rules: KeywordRules) -> list[KeywordTerm]:
    if rules.terms:
        return rules.terms
    return [KeywordTerm(name=keyword, aliases=[keyword]) for keyword in rules.include_any]


def _term_hit(term: KeywordTerm, text: str) -> bool:
    normalized = _normalize_text(text)
    strong_hits = [
        alias for alias in term.aliases if alias and _normalize_text(alias) in normalized
    ]
    if strong_hits:
        return True

    weak_hits = [
        alias
        for alias in term.weak_aliases
        if alias and _normalize_text(alias) in normalized
    ]
    if not weak_hits:
        return False

    negative_hits = [
        alias
        for alias in term.exclude_aliases
        if alias and _normalize_text(alias) in normalized
    ]
    return not negative_hits


def matched_term_names(text: str, rules: KeywordRules) -> list[str]:
    return [term.name for term in _iter_terms(rules) if _term_hit(term, text)]


def matched_term_categories(text: str, rules: KeywordRules) -> list[str]:
    categories: list[str] = []
    seen: set[str] = set()
    for term in _iter_terms(rules):
        if not _term_hit(term, text):
            continue
        if term.category in seen:
            continue
        seen.add(term.category)
        categories.append(term.category)
    return categories


def seed_terms(rules: KeywordRules) -> list[str]:
    terms = _iter_terms(rules)
    return [term.name for term in terms]


def should_keep_text(text: str, rules: KeywordRules) -> bool:
    normalized = _normalize_text(text)
    if any(keyword.lower() in normalized for keyword in rules.exclude_any):
        return False

    terms = _iter_terms(rules)
    if not terms:
        return True
    return any(_term_hit(term, normalized) for term in terms)


def apply_keyword_rules(
    items: list[CollectedItem], rules: KeywordRules
) -> list[CollectedItem]:
    kept: list[CollectedItem] = []
    for item in items:
        haystack = f"{item.title}\n{item.content_excerpt}"
        normalized = _normalize_text(haystack)
        include_hits = matched_term_names(haystack, rules)
        exclude_hits = [
            keyword for keyword in rules.exclude_any if keyword.lower() in normalized
        ]

        if exclude_hits:
            continue
        if _iter_terms(rules) and not include_hits:
            continue

        group_hits = [
            group
            for group in rules.groups
            if group and all(term in include_hits for term in group)
        ]

        item.matched_keywords = include_hits
        item.matched_categories = matched_term_categories(haystack, rules)
        item.matched_groups = group_hits
        item.score = len(include_hits) + len(group_hits) * 3
        kept.append(item)

    return kept
