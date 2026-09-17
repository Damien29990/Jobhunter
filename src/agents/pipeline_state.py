"""LangGraph state schema for the Jobhunter pipeline.

Defines ProfileAcceptanceContext (PAC), TokenMetrics, and JobhunterState.
PAC replaces the old JobAcceptanceCriteria — Milo acts as an Exploratory
Summarizer (soft guidance), NOT a hard gatekeeper. Rex uses PAC to broaden
cross-domain search; Dana handles nuanced fit assessment.

# Ref: workspace rule — Pydantic v2, 禁用 Any; deterministic logic separation.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# 1. ProfileAcceptanceContext (PAC) — Milo's output, Rex's soft guidance
# ---------------------------------------------------------------------------

class ProfileAcceptanceContext(BaseModel):
    """Candidate's exploration spectrum and transferable skill anchors.

    Milo extracts this from the CV + chatbot interaction. It is NOT a hard
    filter — Rex uses it to BROADEN search across related industries and
    diverse role archetypes. Only absolute_deal_breakers act as a minimal
    text-match check.

    # Ref: Milo design — Exploratory Summarizer, not Gatekeeper
    """

    # 1. Core transferable skills (Rex uses these as cross-domain search anchors)
    core_transferable_skills: list[str] = Field(
        default_factory=list,
        description="What the candidate CAN do — anchors for cross-domain search",
    )

    # 2. Exploration spectrum (industries and role types to search broadly)
    target_industries: list[str] = Field(
        default_factory=list,
        description="Where to explore broadly (e.g. IoT, PropTech, FinTech, automation)",
    )
    role_archetypes: list[str] = Field(
        default_factory=list,
        description="Diverse role types to search (not just current title)",
    )

    # 3. True bottom line (only absolute, non-negotiable boundaries)
    absolute_deal_breakers: list[str] = Field(
        default_factory=list,
        description="Only true non-negotiables (minimal, not a blacklist)",
    )

    # 4. Milo's narrative summary for downstream agents
    executive_narrative: str = Field(
        default="",
        description="Concise candidate story + potential plasticity for downstream agents",
    )

    @model_validator(mode="after")
    def strip_whitespace(self) -> "ProfileAcceptanceContext":
        self.core_transferable_skills = [
            s.strip() for s in self.core_transferable_skills if s and s.strip()
        ]
        self.target_industries = [
            s.strip() for s in self.target_industries if s and s.strip()
        ]
        self.role_archetypes = [
            s.strip() for s in self.role_archetypes if s and s.strip()
        ]
        self.absolute_deal_breakers = [
            s.strip() for s in self.absolute_deal_breakers if s and s.strip()
        ]
        self.executive_narrative = self.executive_narrative.strip()
        return self


# ---------------------------------------------------------------------------
# 2. TokenMetrics — telemetry at each LangGraph node transition
# ---------------------------------------------------------------------------

class TokenMetrics(BaseModel):
    """LLM token usage and latency for a single node execution.

    # Ref: LangGraph telemetry harness — per-node observability
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    node_name: str = ""
    success: bool = True
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# 3. JobhunterState — centralized state flowing through all LangGraph nodes
# ---------------------------------------------------------------------------

class JobhunterState(BaseModel):
    """Centralized state object passed between LangGraph nodes.

    Replaces the implicit SQLite-column-only state with an explicit, typed
    in-memory state that LangGraph checkpoints. DB writes still happen (agents
    own persistence), but the graph state carries context between nodes.

    # Ref: LangGraph StateGraph — centralized state machine
    """

    # Candidate context
    candidate_id: str = "default"
    profile_path: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)
    acceptance_context: Optional[ProfileAcceptanceContext] = None
    milo_summary: Optional[str] = None
    milo_readme_path: str = ""
    chat_history: list[dict[str, str]] = Field(default_factory=list)

    # Pipeline results
    jobs_found: list[dict[str, Any]] = Field(default_factory=list)
    dossiers: list[dict[str, Any]] = Field(default_factory=list)
    cv_results: list[dict[str, Any]] = Field(default_factory=list)
    checklist_results: list[dict[str, Any]] = Field(default_factory=list)

    # Cyclic Typst retry state
    current_job_index: int = 0
    typst_retry_count: int = 0
    typst_compile_error: Optional[str] = None

    # Telemetry
    node_metrics: dict[str, Any] = Field(default_factory=dict)

    # Error tracking
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 4. Convenience: TypedDict for LangGraph (langgraph requires TypedDict)
# ---------------------------------------------------------------------------

# LangGraph's StateGraph works with TypedDict, not Pydantic BaseModel.
# We define a TypedDict that mirrors JobhunterState for the graph, and
# provide helpers to convert between the two.

from typing import TypedDict


class JobhunterStateDict(TypedDict, total=False):
    """TypedDict for LangGraph StateGraph — mirrors JobhunterState fields.

    # Ref: langgraph.graph.StateGraph requires TypedDict for state schema
    """
    candidate_id: str
    profile_path: str
    profile: dict
    acceptance_context: Optional[ProfileAcceptanceContext]
    milo_summary: Optional[str]
    milo_readme_path: str
    chat_history: list
    jobs_found: list
    dossiers: list
    cv_results: list
    checklist_results: list
    current_job_index: int
    typst_retry_count: int
    typst_compile_error: Optional[str]
    node_metrics: dict
    errors: list


def state_to_dict(state: JobhunterState) -> JobhunterStateDict:
    """Convert JobhunterState (Pydantic) to JobhunterStateDict (TypedDict)."""
    return state.model_dump()


def dict_to_state(d: JobhunterStateDict) -> JobhunterState:
    """Convert JobhunterStateDict (TypedDict) to JobhunterState (Pydantic)."""
    return JobhunterState.model_validate(d)
