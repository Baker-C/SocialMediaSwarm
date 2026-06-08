"""Pipeline tool catalog and central import surface."""

from __future__ import annotations

import pytest

from app.pipeline import pipeline, tools
from app.pipeline.service import reset_pipeline


@pytest.fixture(autouse=True)
def _fresh_pipeline() -> None:
    reset_pipeline()
    yield
    reset_pipeline()


def test_tools_namespace_data() -> None:
    mod = tools.data.timeline_fetch
    assert mod.id == "data.timeline_fetch"
    assert mod.kind == "data"
    assert mod.source == "x_timeline"
    assert callable(mod.run)

    search_mod = tools.data.search_fetch
    assert search_mod.id == "data.search_fetch"
    assert search_mod.source == "x_search"


def test_tools_namespace_llm() -> None:
    mod = tools.llm.compose_timeline_post
    assert mod.id == "llm.compose_timeline_post"
    assert mod.kind == "llm"
    assert mod.prompt_stem == "compose_timeline_post"


def test_tools_llm_as_dict() -> None:
    llm_map = tools.llm.as_dict()
    assert "compose_timeline_post" in llm_map
    assert "reference_pattern_summary" in llm_map
    assert llm_map["reference_pattern_summary"].kind == "llm"


def test_tools_get_by_id() -> None:
    mod = tools.get("deterministic.reference_rank")
    assert mod.name == "reference_rank"


def test_tools_by_kind_matches_namespace() -> None:
    assert tools.by_kind("data").names() == tools.data.names()


def test_pipeline_singleton_matches_tools() -> None:
    assert pipeline.tools.data.account_profile.id == tools.data.account_profile.id


def test_registry_lists_llm_tools() -> None:
    llm_ids = pipeline.registry.tool_ids(kind="llm")
    assert "llm.compose_timeline_post" in llm_ids
    assert "llm.reference_pattern_summary" in llm_ids


def test_registry_lists_data_search_fetch() -> None:
    data_ids = pipeline.registry.tool_ids(kind="data")
    assert "data.search_fetch" in data_ids
