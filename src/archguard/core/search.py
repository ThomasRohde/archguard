"""Hybrid search: BM25 (FTS5) + vector similarity + Reciprocal Rank Fusion."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import orjson

from archguard.core.embeddings import blob_to_embedding, cosine_similarity
from archguard.core.models import SearchResult
from archguard.core.search_terms import build_query_plan, count_matching_clauses

RRF_K = 60
HISTORICAL_STATUSES = frozenset({"deprecated", "superseded"})
HISTORICAL_SCORE_PENALTY = 0.01


def rrf_score(ranks: list[int], k: int = RRF_K) -> float:
    """Compute RRF score from a list of ranks (1-indexed)."""
    return sum(1.0 / (k + rank) for rank in ranks)


@dataclass
class RankedDoc:
    """Intermediate representation for RRF merging."""

    doc_id: str
    bm25_rank: int | None = None
    vector_rank: int | None = None

    @property
    def rrf(self) -> float:
        ranks: list[int] = []
        if self.bm25_rank is not None:
            ranks.append(self.bm25_rank)
        if self.vector_rank is not None:
            ranks.append(self.vector_rank)
        return rrf_score(ranks) if ranks else 0.0


def bm25_search(conn: sqlite3.Connection, query: str, limit: int = 100) -> list[tuple[str, int]]:
    """Execute FTS5 MATCH query and return [(doc_id, rank_position)] (1-indexed)."""
    plan = build_query_plan(query)
    if not plan.fts_query:
        return []
    try:
        rows = conn.execute(
            "SELECT id, rank FROM guardrails g JOIN guardrails_fts f ON g.rowid = f.rowid "
            "WHERE guardrails_fts MATCH ? ORDER BY f.rank LIMIT ?",
            (plan.fts_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(row[0], i + 1) for i, row in enumerate(rows)]


def vector_search(
    conn: sqlite3.Connection,
    query_embedding: npt.NDArray[np.float32],
    limit: int = 100,
    min_similarity: float = 0.0,
) -> list[tuple[str, int]]:
    """Load all non-NULL embeddings, compute cosine similarity, return top results."""
    rows = conn.execute(
        "SELECT id, embedding FROM guardrails WHERE embedding IS NOT NULL"
    ).fetchall()
    if not rows:
        return []

    scored: list[tuple[str, float]] = []
    for row in rows:
        emb = blob_to_embedding(row[1])
        sim = cosine_similarity(np.array(query_embedding, dtype=np.float32), emb)
        if sim >= min_similarity:
            scored.append((row[0], sim))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [(doc_id, i + 1) for i, (doc_id, _) in enumerate(scored[:limit])]


DEFAULT_MIN_SCORE = 0.005


def _relevance_label(score: float) -> str:
    """Classify an RRF score into high/medium/low relevance."""
    if score >= 0.02:
        return "high"
    if score >= 0.01:
        return "medium"
    return "low"


def hybrid_search(
    db_path: Path,
    query: str,
    model: Any = None,
    filters: dict[str, str | list[str] | None] | None = None,
    top: int = 10,
    min_score: float = DEFAULT_MIN_SCORE,
    *,
    demote_historical: bool = False,
) -> tuple[list[SearchResult], int]:
    """Run hybrid BM25+vector search with RRF fusion and filters."""
    from archguard.core.index import get_connection

    conn = get_connection(db_path)
    try:
        query_plan = build_query_plan(query)

        # BM25 search
        bm25_results = bm25_search(conn, query)
        bm25_count = len(bm25_results)
        match_sources_map: dict[str, list[str]] = {}
        for doc_id, _ in bm25_results:
            match_sources_map.setdefault(doc_id, []).append("bm25")

        # Vector search (if model available)
        vector_results: list[tuple[str, int]] = []
        if model is not None:
            from archguard.core.embeddings import embed_text

            query_embedding = embed_text(model, query)
            vector_results = vector_search(conn, query_embedding, min_similarity=0.3)
            for doc_id, _ in vector_results:
                match_sources_map.setdefault(doc_id, []).append("vector")

        # Merge via RRF
        docs: dict[str, RankedDoc] = {}
        for doc_id, rank in bm25_results:
            docs.setdefault(doc_id, RankedDoc(doc_id=doc_id)).bm25_rank = rank
        for doc_id, rank in vector_results:
            docs.setdefault(doc_id, RankedDoc(doc_id=doc_id)).vector_rank = rank

        ranked = sorted(docs.values(), key=lambda d: d.rrf, reverse=True)

        # Load full guardrail rows for ranked results
        results: list[SearchResult] = []
        for rd in ranked:
            row = conn.execute(
                "SELECT id, title, severity, status, guidance, scope, applies_to, "
                "lifecycle_stage, owner, superseded_by FROM guardrails WHERE id = ?",
                (rd.doc_id,),
            ).fetchone()
            if row is None:
                continue

            searchable_text = " ".join(
                [
                    row[1],
                    row[4] or "",
                    row[5] or "",
                    row[6] or "",
                    row[7] or "",
                    row[8] or "",
                ]
            )
            matched_clause_count = count_matching_clauses(query_plan, searchable_text)
            total_clauses = len(query_plan.clauses)

            if (
                rd.bm25_rank is not None
                and total_clauses > 1
                and bm25_count >= 2
                and matched_clause_count < 2
            ):
                continue
            if rd.bm25_rank is None and total_clauses > 1 and bm25_count >= 2:
                continue

            # Apply post-ranking filters
            if filters:
                status_val = filters.get("status")
                if status_val:
                    if isinstance(status_val, list):
                        if row[3] not in status_val:
                            continue
                    elif row[3] != status_val:
                        continue
                severity_val = filters.get("severity")
                if isinstance(severity_val, str) and row[2] != severity_val:
                    continue
                scope_val = filters.get("scope")
                if scope_val:
                    row_scope: list[str] = orjson.loads(row[5])
                    if isinstance(scope_val, list):
                        if not any(s in row_scope for s in scope_val):
                            continue
                    elif scope_val not in row_scope:
                        continue
                applies_val = filters.get("applies_to")
                if applies_val:
                    row_applies: list[str] = orjson.loads(row[6])
                    if isinstance(applies_val, list):
                        if not any(a in row_applies for a in applies_val):
                            continue
                    elif applies_val not in row_applies:
                        continue
                lc_val = filters.get("lifecycle_stage")
                if isinstance(lc_val, str):
                    row_lc: list[str] = orjson.loads(row[7])
                    if lc_val not in row_lc:
                        continue
                owner_val = filters.get("owner")
                if isinstance(owner_val, str) and row[8] != owner_val:
                    continue

            coverage_bonus = (
                (matched_clause_count / total_clauses) * 0.002
                if total_clauses > 0 and rd.bm25_rank is not None
                else 0.0
            )
            score = rd.rrf + coverage_bonus
            historical = row[3] in HISTORICAL_STATUSES
            if demote_historical and historical:
                score = max(score - HISTORICAL_SCORE_PENALTY, 0.0)
            score = round(score, 6)
            if score < min_score:
                continue

            snippet: str = row[4][:150] if row[4] else ""
            sources = match_sources_map.get(rd.doc_id, [])
            results.append(
                SearchResult(
                    id=row[0],
                    title=row[1],
                    severity=row[2],
                    status=row[3],
                    historical=historical,
                    superseded_by=row[9],
                    score=score,
                    relevance=_relevance_label(score),  # type: ignore[arg-type]
                    match_sources=sources,  # type: ignore[arg-type]
                    snippet=snippet,
                )
            )

        results.sort(key=lambda result: result.score, reverse=True)
        total = len(results)
        return results[:top], total
    finally:
        conn.close()
