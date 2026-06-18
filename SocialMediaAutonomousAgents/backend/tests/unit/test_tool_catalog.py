"""Unit tests for tool catalog introspection."""

from __future__ import annotations

import pytest

from app.models.tool_catalog import ConfigField, ToolCatalogDocument, ToolParameter, config_type
from app.pipeline.spec.catalog import (
    build_tool_catalog,
    get_tool,
    get_tool_catalog,
    tool_catalog_hash,
)


class TestToolCatalogIntrospection:
    """Test that the six SENSE tools are correctly introspected."""

    def test_build_tool_catalog_returns_six_tools(self) -> None:
        """The catalog must contain exactly six tools, no more, no less."""
        catalog = build_tool_catalog()
        assert len(catalog) == 6
        tool_ids = [t.tool_id for t in catalog]
        expected = [
            "data.account_profile",
            "data.search_fetch",
            "data.own_posts_fetch",
            "deterministic.reference_rank",
            "llm.reference_pattern_summary",
            "llm.compose_timeline_post",
        ]
        assert tool_ids == expected

    def test_get_tool_catalog_returns_lookup_object(self) -> None:
        """get_tool_catalog() returns a ToolCatalog with correct interface."""
        catalog = get_tool_catalog()
        assert "data.account_profile" in catalog
        assert "nope" not in catalog
        tool = catalog.get("data.account_profile")
        assert tool is not None
        assert tool.tool_id == "data.account_profile"
        assert catalog.all() is not None
        assert len(catalog.all()) == 6

    def test_get_tool_convenience_function(self) -> None:
        """get_tool(tool_id) returns the same result as catalog.get(tool_id)."""
        tool = get_tool("data.account_profile")
        assert tool is not None
        assert tool.tool_id == "data.account_profile"

    def test_account_profile_metadata(self) -> None:
        """data.account_profile has correct metadata and parameter classification."""
        catalog = get_tool_catalog()
        tool = catalog.get("data.account_profile")
        assert tool is not None
        assert tool.kind == "data"
        assert "Load X profile" in tool.purpose
        assert tool.source == "x_api"
        assert tool.output_model == "AccountBundle"
        assert tool.writes == ["account_bundle"]
        assert tool.reads is None

    def test_account_profile_parameters(self) -> None:
        """data.account_profile: tick_data injected, account_id runtime config."""
        catalog = get_tool_catalog()
        tool = catalog.get("data.account_profile")
        assert tool is not None

        # tick_data is injected
        tick_data_param = next((p for p in tool.parameters if p.name == "tick_data"), None)
        assert tick_data_param is not None
        assert tick_data_param.kind == "injected"
        assert tick_data_param.config_origin == "injected"
        assert tick_data_param.required

        # account_id is runtime config
        account_id_param = next((p for p in tool.parameters if p.name == "account_id"), None)
        assert account_id_param is not None
        assert account_id_param.kind == "config"
        assert account_id_param.config_origin == "runtime"
        assert not account_id_param.required
        assert account_id_param.default is None

        # injected_params should only include tick_data
        assert len(tool.injected_params) == 1
        assert tool.injected_params[0].name == "tick_data"

        # proposable_params should be empty (no literal params)
        assert len(tool.proposable_params) == 0

    def test_reference_rank_dynamic_writes(self) -> None:
        """deterministic.reference_rank has dynamic writes (None) because store_key resolves at runtime."""
        catalog = get_tool_catalog()
        tool = catalog.get("deterministic.reference_rank")
        assert tool is not None
        assert tool.kind == "deterministic"
        assert tool.output_model == "RankedReferencesPayload"
        assert tool.writes is None  # dynamic
        assert tool.reads is None  # dynamic

    def test_reference_rank_proposable_params(self) -> None:
        """deterministic.reference_rank: top_n is literal/proposable, rows/store_key are wired."""
        catalog = get_tool_catalog()
        tool = catalog.get("deterministic.reference_rank")
        assert tool is not None

        # top_n is literal
        top_n_param = next((p for p in tool.parameters if p.name == "top_n"), None)
        assert top_n_param is not None
        assert top_n_param.kind == "config"
        assert top_n_param.config_origin == "literal"
        assert top_n_param.default == 10
        assert not top_n_param.required

        # rows is wired
        rows_param = next((p for p in tool.parameters if p.name == "rows"), None)
        assert rows_param is not None
        assert rows_param.kind == "config"
        assert rows_param.config_origin == "wired"
        assert rows_param.required

        # store_key is wired
        store_key_param = next((p for p in tool.parameters if p.name == "store_key"), None)
        assert store_key_param is not None
        assert store_key_param.kind == "config"
        assert store_key_param.config_origin == "wired"
        assert not store_key_param.required

        # exclude_ids is wired
        exclude_ids_param = next((p for p in tool.parameters if p.name == "exclude_ids"), None)
        assert exclude_ids_param is not None
        assert exclude_ids_param.config_origin == "wired"

        # proposable_params should only include top_n
        assert len(tool.proposable_params) == 1
        assert tool.proposable_params[0].name == "top_n"

    def test_reference_rank_config_schema(self) -> None:
        """reference_rank.config_schema only includes top_n, typed as int."""
        catalog = get_tool_catalog()
        tool = catalog.get("deterministic.reference_rank")
        assert tool is not None

        schema = tool.config_schema
        assert len(schema) == 1
        assert schema[0].name == "top_n"
        assert schema[0].type == "int"
        assert not schema[0].required  # has default

    def test_search_fetch_proposable_params(self) -> None:
        """data.search_fetch: max_results_per_query is the only literal param."""
        catalog = get_tool_catalog()
        tool = catalog.get("data.search_fetch")
        assert tool is not None

        max_results = next(
            (p for p in tool.parameters if p.name == "max_results_per_query"), None
        )
        assert max_results is not None
        assert max_results.config_origin == "literal"
        assert max_results.default is None  # optional

        # queries is wired (derived from somewhere)
        queries = next((p for p in tool.parameters if p.name == "queries"), None)
        assert queries is not None
        assert queries.config_origin == "wired"

        # proposable_params should only include max_results_per_query
        assert len(tool.proposable_params) == 1
        assert tool.proposable_params[0].name == "max_results_per_query"

    def test_compose_timeline_post_no_output_model(self) -> None:
        """compose_timeline_post has no OUTPUT_MODEL and no writes (legacy leaf, info-only)."""
        catalog = get_tool_catalog()
        tool = catalog.get("llm.compose_timeline_post")
        assert tool is not None
        assert tool.output_model is None
        assert tool.writes is None
        assert tool.reads is None

    def test_compose_timeline_post_legacy_soul_fields(self) -> None:
        """compose_timeline_post: the four soul fields are literal (legacy-leaf-only)."""
        catalog = get_tool_catalog()
        tool = catalog.get("llm.compose_timeline_post")
        assert tool is not None

        soul_fields = {
            "account_posting_prompt",
            "account_personality",
            "contrast_patterns",
            "punctuation_rules",
        }
        for param in tool.parameters:
            if param.name in soul_fields:
                assert param.config_origin == "literal", f"{param.name} should be literal"

        # Verify they appear in proposable_params
        proposable_names = {p.name for p in tool.proposable_params}
        assert soul_fields <= proposable_names

    def test_no_injected_params_on_compose_timeline_post(self) -> None:
        """compose_timeline_post takes no injected deps."""
        catalog = get_tool_catalog()
        tool = catalog.get("llm.compose_timeline_post")
        assert tool is not None
        assert len(tool.injected_params) == 0

    def test_reference_pattern_summary_dynamic_writes(self) -> None:
        """reference_pattern_summary has dynamic writes due to store_key resolution."""
        catalog = get_tool_catalog()
        tool = catalog.get("llm.reference_pattern_summary")
        assert tool is not None
        assert tool.writes is None
        assert tool.reads is None

    def test_all_literal_params_are_correct_set(self) -> None:
        """Guard: only top_n, max_results_per_query, and four soul fields are literal."""
        catalog = get_tool_catalog()
        all_literal = set()
        for tool in catalog.all():
            for param in tool.proposable_params:
                all_literal.add((tool.tool_id, param.name))

        expected_literal = {
            ("deterministic.reference_rank", "top_n"),
            ("data.search_fetch", "max_results_per_query"),
            ("llm.compose_timeline_post", "account_posting_prompt"),
            ("llm.compose_timeline_post", "account_personality"),
            ("llm.compose_timeline_post", "contrast_patterns"),
            ("llm.compose_timeline_post", "punctuation_rules"),
        }
        assert all_literal == expected_literal

    def test_all_config_schema_entries(self) -> None:
        """config_schema should be empty except for reference_rank, search_fetch, compose_timeline_post."""
        catalog = get_tool_catalog()

        # reference_rank: top_n
        ref_rank = catalog.get("deterministic.reference_rank")
        assert len(ref_rank.config_schema) == 1  # type: ignore

        # search_fetch: max_results_per_query
        search = catalog.get("data.search_fetch")
        assert len(search.config_schema) == 1  # type: ignore

        # compose_timeline_post: 4 soul fields
        compose = catalog.get("llm.compose_timeline_post")
        assert len(compose.config_schema) == 4  # type: ignore

        # All others: empty
        for tool in catalog.all():
            if tool.tool_id not in {
                "deterministic.reference_rank",
                "data.search_fetch",
                "llm.compose_timeline_post",
            }:
                assert len(tool.config_schema) == 0


class TestConfigTypeMapping:
    """Test the _config_type annotation→type mapping."""

    def test_config_type_int(self) -> None:
        """int and int | None map to 'int'."""
        assert config_type("int") == "int"
        assert config_type("int | None") == "int"
        assert config_type("int|None") == "int"

    def test_config_type_float(self) -> None:
        """float and float | None map to 'float'."""
        assert config_type("float") == "float"
        assert config_type("float | None") == "float"

    def test_config_type_bool(self) -> None:
        """bool maps to 'bool'."""
        assert config_type("bool") == "bool"

    def test_config_type_list_str(self) -> None:
        """list[str] maps to 'list[str]'."""
        assert config_type("list[str]") == "list[str]"
        assert config_type("list[str] | None") == "list[str]"

    def test_config_type_list_and_dict(self) -> None:
        """Other list and dict types map to 'dict'."""
        assert config_type("list") == "dict"
        assert config_type("list[dict[str, Any]]") == "dict"
        assert config_type("dict") == "dict"

    def test_config_type_default_str(self) -> None:
        """Unrecognized types default to 'str'."""
        assert config_type("str") == "str"
        assert config_type("TickDataService") == "str"
        assert config_type("GatheredTweet") == "str"


class TestToolCatalogHashing:
    """Test the tool catalog hash stability and sensitivity."""

    def test_tool_catalog_hash_stable(self) -> None:
        """Hash is stable across two calls."""
        hash1 = tool_catalog_hash()
        hash2 = tool_catalog_hash()
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest

    def test_tool_catalog_hash_is_hex_string(self) -> None:
        """Hash is a valid hex string."""
        h = tool_catalog_hash()
        assert all(c in "0123456789abcdef" for c in h)


class TestToolRunMapping:
    """Test the _TOOL_RUN mapping."""

    def test_run_for_returns_callable_or_none(self) -> None:
        """run_for returns a callable for unique-wrapper tools and None for shared tools."""
        catalog = get_tool_catalog()

        # Unique-wrapper tools should return callables
        assert callable(catalog.run_for("data.account_profile"))
        assert callable(catalog.run_for("data.search_fetch"))
        assert callable(catalog.run_for("data.own_posts_fetch"))

        # Shared tools should return None (compiler resolves per-step)
        assert catalog.run_for("deterministic.reference_rank") is None
        assert catalog.run_for("llm.reference_pattern_summary") is None

        # Legacy informational tool should return None
        assert catalog.run_for("llm.compose_timeline_post") is None

        # Unknown tool should return None
        assert catalog.run_for("nope") is None


class TestToolCatalogDocument:
    """Test ToolCatalogDocument model properties."""

    def test_injected_params_property(self) -> None:
        """injected_params property filters to kind=='injected'."""
        doc = ToolCatalogDocument(
            tool_id="test",
            parameters=[
                ToolParameter(name="injected1", kind="injected", config_origin="injected"),
                ToolParameter(name="config1", kind="config", config_origin="literal"),
                ToolParameter(name="injected2", kind="injected", config_origin="injected"),
            ],
        )
        assert len(doc.injected_params) == 2
        assert all(p.kind == "injected" for p in doc.injected_params)

    def test_proposable_params_property(self) -> None:
        """proposable_params property filters to config_origin=='literal'."""
        doc = ToolCatalogDocument(
            tool_id="test",
            parameters=[
                ToolParameter(name="literal1", kind="config", config_origin="literal"),
                ToolParameter(name="wired1", kind="config", config_origin="wired"),
                ToolParameter(name="literal2", kind="config", config_origin="literal"),
            ],
        )
        assert len(doc.proposable_params) == 2
        assert all(p.config_origin == "literal" for p in doc.proposable_params)

    def test_config_schema_property(self) -> None:
        """config_schema derives ConfigField from proposable_params with correct types."""
        doc = ToolCatalogDocument(
            tool_id="test",
            parameters=[
                ToolParameter(
                    name="top_n", kind="config", config_origin="literal", annotation="int", required=False
                ),
                ToolParameter(
                    name="name",
                    kind="config",
                    config_origin="literal",
                    annotation="str",
                    required=True,
                ),
            ],
        )
        schema = doc.config_schema
        assert len(schema) == 2

        top_n_field = next((f for f in schema if f.name == "top_n"), None)
        assert top_n_field is not None
        assert top_n_field.type == "int"
        assert not top_n_field.required

        name_field = next((f for f in schema if f.name == "name"), None)
        assert name_field is not None
        assert name_field.type == "str"
        assert name_field.required
