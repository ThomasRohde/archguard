"""Tests for hybrid search accuracy."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from archguard.core.embeddings import embedding_to_blob
from archguard.core.search import (
    RankedDoc,
    bm25_search,
    hybrid_search,
    rrf_score,
    vector_search,
)


class TestRRFScore:
    def test_single_rank(self) -> None:
        score = rrf_score([1])
        assert score == 1 / (60 + 1)

    def test_two_ranks(self) -> None:
        score = rrf_score([1, 2])
        expected = 1 / (60 + 1) + 1 / (60 + 2)
        assert abs(score - expected) < 1e-9

    def test_empty_ranks(self) -> None:
        assert rrf_score([]) == 0.0


class TestRankedDoc:
    def test_both_sources(self) -> None:
        doc = RankedDoc(doc_id="test", bm25_rank=1, vector_rank=3)
        expected = 1 / (60 + 1) + 1 / (60 + 3)
        assert abs(doc.rrf - expected) < 1e-9

    def test_bm25_only(self) -> None:
        doc = RankedDoc(doc_id="test", bm25_rank=5)
        expected = 1 / (60 + 5)
        assert abs(doc.rrf - expected) < 1e-9

    def test_no_ranks(self) -> None:
        doc = RankedDoc(doc_id="test")
        assert doc.rrf == 0.0


def _build_test_index(tmp_path: Path) -> Path:
    """Build a test index with two guardrails for search testing."""
    import orjson

    data_dir = tmp_path / "guardrails"
    data_dir.mkdir()
    (data_dir / "references.jsonl").touch()
    (data_dir / "links.jsonl").touch()
    (data_dir / "taxonomy.json").write_bytes(
        orjson.dumps({"scope": ["it-platform", "data-platform"]})
    )

    guardrails_data = [
        {
            "id": "01TEST_MANAGED_SVC00000001",
            "title": "Prefer managed services over self-hosted infrastructure",
            "status": "active",
            "severity": "should",
            "rationale": "Managed services reduce operational burden",
            "guidance": "Use managed offerings when available instead of self-hosted",
            "exceptions": "",
            "consequences": "",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "lifecycle_stage": ["acquire"],
            "owner": "Platform Team",
            "review_date": None,
            "superseded_by": None,
            "created_at": "2025-06-15T10:30:00Z",
            "updated_at": "2025-06-15T10:30:00Z",
            "metadata": {},
        },
        {
            "id": "01TEST_ENCRYPT_DATA0000002",
            "title": "Encrypt data at rest",
            "status": "active",
            "severity": "must",
            "rationale": "Security compliance requires encryption",
            "guidance": "All persistent stores must use AES-256 encryption at rest",
            "exceptions": "",
            "consequences": "",
            "scope": ["data-platform"],
            "applies_to": ["data", "technology"],
            "lifecycle_stage": ["build", "operate"],
            "owner": "Security Team",
            "review_date": None,
            "superseded_by": None,
            "created_at": "2025-06-15T10:30:00Z",
            "updated_at": "2025-06-15T10:30:00Z",
            "metadata": {},
        },
    ]

    with (data_dir / "guardrails.jsonl").open("wb") as f:
        for g in guardrails_data:
            f.write(orjson.dumps(g) + b"\n")

    from archguard.core.index import build_index
    from archguard.core.models import Guardrail

    db_path = data_dir / ".guardrails.db"
    models = [Guardrail(**g) for g in guardrails_data]
    build_index(db_path, models, [], [])
    return db_path


def _build_feedback_index(tmp_path: Path) -> Path:
    """Build a test index mirroring the feedback retrieval cases."""
    import orjson

    data_dir = tmp_path / "feedback_guardrails"
    data_dir.mkdir()
    (data_dir / "references.jsonl").touch()
    (data_dir / "links.jsonl").touch()
    (data_dir / "taxonomy.json").write_bytes(
        orjson.dumps({"scope": ["it-platform", "data-platform"]})
    )

    guardrails_data = [
        {
            "id": "01TEST_KAFKA_SPECIFIC000001",
            "title": "Use managed Kafka offerings instead of self-hosted clusters",
            "status": "active",
            "severity": "should",
            "rationale": "Managed Kafka reduces cluster operations.",
            "guidance": "Prefer platform-managed Kafka services over self-hosted Kafka clusters.",
            "exceptions": "",
            "consequences": "",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "lifecycle_stage": ["build"],
            "owner": "Platform Team",
            "review_date": None,
            "superseded_by": None,
            "created_at": "2025-06-15T10:30:00Z",
            "updated_at": "2025-06-15T10:30:00Z",
            "metadata": {},
        },
        {
            "id": "01TEST_MANAGED_MSG00000002",
            "title": "Prefer managed messaging services over self-hosted brokers",
            "status": "active",
            "severity": "should",
            "rationale": "Managed messaging reduces broker operations.",
            "guidance": (
                "Use cloud-managed messaging platforms unless a documented "
                "exception is approved."
            ),
            "exceptions": "",
            "consequences": "",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "lifecycle_stage": ["build"],
            "owner": "Platform Team",
            "review_date": None,
            "superseded_by": None,
            "created_at": "2025-06-15T10:30:00Z",
            "updated_at": "2025-06-15T10:30:00Z",
            "metadata": {},
        },
        {
            "id": "01TEST_ENCRYPT_KEYS0000003",
            "title": "Encrypt data at rest with platform-managed keys",
            "status": "active",
            "severity": "must",
            "rationale": "Protect stored data.",
            "guidance": "Use encryption at rest with provider-managed keys.",
            "exceptions": "",
            "consequences": "",
            "scope": ["data-platform"],
            "applies_to": ["data"],
            "lifecycle_stage": ["operate"],
            "owner": "Security Team",
            "review_date": None,
            "superseded_by": None,
            "created_at": "2025-06-15T10:30:00Z",
            "updated_at": "2025-06-15T10:30:00Z",
            "metadata": {},
        },
    ]

    with (data_dir / "guardrails.jsonl").open("wb") as f:
        for g in guardrails_data:
            f.write(orjson.dumps(g) + b"\n")

    from archguard.core.index import build_index
    from archguard.core.models import Guardrail

    db_path = data_dir / ".guardrails.db"
    models = [Guardrail(**g) for g in guardrails_data]
    build_index(db_path, models, [], [])
    return db_path


def _build_historical_index(tmp_path: Path) -> Path:
    """Build a test index with active and superseded results for lifecycle filtering."""
    import orjson

    data_dir = tmp_path / "historical_guardrails"
    data_dir.mkdir()
    (data_dir / "references.jsonl").touch()
    (data_dir / "links.jsonl").touch()
    (data_dir / "taxonomy.json").write_bytes(orjson.dumps({"scope": ["it-platform"]}))

    guardrails_data = [
        {
            "id": "01TEST_ACTIVE_SECRET000001",
            "title": "Use platform secret stores",
            "status": "active",
            "severity": "must",
            "rationale": "Secret stores reduce credential leakage.",
            "guidance": "Store application secrets in the managed platform secret store.",
            "exceptions": "",
            "consequences": "",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "lifecycle_stage": ["build"],
            "owner": "Security Team",
            "review_date": None,
            "superseded_by": None,
            "created_at": "2025-06-15T10:30:00Z",
            "updated_at": "2025-06-15T10:30:00Z",
            "metadata": {},
        },
        {
            "id": "01TEST_OLD_SECRET00000002",
            "title": "Store secrets in a central vault",
            "status": "superseded",
            "severity": "must",
            "rationale": "A central vault protects credentials.",
            "guidance": "Store secrets in the old central vault.",
            "exceptions": "",
            "consequences": "",
            "scope": ["it-platform"],
            "applies_to": ["technology"],
            "lifecycle_stage": ["build"],
            "owner": "Security Team",
            "review_date": None,
            "superseded_by": "01TEST_ACTIVE_SECRET000001",
            "created_at": "2025-06-15T10:30:00Z",
            "updated_at": "2025-06-15T10:30:00Z",
            "metadata": {},
        },
    ]

    with (data_dir / "guardrails.jsonl").open("wb") as f:
        for g in guardrails_data:
            f.write(orjson.dumps(g) + b"\n")

    from archguard.core.index import build_index
    from archguard.core.models import Guardrail

    db_path = data_dir / ".guardrails.db"
    models = [Guardrail(**g) for g in guardrails_data]
    build_index(db_path, models, [], [])
    return db_path


class TestBM25Search:
    def test_matches_keyword(self, tmp_path) -> None:
        db_path = _build_test_index(tmp_path)
        from archguard.core.index import get_connection

        conn = get_connection(db_path)
        try:
            results = bm25_search(conn, "managed services")
            assert len(results) >= 1
            doc_ids = [r[0] for r in results]
            assert "01TEST_MANAGED_SVC00000001" in doc_ids
        finally:
            conn.close()

    def test_matches_encryption(self, tmp_path) -> None:
        db_path = _build_test_index(tmp_path)
        from archguard.core.index import get_connection

        conn = get_connection(db_path)
        try:
            results = bm25_search(conn, "encryption")
            assert len(results) >= 1
            doc_ids = [r[0] for r in results]
            assert "01TEST_ENCRYPT_DATA0000002" in doc_ids
        finally:
            conn.close()

    def test_no_match(self, tmp_path) -> None:
        db_path = _build_test_index(tmp_path)
        from archguard.core.index import get_connection

        conn = get_connection(db_path)
        try:
            results = bm25_search(conn, "xyznonexistent")
            assert len(results) == 0
        finally:
            conn.close()


class TestVectorSearch:
    def test_with_synthetic_embeddings(self, tmp_path) -> None:
        db_path = _build_test_index(tmp_path)
        from archguard.core.index import get_connection

        conn = get_connection(db_path)
        try:
            # Insert synthetic embeddings
            vec1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
            vec2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            conn.execute(
                "UPDATE guardrails SET embedding = ? WHERE id = ?",
                (embedding_to_blob(vec1), "01TEST_MANAGED_SVC00000001"),
            )
            conn.execute(
                "UPDATE guardrails SET embedding = ? WHERE id = ?",
                (embedding_to_blob(vec2), "01TEST_ENCRYPT_DATA0000002"),
            )
            conn.commit()

            # Query close to vec1
            query_emb = np.array([0.9, 0.1, 0.0], dtype=np.float32)
            results = vector_search(conn, query_emb)
            assert len(results) == 2
            # First result should be the managed services guardrail
            assert results[0][0] == "01TEST_MANAGED_SVC00000001"
            assert results[0][1] == 1  # rank 1
        finally:
            conn.close()

    def test_no_embeddings(self, tmp_path) -> None:
        db_path = _build_test_index(tmp_path)
        from archguard.core.index import get_connection

        conn = get_connection(db_path)
        try:
            results = vector_search(conn, np.array([1.0, 0.0], dtype=np.float32))
            assert results == []
        finally:
            conn.close()


class TestHybridSearch:
    def test_bm25_only(self, tmp_path) -> None:
        db_path = _build_test_index(tmp_path)
        results, total = hybrid_search(db_path, "managed services", model=None)
        assert total >= 1
        assert any(r.id == "01TEST_MANAGED_SVC00000001" for r in results)
        assert all("bm25" in r.match_sources for r in results)

    def test_with_severity_filter(self, tmp_path) -> None:
        db_path = _build_test_index(tmp_path)
        results, _total = hybrid_search(
            db_path, "services encryption", model=None, filters={"severity": "must"}
        )
        assert all(r.severity == "must" for r in results)

    def test_with_scope_filter(self, tmp_path) -> None:
        db_path = _build_test_index(tmp_path)
        results, _total = hybrid_search(
            db_path, "managed services", model=None, filters={"scope": "data-platform"}
        )
        # Managed services is in it-platform, not data-platform
        assert all(r.id != "01TEST_MANAGED_SVC00000001" for r in results)

    def test_snippet_generation(self, tmp_path) -> None:
        db_path = _build_test_index(tmp_path)
        results, _ = hybrid_search(db_path, "managed services", model=None)
        for r in results:
            assert len(r.snippet) <= 150
            assert isinstance(r.snippet, str)

    def test_empty_query_returns_empty(self, tmp_path) -> None:
        db_path = _build_test_index(tmp_path)
        results, total = hybrid_search(db_path, "xyznotfound", model=None)
        assert total == 0
        assert results == []

    def test_managed_kafka_surfaces_broader_messaging_rule(self, tmp_path) -> None:
        db_path = _build_feedback_index(tmp_path)
        results, _ = hybrid_search(db_path, "managed kafka", model=None)
        doc_ids = [r.id for r in results]
        assert "01TEST_MANAGED_MSG00000002" in doc_ids

    def test_self_hosted_kafka_decision_surfaces_broader_messaging_rule(self, tmp_path) -> None:
        db_path = _build_feedback_index(tmp_path)
        results, _ = hybrid_search(
            db_path,
            "Use self-hosted Kafka for event streaming kafka self-hosted",
            model=None,
        )
        doc_ids = [r.id for r in results]
        assert "01TEST_MANAGED_MSG00000002" in doc_ids

    def test_low_coverage_noise_is_filtered_from_multi_term_queries(self, tmp_path) -> None:
        db_path = _build_feedback_index(tmp_path)
        results, _ = hybrid_search(db_path, "managed kafka", model=None)
        doc_ids = [r.id for r in results]
        assert "01TEST_ENCRYPT_KEYS0000003" not in doc_ids

    def test_status_list_filter_can_exclude_historical_records(self, tmp_path) -> None:
        db_path = _build_historical_index(tmp_path)
        results, _ = hybrid_search(
            db_path,
            "secret vault",
            model=None,
            filters={"status": ["draft", "active"]},
        )
        assert all(result.status in {"draft", "active"} for result in results)

    def test_historical_results_surface_superseded_by(self, tmp_path) -> None:
        db_path = _build_historical_index(tmp_path)
        results, _ = hybrid_search(
            db_path,
            "vault",
            model=None,
            demote_historical=True,
            min_score=0.0,
        )
        historical = [result for result in results if result.historical]
        assert historical
        assert historical[0].superseded_by == "01TEST_ACTIVE_SECRET000001"
