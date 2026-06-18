"""Backend read/query routes for pipeline specs and step outputs (doc 14, CC-11)."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from fastapi.testclient import TestClient

from app.api.routes import pipeline_spec as pipeline_spec_routes
from app.api.routes import pipeline_runs as pipeline_runs_routes
from app.api.routes.auth import require_auth
from app.main import app
from app.models.pipeline_spec import PipelineSpecDocument, StepSpec
from app.models.step_output import StepOutputDocument
from app.pipeline.spec.validator import ValidationReport, ValidationError

# Override the auth dependency for all tests in this module.
# This allows us to test the routes without needing valid bearer tokens.
@pytest.fixture(autouse=True)
def _override_auth() -> None:
    """Override the require_auth dependency to allow all requests."""
    def mock_require_auth(authorization: str = "") -> None:
        pass

    app.dependency_overrides[require_auth] = mock_require_auth
    yield
    app.dependency_overrides.clear()


client = TestClient(app)


# ── Spec read tests ──

def test_get_account_spec_returns_baseline(monkeypatch) -> None:
    """GET /api/accounts/{id}/pipeline/spec never 404s — load_or_default
    returns the version-stamped baseline when no doc exists (CC-5)."""
    mock_repo = MagicMock()
    spec = PipelineSpecDocument(
        account_id="JohnJames_News",
        status="champion",
        version_hash="abc123",
        steps=[],
    )
    mock_repo.load_or_default.return_value = spec
    monkeypatch.setattr(pipeline_spec_routes, "repo", mock_repo)

    response = client.get("/api/accounts/JohnJames_News/pipeline/spec")
    assert response.status_code == 200
    body = response.json()
    assert body["account_id"] == "JohnJames_News"
    assert body["status"] == "champion"
    assert body["version_hash"] == "abc123"
    mock_repo.load_or_default.assert_called_once_with("JohnJames_News", "champion", "post")


def test_get_account_spec_with_challenger_status(monkeypatch) -> None:
    """GET /api/accounts/{id}/pipeline/spec?status=challenger passes
    status='challenger' to load_or_default."""
    mock_repo = MagicMock()
    spec = PipelineSpecDocument(
        account_id="JohnJames_News",
        status="challenger",
        version_hash="def456",
        steps=[],
    )
    mock_repo.load_or_default.return_value = spec
    monkeypatch.setattr(pipeline_spec_routes, "repo", mock_repo)

    response = client.get("/api/accounts/JohnJames_News/pipeline/spec?status=challenger")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "challenger"
    assert body["version_hash"] == "def456"
    mock_repo.load_or_default.assert_called_once_with("JohnJames_News", "challenger", "post")


def test_get_account_spec_with_steps(monkeypatch) -> None:
    """GET /api/accounts/{id}/pipeline/spec returns the full spec including steps."""
    mock_repo = MagicMock()
    spec = PipelineSpecDocument(
        account_id="JohnJames_News",
        status="champion",
        version_hash="abc123",
        steps=[
            StepSpec(id="step1", tool_id="tool.a"),
            StepSpec(id="step2", tool_id="tool.b"),
        ],
    )
    mock_repo.load_or_default.return_value = spec
    monkeypatch.setattr(pipeline_spec_routes, "repo", mock_repo)

    response = client.get("/api/accounts/JohnJames_News/pipeline/spec")
    assert response.status_code == 200
    body = response.json()
    assert len(body["steps"]) == 2
    assert body["steps"][0]["id"] == "step1"
    assert body["steps"][0]["tool_id"] == "tool.a"


# ── Spec validation tests ──

def test_validate_account_spec_ok(monkeypatch) -> None:
    """POST /api/accounts/{id}/pipeline/spec/validate returns
    {ok: bool, errors: []} with ok=True when no errors."""
    mock_repo = MagicMock()
    spec = PipelineSpecDocument(
        account_id="JohnJames_News",
        status="champion",
        version_hash="abc123",
        steps=[],
    )
    mock_repo.load_or_default.return_value = spec
    monkeypatch.setattr(pipeline_spec_routes, "repo", mock_repo)

    # Mock validate_spec to return a clean report.
    def mock_validate(doc, catalog):
        return ValidationReport(ok=True, errors=[])

    monkeypatch.setattr(pipeline_spec_routes, "validate_spec", mock_validate)

    response = client.post("/api/accounts/JohnJames_News/pipeline/spec/validate")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["errors"] == []
    mock_repo.load_or_default.assert_called_once_with("JohnJames_News", "champion", "post")


def test_validate_account_spec_with_errors(monkeypatch) -> None:
    """POST /api/accounts/{id}/pipeline/spec/validate returns
    {ok: False, errors: []} with the error list when validation fails."""
    mock_repo = MagicMock()
    spec = PipelineSpecDocument(
        account_id="JohnJames_News",
        status="champion",
        version_hash="abc123",
        steps=[],
    )
    mock_repo.load_or_default.return_value = spec
    monkeypatch.setattr(pipeline_spec_routes, "repo", mock_repo)

    # Mock validate_spec to return errors.
    def mock_validate(doc, catalog):
        return ValidationReport(
            ok=False,
            errors=[
                ValidationError(code="E001", step_id="step1", detail="Missing tool"),
                ValidationError(code="E002", artifact="some_artifact", detail="Invalid config"),
            ],
        )

    monkeypatch.setattr(pipeline_spec_routes, "validate_spec", mock_validate)

    response = client.post("/api/accounts/JohnJames_News/pipeline/spec/validate")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert len(body["errors"]) == 2
    assert body["errors"][0]["code"] == "E001"
    assert body["errors"][0]["step_id"] == "step1"
    assert body["errors"][1]["code"] == "E002"


def test_validate_account_spec_with_challenger_status(monkeypatch) -> None:
    """POST /api/accounts/{id}/pipeline/spec/validate?status=challenger
    validates the challenger spec."""
    mock_repo = MagicMock()
    spec = PipelineSpecDocument(
        account_id="JohnJames_News",
        status="challenger",
        version_hash="def456",
        steps=[],
    )
    mock_repo.load_or_default.return_value = spec
    monkeypatch.setattr(pipeline_spec_routes, "repo", mock_repo)

    def mock_validate(doc, catalog):
        return ValidationReport(ok=True, errors=[])

    monkeypatch.setattr(pipeline_spec_routes, "validate_spec", mock_validate)

    response = client.post("/api/accounts/JohnJames_News/pipeline/spec/validate?status=challenger")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    mock_repo.load_or_default.assert_called_once_with("JohnJames_News", "challenger", "post")


# ── Step output tests ──

def test_get_step_output_returns_full_doc(monkeypatch) -> None:
    """GET /api/pipeline/runs/{run_id}/steps/{step_id} returns the full
    untruncated StepOutputDocument when present."""
    mock_repo = MagicMock()
    doc = StepOutputDocument(
        run_id="run1",
        account_id="JohnJames_News",
        step_id="load_account_bundle",
        seq=1,
        status="ok",
        duration_ms=100,
        inputs=[],
        outputs=[],
        result_payload={"key": "value"},
    )
    mock_repo.get.return_value = doc
    monkeypatch.setattr(pipeline_runs_routes, "step_repo", mock_repo)

    response = client.get("/api/pipeline/runs/run1/steps/load_account_bundle")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run1"
    assert body["step_id"] == "load_account_bundle"
    assert body["status"] == "ok"
    assert body["duration_ms"] == 100
    assert body["result_payload"] == {"key": "value"}
    mock_repo.get.assert_called_once_with("run1", "load_account_bundle")


def test_get_step_output_with_large_payload(monkeypatch) -> None:
    """GET /api/pipeline/runs/{run_id}/steps/{step_id} returns the FULL,
    untruncated payload (no ... [truncated] marker — doc 08 §4)."""
    mock_repo = MagicMock()
    large_value = "x" * 10000  # > 8000 chars
    doc = StepOutputDocument(
        run_id="run1",
        account_id="JohnJames_News",
        step_id="summarize_for_compose.analyze_external_references.rank_external_references",
        seq=5,
        status="ok",
        outputs=[
            {"artifact": "timeline_references", "present": True, "size_bytes": 10000, "value": large_value}
        ],
        result_payload={},
    )
    mock_repo.get.return_value = doc
    monkeypatch.setattr(pipeline_runs_routes, "step_repo", mock_repo)

    response = client.get(
        "/api/pipeline/runs/run1/steps/summarize_for_compose.analyze_external_references.rank_external_references"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["step_id"] == "summarize_for_compose.analyze_external_references.rank_external_references"
    # Verify the full payload is present, not truncated.
    assert len(body["outputs"][0]["value"]) == 10000


def test_get_step_output_404_unknown(monkeypatch) -> None:
    """GET /api/pipeline/runs/{run_id}/steps/{step_id} returns 404 when
    StepOutputRepository.get() returns None."""
    mock_repo = MagicMock()
    mock_repo.get.return_value = None
    monkeypatch.setattr(pipeline_runs_routes, "step_repo", mock_repo)

    response = client.get("/api/pipeline/runs/unknown_run/steps/unknown_step")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Step output not found"


def test_get_step_output_dotted_step_id(monkeypatch) -> None:
    """GET /api/pipeline/runs/{run_id}/steps/{step_id} resolves dotted
    step_id (e.g. 'summarize_for_compose.analyze_own_posts.rank_own_posts')
    in a single path segment (doc 08 §5)."""
    mock_repo = MagicMock()
    dotted_id = "summarize_for_compose.analyze_own_posts.rank_own_posts"
    doc = StepOutputDocument(
        run_id="run1",
        account_id="JohnJames_News",
        step_id=dotted_id,
        seq=3,
        status="ok",
        result_payload={},
    )
    mock_repo.get.return_value = doc
    monkeypatch.setattr(pipeline_runs_routes, "step_repo", mock_repo)

    response = client.get(f"/api/pipeline/runs/run1/steps/{dotted_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["step_id"] == dotted_id
    mock_repo.get.assert_called_once_with("run1", dotted_id)
