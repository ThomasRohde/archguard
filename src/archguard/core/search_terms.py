"""Shared query normalization helpers for lexical search and indexing."""

from __future__ import annotations

import re
from dataclasses import dataclass

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "any",
        "architecture",
        "architectural",
        "for",
        "in",
        "into",
        "is",
        "of",
        "on",
        "or",
        "our",
        "please",
        "rule",
        "rules",
        "service",
        "services",
        "system",
        "systems",
        "that",
        "the",
        "this",
        "to",
        "use",
        "using",
        "with",
    }
)
_CONCEPT_TERMS: dict[str, tuple[str, ...]] = {
    "managed_service": (
        "managed",
        "cloud managed",
        "platform managed",
        "provider managed",
        "saas",
    ),
    "self_hosted": (
        "self hosted",
        "self managed",
        "on prem",
        "on premise",
        "on premises",
        "customer hosted",
    ),
    "messaging": (
        "kafka",
        "messaging",
        "broker",
        "brokers",
        "queue",
        "queues",
        "pubsub",
        "stream",
        "streams",
        "streaming",
        "event streaming",
    ),
    "encryption_at_rest": (
        "encrypt",
        "encrypted",
        "encryption",
        "at rest",
        "kms",
        "key management",
        "keys",
    ),
}


@dataclass(frozen=True)
class SearchClause:
    """One logical retrieval clause made up of one or more synonymous terms."""

    key: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class QueryPlan:
    """Normalized lexical retrieval plan derived from a user query."""

    raw_query: str
    clauses: tuple[SearchClause, ...]

    @property
    def fts_query(self) -> str:
        if not self.clauses:
            return ""
        clause_parts: list[str] = []
        for clause in self.clauses:
            if len(clause.terms) == 1:
                clause_parts.append(_quote_term(clause.terms[0]))
                continue
            joined = " OR ".join(_quote_term(term) for term in clause.terms)
            clause_parts.append(f"({joined})")
        return " OR ".join(clause_parts)


def normalize_text(text: str) -> str:
    """Normalize free text for token and phrase matching."""
    lowered = text.lower().replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", _NON_ALNUM_RE.sub(" ", lowered)).strip()


def build_query_plan(query: str) -> QueryPlan:
    """Convert free text into a concept-aware lexical search plan."""
    normalized = normalize_text(query)
    if not normalized:
        return QueryPlan(raw_query=query, clauses=())

    tokens = tuple(_TOKEN_RE.findall(normalized))
    token_set = set(tokens)
    clauses: list[SearchClause] = []
    consumed_tokens: set[str] = set()

    for concept, terms in _CONCEPT_TERMS.items():
        if any(_contains_term(normalized, token_set, term) for term in terms):
            clauses.append(SearchClause(key=concept, terms=terms))
            for term in terms:
                consumed_tokens.update(_TOKEN_RE.findall(term))

    for token in tokens:
        if token in consumed_tokens or token in _STOP_WORDS or len(token) < 3:
            continue
        clauses.append(SearchClause(key=f"term:{token}", terms=(token,)))
        consumed_tokens.add(token)

    return QueryPlan(raw_query=query, clauses=tuple(dict.fromkeys(clauses)))


def derive_search_terms(text: str) -> tuple[str, ...]:
    """Expand a document into nearby architectural terms for lexical recall."""
    normalized = normalize_text(text)
    if not normalized:
        return ()
    token_set = set(_TOKEN_RE.findall(normalized))
    expanded: list[str] = []
    for terms in _CONCEPT_TERMS.values():
        if any(_contains_term(normalized, token_set, term) for term in terms):
            expanded.extend(terms)
    return tuple(dict.fromkeys(expanded))


def count_matching_clauses(plan: QueryPlan, text: str) -> int:
    """Count how many query clauses are satisfied by the given document text."""
    if not plan.clauses:
        return 0
    normalized = normalize_text(text)
    token_set = set(_TOKEN_RE.findall(normalized))
    return sum(
        1
        for clause in plan.clauses
        if any(_contains_term(normalized, token_set, term) for term in clause.terms)
    )


def _contains_term(normalized_text: str, token_set: set[str], term: str) -> bool:
    normalized_term = normalize_text(term)
    if " " in normalized_term:
        return normalized_term in normalized_text
    return normalized_term in token_set


def _quote_term(term: str) -> str:
    if " " in term:
        return f"\"{term}\""
    return term
