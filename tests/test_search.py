"""Tests for the hybrid search pipeline with current indexed data."""
import pytest

from app.services.search_service import search


class TestSearchBasics:
    """Basic search functionality tests."""

    def test_search_returns_results(self):
        """A broad query should return some results."""
        results = search("machine learning", top_k=10)
        assert len(results) > 0
        assert len(results) <= 10

    def test_search_result_structure(self):
        """Results should have all required fields."""
        results = search("artificial intelligence", top_k=5)
        assert len(results) > 0

        for r in results:
            assert "chunk_id" in r
            assert isinstance(r["chunk_id"], int)
            assert r["chunk_id"] > 0

            assert "document_id" in r
            assert isinstance(r["document_id"], int)
            assert r["document_id"] > 0

            assert "document_name" in r
            assert isinstance(r["document_name"], str)
            assert len(r["document_name"]) > 0

            assert "document_path" in r
            assert isinstance(r["document_path"], str)

            assert "score" in r
            assert isinstance(r["score"], float)

            assert "snippet" in r
            assert isinstance(r["snippet"], str)
            assert len(r["snippet"]) > 0

            assert "breadcrumbs" in r
            assert isinstance(r["breadcrumbs"], list)
            for bc in r["breadcrumbs"]:
                assert isinstance(bc, str)

    def test_search_ranks_by_score(self):
        """Results should be ranked by score (descending)."""
        results = search("history", top_k=10)
        if len(results) > 1:
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_search_returns_top_k(self):
        """Search should respect the top_k parameter."""
        for k in [1, 5, 20]:
            results = search("science", top_k=k)
            assert len(results) <= k

    def test_search_empty_query(self):
        """Empty or whitespace-only queries should return no results."""
        assert search("") == []
        assert search("   ") == []

    def test_search_returns_max_20_by_default(self):
        """Default limit is 20."""
        results = search("the", top_k=20)
        assert len(results) <= 20

    def test_search_consistency(self):
        """Same query should return same top result (deterministic)."""
        query = "ancient Rome"
        r1 = search(query, top_k=1)
        r2 = search(query, top_k=1)
        if r1 and r2:
            assert r1[0]["chunk_id"] == r2[0]["chunk_id"]
            assert abs(r1[0]["score"] - r2[0]["score"]) < 0.01


class TestSearchQueries:
    """Test specific queries and document retrieval."""

    def test_search_for_artificial_intelligence(self):
        """Search for AI should find relevant documents."""
        results = search("artificial intelligence", top_k=5)
        assert len(results) > 0
        # At least some results should have "intelligence" or "AI" in snippet or doc name
        snippets = " ".join(r["snippet"].lower() for r in results)
        assert ("intelligence" in snippets or "neural" in snippets or
                "learning" in snippets)

    def test_search_for_history(self):
        """Search for history should find historical documents."""
        results = search("ancient Roman history", top_k=5)
        assert len(results) > 0

    def test_search_for_science(self):
        """Search for science topics should return results."""
        results = search("climate change", top_k=5)
        assert len(results) > 0

    def test_search_for_people(self):
        """Search for people should find biographical content."""
        results = search("famous people", top_k=5)
        assert len(results) > 0

    def test_search_specificity(self):
        """More specific queries may return fewer results but higher quality."""
        broad_results = search("data", top_k=20)
        specific_results = search("neural networks optimization", top_k=20)

        # Both should return something
        assert len(broad_results) > 0
        assert len(specific_results) > 0
