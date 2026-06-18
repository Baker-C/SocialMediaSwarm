"""Tool catalog Pydantic models — introspection of the six SENSE tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ParamKind = Literal["injected", "config"]
ConfigOrigin = Literal["injected", "runtime", "wired", "literal"]
# The closed type vocabulary doc 05's _typecheck switches on (validator §5.1).
ConfigType = Literal["str", "int", "float", "bool", "list[str]", "dict"]


class ToolParameter(BaseModel):
    """One parameter in a tool's run() signature (after ctx and deps are skipped)."""

    name: str
    annotation: str = ""  # raw annotation STRING (e.g., 'int | None', 'list[dict[str, Any]]')
    required: bool = False
    default: Any = None  # JSON-safe default, or None
    kind: ParamKind  # "injected" => live service; "config" => everything else
    config_origin: ConfigOrigin  # only "literal" is spec-proposable; others are engine/context/wired


class ConfigField(BaseModel):
    """The typed schema entry doc 05's validator type-checks a spec config value against.

    Derived from a proposable (literal-origin) ToolParameter via config_schema.
    """

    name: str
    type: ConfigType
    required: bool = False


class ToolCatalogDocument(BaseModel):
    """Introspected metadata for one catalog tool."""

    tool_id: str
    kind: str = ""  # "data" | "deterministic" | "llm"
    purpose: str = ""
    source: str | None = None  # TOOL_SOURCE (data tools only)
    prompt_stem: str | None = None  # PROMPT_STEM (llm tools only)
    output_model: str | None = None  # OUTPUT_MODEL.__name__ or None (compose => None)
    reads: list[str] | None = None  # fixed reads (ACT tools), or None when dynamic
    writes: list[str] | None = None  # fixed writes, or None when dynamic (store_key)
    parameters: list[ToolParameter] = Field(default_factory=list)
    # CC-2: NO invariant_tool field. Doc 05's R7 detects the guardian/publish invariants
    # from the static `writes` artifacts (writes ⊇ safety_verdict / published_post), not a flag.

    @property
    def injected_params(self) -> list[ToolParameter]:
        """Live engine-injected dependencies (never spec-proposable)."""
        return [p for p in self.parameters if p.kind == "injected"]

    @property
    def proposable_params(self) -> list[ToolParameter]:
        """LLM-tunable config parameters (config_origin == "literal" only)."""
        return [p for p in self.parameters if p.config_origin == "literal"]

    @property
    def config_schema(self) -> list[ConfigField]:
        """The proposable surface as a TYPED schema for doc 05's type-checker.

        One ConfigField per literal-origin param, with JSON type derived from annotation.
        """
        return [
            ConfigField(name=p.name, type=config_type(p.annotation), required=p.required)
            for p in self.proposable_params
        ]


def config_type(annotation: str) -> ConfigType:
    """Map annotation string to ConfigType for type-checking.

    Annotations are raw strings (§2.1 in doc 03); unrecognized types default to "str".
    """
    a = annotation.replace(" ", "")
    if a.startswith("int") or a == "int|None":
        return "int"
    if a.startswith("float") or a == "float|None":
        return "float"
    if a.startswith("bool"):
        return "bool"
    if a.startswith("list[str]") or a == "list[str]|None":
        return "list[str]"
    if a.startswith("list") or a.startswith("dict"):
        return "dict"  # coarse; no list-of-scalar knob exists today
    return "str"
