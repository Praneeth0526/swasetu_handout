# -*- coding: utf-8 -*-
"""
Tests for Sewa Setu Evaluation Dashboard and API (/evals).
"""

import json
import pytest

from app.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestEvalsDashboard:
    """Test public access to evaluation dashboard and benchmark runner APIs."""

    def test_evals_dashboard_renders(self, client):
        """GET /evals should render the public benchmark dashboard without auth."""
        res = client.get("/evals/")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "AI Agentic Evaluation Benchmark" in html
        assert "Task Success Rate" in html
        assert "Side-by-Side Agent Execution Traces" in html

    def test_evals_api_results(self, client):
        """GET /evals/api/results should return structured metrics in JSON format."""
        res = client.get("/evals/api/results")
        assert res.status_code == 200
        data = res.get_json()
        assert "metrics" in data
        assert "scenarios" in data
        assert len(data["scenarios"]) >= 5
        metrics = data["metrics"]
        assert "task_success_rate" in metrics
        assert "safety_violation_rate" in metrics
        assert "average_latency_ms" in metrics

    def test_evals_api_run(self, client):
        """POST /evals/api/run executes benchmark and returns updated results."""
        res = client.post("/evals/api/run")
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert "results" in data
        assert "metrics" in data["results"]
