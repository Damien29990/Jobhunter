"""LangGraph StateGraph for the Jobhunter pipeline.

Defines the cyclic graph topology: Milo → Rex → Dana → Leo ↔ Typst → Clara.
Nodes wrap existing agent logic without rewriting agent internals.
Conditional edges handle score gates, verdict gates, and Typst compile retry.

# Ref: workspace rule — deterministic logic separation; LangGraph for flow control.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from activity_logger import log_activity, log_system  # noqa: E402
from llm_usage import finalize_usage, reset_usage  # noqa: E402

# LangGraph imports (installed in requirements.txt)
try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

from talent_scout_agent import (  # noqa: E402
    DEFAULT_DB_PATH,
    PROJECT_ROOT,
    DEFAULT_PROFILE_PATH,
    JobDBManager,
    now_hk_iso,
)
from pipeline_state import TokenMetrics  # noqa: E402

_VALIDATORS_DIR = Path(__file__).resolve().parent.parent / "validators"
if str(_VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS_DIR))
from pipeline_gates import should_continue_after_dana, should_continue_after_rex  # noqa: E402

MAX_TYPST_RETRIES = 3


def _presence_node(agent_key: str):
    """Mark dashboard WORKING for the whole LangGraph node."""

    def deco(fn):
        def wrapped(state: dict) -> dict:
            from run_presence import mark_idle, mark_working

            mark_working(agent_key, f"LangGraph: {agent_key}_node")
            failed = True
            try:
                out = fn(state)
                failed = False
                return out
            finally:
                mark_idle(agent_key, failed=failed)

        wrapped.__name__ = fn.__name__
        wrapped.__doc__ = fn.__doc__
        return wrapped

    return deco


def _record_metrics(
    node_name: str,
    start: float,
    success: bool,
    error: str = "",
    usage: Optional[dict] = None,
) -> TokenMetrics:
    """Record telemetry for a node execution, including LLM tokens."""
    snap = usage or {}
    metrics = TokenMetrics(
        node_name=node_name,
        latency_ms=int((time.time() - start) * 1000),
        success=success,
        error=error or None,
        prompt_tokens=int(snap.get("prompt_tokens") or 0),
        completion_tokens=int(snap.get("completion_tokens") or 0),
    )
    log_activity(
        "SYSTEM",
        f"[telemetry] {node_name}: {metrics.latency_ms}ms "
        f"tokens={metrics.prompt_tokens + metrics.completion_tokens} success={success}",
    )
    return metrics


def _notify_agent(agent_name: str, emoji: str, summary: str, details: list = None,
                   metrics: dict = None, errors: list = None):
    """Send Telegram notification after an agent node completes.

    # Ref: Each notification includes token usage metrics.
    """
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
        from telegram_notifier import send_agent_update
        send_agent_update(agent_name, emoji, summary, details, metrics, errors)
    except ImportError:
        pass  # telegram_notifier not available — skip gracefully
    except Exception:
        pass  # never let notification crash the pipeline


# ---------------------------------------------------------------------------
# Node functions — each wraps existing agent logic
# ---------------------------------------------------------------------------

@_presence_node("milo")
def milo_node(state: dict) -> dict:
    """Agent 0 — Exploratory Summarizer. Extracts PAC from CV + chat.

    # Ref: Milo does NOT gate. Milo expands Rex's search horizon.
    """
    start = time.time()
    reset_usage("Milo")
    log_system("LangGraph: milo_node started", level="START")

    from milo_intake import MiloIntakeAgent

    profile_path = Path(state.get("profile_path") or str(DEFAULT_PROFILE_PATH))
    agent = MiloIntakeAgent(profile_path=profile_path)
    pac = agent.generate_pac()

    if pac:
        state["acceptance_context"] = pac.model_dump()
        state["milo_summary"] = pac.executive_narrative
        state["milo_readme_path"] = str(agent.readme_path)
        state["profile"] = agent.profile
        m = _record_metrics("milo", start, True, usage=finalize_usage("Milo"))
        state["node_metrics"]["milo"] = m.model_dump()
        log_activity("Milo", f"PAC ready: {len(pac.core_transferable_skills)} skills, "
                     f"{len(pac.target_industries)} industries")
        _notify_agent("Milo", "🤖", "PAC refreshed",
                       [f"Transferable skills: {len(pac.core_transferable_skills)}",
                        f"Target industries: {len(pac.target_industries)}",
                        f"Role archetypes: {len(pac.role_archetypes)}",
                        f"README: {agent.readme_path.name}"],
                       metrics=m.model_dump())
    else:
        state["node_metrics"]["milo"] = _record_metrics(
            "milo", start, False, "PAC extraction failed", usage=finalize_usage("Milo")
        ).model_dump()
        state["errors"].append("Milo: PAC extraction failed")
        # Continue with empty PAC — Rex still runs with default behavior
        state["acceptance_context"] = None

    return state


@_presence_node("rex")
def rex_node(state: dict) -> dict:
    """Agent 1 — Rex scanner. Broad cross-domain search using PAC as soft guidance.

    # Ref: Rex broadens search based on Milo's PAC, does NOT hard-filter.
    """
    start = time.time()
    reset_usage("Rex")
    log_system("LangGraph: rex_node started", level="START")

    from talent_scout_agent_2 import TalentScoutAgent
    from env_keys import deepseek_api_key, tavily_api_key

    tavily_key = tavily_api_key()
    deepseek_key = deepseek_api_key()
    if not tavily_key or not deepseek_key:
        state["errors"].append("Rex: missing API keys")
        state["node_metrics"]["rex"] = _record_metrics(
            "rex", start, False, "missing keys", usage=finalize_usage("Rex")
        ).model_dump()
        return state

    agent = TalentScoutAgent(tavily_api_key=tavily_key, deepseek_api_key=deepseek_key)

    from milo_intake import MiloIntakeAgent
    profile_path = Path(state.get("profile_path") or str(DEFAULT_PROFILE_PATH))
    milo = MiloIntakeAgent(profile_path=profile_path)
    milo.sync_compress_if_new_chat(source="rex")
    if milo.profile:
        state["profile"] = milo.profile
        if milo.profile.get("acceptance_context"):
            state["acceptance_context"] = milo.profile["acceptance_context"]

    # Feed PAC into Rex as soft guidance (broaden, not filter)
    pac_dict = state.get("acceptance_context")
    user_profile = state.get("profile", {})

    # If PAC exists, inject its narrative + skills into the profile for Rex
    if pac_dict:
        user_profile.setdefault("acceptance_context", pac_dict)
        narrative = pac_dict.get("executive_narrative", "")
        if narrative:
            log_activity("Rex", f"Using Milo narrative for horizon expansion: {narrative[:80]}...")

    try:
        count = agent.run_pipeline(
            search_keywords=state.get("query", ""),
            user_profile=user_profile,
            min_score=75,
            profile_path=Path(state.get("profile_path") or str(DEFAULT_PROFILE_PATH)),
        )
    except Exception as exc:
        state["errors"].append(f"Rex: {exc}")
        m = _record_metrics("rex", start, False, str(exc), usage=finalize_usage("Rex"))
        state["node_metrics"]["rex"] = m.model_dump()
        log_activity("Rex", f"Scan crashed: {exc}", level="ERROR")
        try:
            from telegram_notifier import send_error
            send_error("Rex", str(exc)[:500])
        except Exception:
            pass
        _notify_agent("Rex", "🔍", "scan failed", errors=[str(exc)[:200]], metrics=m.model_dump())
        return state
    state["jobs_found"] = [{"count": count}]
    m = _record_metrics("rex", start, True, usage=finalize_usage("Rex"))
    state["node_metrics"]["rex"] = m.model_dump()
    log_activity("Rex", f"Scan complete: {count} jobs found")
    _notify_agent("Rex", "🔍", f"{count} new jobs found",
                   metrics=m.model_dump())
    return state


@_presence_node("dana")
def dana_node(state: dict) -> dict:
    """Agent 2 — Dana researcher. Nuanced fit assessment + background check."""
    start = time.time()
    reset_usage("Dana")
    log_system("LangGraph: dana_node started", level="START")

    from due_diligence_agent import DueDiligenceAgent
    from env_keys import deepseek_api_key, tavily_api_key

    tavily_key = tavily_api_key()
    deepseek_key = deepseek_api_key()
    backend = os.environ.get("DUE_DILIGENCE_BACKEND", "tavily" if tavily_key else "official")

    agent = DueDiligenceAgent(
        deepseek_api_key=deepseek_key,
        tavily_api_key=tavily_key or None,
        backend=backend,
    )
    try:
        count = agent.run_pipeline(min_score=80, force_refresh=False)
    except Exception as exc:
        log_activity("Dana", f"Research crashed: {exc}", level="ERROR")
        state["errors"].append(f"Dana: {exc}")
        m = _record_metrics("dana", start, False, str(exc), usage=finalize_usage("Dana"))
        state["node_metrics"]["dana"] = m.model_dump()
        state["dossiers"] = [{"count": 0}]
        try:
            from telegram_notifier import send_error
            send_error("Dana", str(exc)[:500])
        except Exception:
            pass
        _notify_agent("Dana", "📋", "research failed", errors=[str(exc)[:200]], metrics=m.model_dump())
        return state
    state["dossiers"] = [{"count": count}]
    m = _record_metrics("dana", start, True, usage=finalize_usage("Dana"))
    state["node_metrics"]["dana"] = m.model_dump()
    log_activity("Dana", f"Research complete: {count} dossiers")
    _notify_agent("Dana", "📋", f"{count} dossiers written",
                   metrics=m.model_dump())
    return state


@_presence_node("leo")
def leo_node(state: dict) -> dict:
    """Agent 3 — Leo generator. Tailors CV and renders Typst. Cyclic retry on compile error."""
    start = time.time()
    reset_usage("Leo")
    log_system("LangGraph: leo_node started", level="START")

    from cv_generator_agent import CVGeneratorAgent
    from env_keys import deepseek_api_key

    deepseek_key = deepseek_api_key()
    agent = CVGeneratorAgent(deepseek_api_key=deepseek_key)

    # If this is a retry, pass the compile error as additional context
    compile_error = state.get("typst_compile_error")
    retry_count = state.get("typst_retry_count", 0)

    if compile_error and retry_count > 0:
        log_activity("Leo", f"Retry #{retry_count} with compile error feedback", level="WARN")

    count = agent.run_pipeline(min_score=80)
    state["cv_results"] = [{"count": count, "retries": retry_count}]
    state["typst_compile_error"] = None  # reset for next job
    m = _record_metrics("leo", start, True, usage=finalize_usage("Leo"))
    state["node_metrics"]["leo"] = m.model_dump()
    log_activity("Leo", f"CV generation complete: {count} CVs (retries: {retry_count})")
    _notify_agent("Leo", "📄", f"{count} CVs generated (retries: {retry_count})",
                   metrics=m.model_dump())
    return state


@_presence_node("clara")
def clara_node(state: dict) -> dict:
    """Agent 4 — Clara auditor. Application readiness + checklist export."""
    start = time.time()
    reset_usage("Clara")
    log_system("LangGraph: clara_node started", level="START")

    from cert_matcher_agent import CertMatcherAgent
    from env_keys import deepseek_api_key

    deepseek_key = deepseek_api_key()
    agent = CertMatcherAgent(deepseek_api_key=deepseek_key)
    count = agent.run_pipeline(min_score=80)
    state["checklist_results"] = [{"count": count}]
    m = _record_metrics("clara", start, True, usage=finalize_usage("Clara"))
    state["node_metrics"]["clara"] = m.model_dump()
    log_activity("Clara", f"Audit complete: {count} checklists")
    _notify_agent("Clara", "✅", f"{count} applications ready",
                   metrics=m.model_dump())
    return state


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def after_rex(state: dict) -> str:
    """Route after Rex: Dana if this scan stored jobs or DB already has a queue.

    High-score jobs from earlier scans must not be skipped just because Rex
    found 0 new URLs this run.
    # Ref: pipeline_gates.should_continue_after_rex
    """
    jobs = state.get("jobs_found", [])
    new_count = jobs[0].get("count", 0) if jobs else 0
    pending = 0
    try:
        db = JobDBManager(db_path=DEFAULT_DB_PATH)
        pending = len(
            db.list_companies_pending_diligence(min_score=80, include_existing=True)
        )
    except Exception as exc:
        log_activity("Rex", f"Pending-queue check failed: {exc}", level="WARN")
    if should_continue_after_rex(int(new_count or 0), pending):
        return "dana"
    return "end"


def after_dana(state: dict) -> str:
    """Route after Dana: Leo if this run wrote dossiers or PROCEED already exists."""
    dossiers = state.get("dossiers", [])
    written = dossiers[0].get("count", 0) if dossiers else 0
    proceed = 0
    try:
        db = JobDBManager(db_path=DEFAULT_DB_PATH)
        row = db.db.execute(
            "SELECT COUNT(*) FROM company_dossiers "
            "WHERE UPPER(COALESCE(vetting_verdict, '')) = 'PROCEED'"
        ).fetchone()
        proceed = int(row[0] if row and row[0] is not None else 0)
    except Exception as exc:
        log_activity("Dana", f"PROCEED-queue check failed: {exc}", level="WARN")
    if should_continue_after_dana(int(written or 0), proceed):
        return "leo"
    return "end"


def after_leo(state: dict) -> str:
    """Route after Leo: if compile error and retry < max, go back to Leo; else Clara or END."""
    error = state.get("typst_compile_error")
    retries = state.get("typst_retry_count", 0)
    if error and retries < MAX_TYPST_RETRIES:
        state["typst_retry_count"] = retries + 1
        return "leo"  # cyclic self-correction
    if error:
        log_activity("Leo", f"Max retries ({MAX_TYPST_RETRIES}) reached, marking failed", level="ERROR")
        return "end"
    return "clara"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_pipeline_graph():
    """Build and compile the LangGraph StateGraph.

    # Ref: LangGraph cyclic topology — Milo → Rex → Dana → Leo ↔ Typst → Clara
    """
    if not LANGGRAPH_AVAILABLE:
        raise ImportError("langgraph is not installed. Run: pip install langgraph langchain-core")

    builder = StateGraph(dict)

    # Add nodes
    builder.add_node("milo", milo_node)
    builder.add_node("rex", rex_node)
    builder.add_node("dana", dana_node)
    builder.add_node("leo", leo_node)
    builder.add_node("clara", clara_node)

    # Set entry point
    builder.set_entry_point("milo")

    # Add edges
    builder.add_edge("milo", "rex")
    builder.add_conditional_edges("rex", after_rex, {"dana": "dana", "end": END})
    builder.add_conditional_edges("dana", after_dana, {"leo": "leo", "end": END})
    builder.add_conditional_edges("leo", after_leo, {"leo": "leo", "clara": "clara", "end": END})
    builder.add_edge("clara", END)

    # Compile with memory checkpointing
    memory = MemorySaver()
    graph = builder.compile(checkpointer=memory)
    log_system("LangGraph pipeline compiled with MemorySaver")
    return graph


def run_pipeline(
    candidate_id: str = "default",
    profile_path: str = "",
    query: str = "",
) -> dict:
    """Run the full LangGraph pipeline in-process.

    Returns the final state dict with all results and telemetry.
    """
    load_dotenv(PROJECT_ROOT / ".env")

    if not LANGGRAPH_AVAILABLE:
        raise ImportError("langgraph is not installed")

    graph = build_pipeline_graph()
    initial_state = {
        "candidate_id": candidate_id,
        "profile_path": profile_path or str(DEFAULT_PROFILE_PATH),
        "profile": {},
        "acceptance_context": None,
        "milo_summary": None,
        "milo_readme_path": "",
        "chat_history": [],
        "jobs_found": [],
        "dossiers": [],
        "cv_results": [],
        "checklist_results": [],
        "current_job_index": 0,
        "typst_retry_count": 0,
        "typst_compile_error": None,
        "node_metrics": {},
        "errors": [],
        "query": query,
    }

    log_system("LangGraph pipeline run started", level="START")
    try:
        final_state = graph.invoke(
            initial_state, {"configurable": {"thread_id": candidate_id}}
        )
    except Exception as exc:
        log_system(f"LangGraph pipeline crashed: {exc}", level="ERROR")
        raise
    log_system("LangGraph pipeline run complete", level="EXIT")

    # Send pipeline summary to Telegram with total token usage
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
        from telegram_notifier import send_pipeline_summary
        jobs = len(final_state.get("jobs_found", []))
        dossiers = len(final_state.get("dossiers", []))
        cvs = len(final_state.get("cv_results", []))
        checklists = len(final_state.get("checklist_results", []))
        node_metrics = final_state.get("node_metrics", {})
        total_tokens = sum(
            m.get("prompt_tokens", 0) + m.get("completion_tokens", 0)
            for m in node_metrics.values() if isinstance(m, dict)
        )
        total_latency = sum(
            m.get("latency_ms", 0) for m in node_metrics.values() if isinstance(m, dict)
        )
        send_pipeline_summary(
            jobs_found=jobs, dossiers=dossiers, cv_generated=cvs,
            application_ready=checklists, total_tokens=total_tokens,
            total_latency_ms=total_latency, errors=final_state.get("errors"),
        )
    except Exception:
        pass  # never let notification crash the pipeline

    return final_state
