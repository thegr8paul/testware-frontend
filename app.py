import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import requests
import streamlit as st  # Streamlit for the whole UI
import streamlit.components.v1 as components  # raw HTML/JS embeds (the "thinking" cue) + the workflow component

def _resolve_api_url() -> str:
    """Backend base URL. Precedence: API_URL env var -> [API_URL] in
    Streamlit secrets (how you set it on Streamlit Community Cloud) ->
    localhost for local dev against `make mock` / a local FastAPI."""
    if os.environ.get("API_URL"):
        return os.environ["API_URL"]
    try:
        if "API_URL" in st.secrets:
            return str(st.secrets["API_URL"])
    except Exception:  # no secrets.toml at all -- fine, fall through
        pass
    return "http://localhost:8000"


DEFAULT_API_URL = _resolve_api_url()

# Section 3's node canvas -- a bidirectional component (Drawflow, vendored).
# Returns {node, catalogue_id, ts} when a node is clicked, else None.
_WF_DIR = Path(__file__).with_name("components") / "workflow"
workflow_canvas = components.declare_component("tw_workflow", path=str(_WF_DIR))

# Search-bar facets (curated -- see facets.json "_provenance"). Loaded once.
_FACETS = json.loads(Path(__file__).with_name("facets.json").read_text())
INDUSTRY_TAXONOMY = _FACETS["industries"]
NATURE_OPTIONS = _FACETS["nature_options"]

INDUSTRY_ICON = ":material/factory:"
APPLICATION_ICON = ":material/tune:"
NATURE_ICON = ":material/science:"

# Landing headline -- one is picked at random per session (re-rolls on
# "New workflow"). Professional but with some energy.
HEADLINES = [
    "Let's twin.",
    "What are we twinning today?",
    "Describe the system. Get its twin.",
    "What do you want to model?",
    "Let's build your digital twin.",
    "What should we clone today?",
    "From description to digital twin.",
    "Point me at a system.",
    "What are we simulating today?",
    "Spin up a twin.",
]

# "Liquid glass" panel recipe. Duplicated across three documents (styles.css
# search bar, the "thinking" cue, and components/workflow/index.html) since
# each has its own <style>. Keep them visually in sync.
GLASS_PANEL_CSS = """
  border: 1px solid rgba(255, 255, 255, 0.55);
  border-radius: 16px;
  background:
    linear-gradient(150deg, rgba(255, 255, 255, 0.62), rgba(255, 255, 255, 0.28)),
    rgba(220, 225, 235, 0.30);
  -webkit-backdrop-filter: blur(18px) saturate(180%);
  backdrop-filter: blur(18px) saturate(180%);
  box-shadow:
    0 8px 30px rgba(0, 0, 0, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.65);
"""

# Workflow node types the backend emits and the canvas component styles.
WORKFLOW_NODE_TYPES = ("input", "process", "model", "decision", "merge", "output", "database")

# Loading cue: a grey shimmer sweep over the whole compact search bar. Rendered
# into `status_slot` while run_query() blocks; status_slot.empty() removes this
# <style> node so the sweep stops. No text.
_BAR_LOADING_CSS = (
    "<style>"
    "@keyframes tw-bar-sweep{0%{background-position:220% 0}100%{background-position:-220% 0}}"
    ".st-key-tw_searchbar_compact::after{content:'';position:absolute;inset:0;"
    "border-radius:inherit;pointer-events:none;z-index:6;"
    "background:linear-gradient(100deg,transparent 38%,rgba(17,17,17,0.10) 50%,transparent 62%);"
    "background-size:220% 100%;animation:tw-bar-sweep 2.5s linear infinite;}"
    "</style>"
)

# --- PAGE CONFIG -----------------------------------------------------------
st.set_page_config(page_title="Digital Twin Model Selector", layout="wide")  # wide layout gives room for tool cards side by side


def load_css():
    """Inject styles.css once. Kept in a separate file so visual tweaks are a
    save-and-reload loop with no Python change (see README)."""
    css = Path(__file__).with_name("styles.css").read_text()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


load_css()

# Fixed backend URL -- override with the API_URL env var. (Used to be a
# sidebar text input; the sidebar is now a nav rail.)
api_url = DEFAULT_API_URL.rstrip("/")

# --- STATE ---------------------------------------------------------------------
# session_state persists across the reruns that every widget interaction
# triggers. `query` is None until the first search -> that gates the whole
# results block and the landing-vs-compact layout switch.
st.session_state.setdefault("query", None)
st.session_state.setdefault("industry", "(Any)")
st.session_state.setdefault("application", "(Any)")
st.session_state.setdefault("nature", "(Any)")
st.session_state.setdefault("categories", {})
st.session_state.setdefault("focus_tool", None)  # catalogue_id of the node clicked in Section 3
st.session_state.setdefault("headline", random.choice(HEADLINES))


def _current_categories() -> dict:
    """The three picker values as structured fields -- "(Any)" dropped. Only
    ever folded into the query text and shown as chips."""
    picks = {
        "industry": st.session_state.industry,
        "application": st.session_state.application,
        "nature_of_project": st.session_state.nature,
    }
    return {k: v for k, v in picks.items() if v != "(Any)"}


def build_enhanced_query(raw_query: str, categories: dict) -> str:
    """Fold the selected dropdown tags into the query text sent to the backend.

    Each tag is optional -- an unset dropdown is stored as None in `categories`
    and skipped here. With nothing selected, the raw query is returned as-is.
    The backend embeds this same string for retrieval and reuses it for
    generation, so the tags inform both.
    """
    labels = {"industry": "Industry", "application": "Application", "nature_of_project": "Nature of project"}
    parts = [f"{labels.get(key, key)}: {value}" for key, value in categories.items() if value]
    if not parts:
        return raw_query
    return f"{raw_query}\n\nContext — " + "; ".join(parts)


SAVED_WORKFLOWS_PATH = Path(__file__).with_name("saved_workflows.json")


def _save_workflow(result: dict | None) -> bool:
    """Append the on-screen result (query + categories + workflow + tools +
    description) to saved_workflows.json. No-op if there is no workflow yet."""
    if not result or not (result.get("workflow") or {}).get("nodes"):
        return False
    try:
        existing = json.loads(SAVED_WORKFLOWS_PATH.read_text()) if SAVED_WORKFLOWS_PATH.exists() else []
        if not isinstance(existing, list):
            existing = []
    except (json.JSONDecodeError, OSError):
        existing = []
    existing.append({**result, "saved_at": datetime.now(timezone.utc).isoformat()})
    SAVED_WORKFLOWS_PATH.write_text(json.dumps(existing, indent=2))
    return True


def run_query(query: str, categories: dict):
    """
    The selected `categories` are folded into the query text via
    build_enhanced_query() before it's sent -- the API has no separate
    categories field.
    """
    try:
        resp = requests.post(
            f"{api_url}/query",
            json={"query": build_enhanced_query(query, categories)},
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        description = data["answer"]
        tools = data["tools"]
        workflow = data.get("workflow") or {"nodes": [], "edges": []}
    except requests.RequestException as exc:
        description = f"Couldn't reach the RAG API at {api_url} — is it running? ({exc})"
        tools = []
        workflow = {"nodes": [], "edges": []}

    return description, tools, workflow


def _pop_label(field_name: str, value: str) -> str:
    """Popover label: the picked value, or the field name when unset -- so
    active filters are visible on the closed bar."""
    return field_name if value == "(Any)" else value


def render_search_bar(mode: str):
    """The one search bar. `mode` is "hero" (big, centered -- landing) or
    "compact" (slim, top -- results view). Three in-bar pickers: Industry,
    Application (cascades within Industry), Nature of project -- all from
    facets.json. Returns the status slot the caller uses to trigger the
    loading shimmer while run_query() blocks.
    """
    # In the results view, show the executed query inside the input field
    # (seed the widget state once if a fresh session lost it).
    if mode == "compact" and "query_input" not in st.session_state and st.session_state.get("query"):
        st.session_state.query_input = st.session_state.query

    with st.container(key=f"tw_searchbar_{mode}"):
        # Row 1: the text field. The Search icon-button is rendered right
        # after it and then CSS-positioned to sit *inside* the field on the
        # right (Streamlit can't put a widget inside st.text_input directly).
        query_text = st.text_input(
            "Describe your digital twin problem",  # kept for a11y; hidden below
            key="query_input",
            label_visibility="collapsed",
            placeholder="e.g. Digital twin for a hydraulic press with predictive maintenance",
        )
        submitted = st.button(
            "",
            icon=":material/search:",
            type="primary",
            key="tw_search_btn",
            help="Search",
        )

        # Row 2: Industry / Application / Nature-of-project icon popovers, plus the
        # empty area the caller uses to trigger the loading shimmer
        # while run_query() blocks.
        btn_cols = st.columns([1, 1, 1, 7], gap="small", vertical_alignment="center")

        with btn_cols[0]:
            with st.popover(
                "",
                icon=INDUSTRY_ICON,
                use_container_width=True,
                help=_pop_label("Industry", st.session_state.industry),
            ):
                st.selectbox(
                    "Industry",
                    options=["(Any)"] + list(INDUSTRY_TAXONOMY.keys()),
                    key="industry",
                )

        with btn_cols[1]:
            # Application options cascade from the picked Industry; "(Any)"
            # -> the de-duplicated union across all industries.
            if st.session_state.industry == "(Any)":
                application_options = ["(Any)"] + sorted(
                    {app for apps in INDUSTRY_TAXONOMY.values() for app in apps}
                )
            else:
                application_options = ["(Any)"] + INDUSTRY_TAXONOMY[st.session_state.industry]
            # Drop a stale Application pick before the selectbox renders.
            if st.session_state.application not in application_options:
                st.session_state.application = "(Any)"
            with st.popover(
                "",
                icon=APPLICATION_ICON,
                use_container_width=True,
                help=_pop_label("Application", st.session_state.application),
            ):
                st.selectbox("Application", options=application_options, key="application")

        with btn_cols[2]:
            with st.popover(
                "",
                icon=NATURE_ICON,
                use_container_width=True,
                help=_pop_label("Nature of project", st.session_state.nature),
            ):
                st.selectbox(
                    "Nature of project",
                    options=["(Any)"] + list(NATURE_OPTIONS),
                    key="nature",
                )

        status_slot = btn_cols[3].empty()

    if submitted and query_text.strip():
        st.session_state.query = query_text
        st.session_state.categories = _current_categories()
        st.rerun()

    return status_slot


# --- SIDEBAR (nav rail) ---------------------------------------------------
with st.sidebar:
    if st.button(
        "New workflow",
        icon=":material/add:",
        key="sb_new_workflow",
        use_container_width=True,
        help="Save the current workflow and start a new one",
    ):
        # Save what's on screen, then reset to a clean landing (pop every
        # stored widget value -- setdefault() re-seeds next run).
        if _save_workflow(st.session_state.get("last_result")):
            st.toast("Workflow saved", icon=":material/check:")
        for _k in ("query", "query_input", "industry", "application", "nature",
                   "categories", "focus_tool", "last_result", "results", "headline"):
            st.session_state.pop(_k, None)
        st.rerun()

    # Placeholders -- no function yet.
    st.button("Saved workflows", icon=":material/bookmark:", key="sb_saved",
              use_container_width=True, disabled=True)
    st.button("Settings", icon=":material/settings:", key="sb_settings",
              use_container_width=True, disabled=True)
    st.button("Help", icon=":material/help:", key="sb_help",
              use_container_width=True, disabled=True)


# --- LAYOUT -----------------------------------------------------------------
if st.session_state.query:
    # Results view: slim bar at the top, everything below it.
    status_slot = render_search_bar("compact")  # the executed query shows in its input field

    # applied category filters as chips, for transparency
    applied = [f"{k.replace('_', ' ').title()}: {v}" for k, v in st.session_state.categories.items() if v]
    if applied:
        chips = "".join(f"<span class='tw-chip'>{a}</span>" for a in applied)
        st.markdown(f"<div class='tw-chips'>{chips}</div>", unsafe_allow_html=True)

    # Cache the fetch for the current (query, categories). Reruns triggered by
    # UI churn -- clicking a workflow node, opening a popover -- then reuse the
    # result instead of re-POSTing (which, being LLM-backed, would return a
    # different graph and rebuild the canvas, losing any dragged node positions).
    _cache_key = (st.session_state.query,
                  json.dumps(st.session_state.categories, sort_keys=True))
    _cache = st.session_state.get("results")
    if not (_cache and _cache.get("key") == _cache_key):
        with status_slot:
            st.markdown(_BAR_LOADING_CSS, unsafe_allow_html=True)  # shimmer only on a real fetch
        description, tools, workflow = run_query(
            st.session_state.query, st.session_state.categories
        )
        status_slot.empty()  # remove the <style> -> shimmer stops once results (or error) are in
        _cache = {"key": _cache_key, "description": description,
                  "tools": tools, "workflow": workflow}
        st.session_state.results = _cache

    description = _cache["description"]
    tools = _cache["tools"]
    workflow = _cache["workflow"]

    # Stash the current result so the "New workflow" button can save it.
    st.session_state.last_result = {
        "query": st.session_state.query,
        "categories": dict(st.session_state.categories),
        "description": description,
        "tools": tools,
        "workflow": workflow,
    }

    # --- SECTION: DESCRIPTION ---------------------------------------------
    st.header("Workflow Description")
    st.write(description)  # plain prose explanation of the digital twin workflow

    # --- SECTION: WORKFLOW CANVAS ---------------------------------------------
    st.header("Workflow")
    st.caption(
        "Suggested pipeline. Nodes tagged **DB** map to a catalogue entry; an "
        "accent ring marks tools also in the list below. Click a node to focus "
        "its card. Drag a node to move it; drag an output dot to an input dot to "
        "wire; click a wire then Delete (or its ×) to remove it. Drag canvas to "
        "pan, wheel to zoom."
    )
    _wf_suggested = [t["catalogue_id"] for t in tools if t.get("catalogue_id")]
    if workflow.get("nodes"):
        _sel = workflow_canvas(
            workflow=workflow, suggested=_wf_suggested, key="tw_wf", default=None
        )
        if isinstance(_sel, dict):
            if _sel.get("kind") == "edit" and _sel.get("workflow"):
                # User re-wired / moved nodes on the canvas -- make that the new
                # truth for this query. The component recognises its own echo
                # (matching heldSig) so this doesn't trigger a canvas rebuild.
                st.session_state.results["workflow"] = _sel["workflow"]
                st.session_state.last_result["workflow"] = _sel["workflow"]
            elif _sel.get("catalogue_id"):
                if st.session_state.get("focus_tool") != _sel["catalogue_id"]:
                    st.session_state.focus_tool = _sel["catalogue_id"]
                    st.rerun()
    else:
        st.caption("No workflow available for this query.")

    # --- SECTION: TOOL SUGGESTIONS ------------------------------------------
    st.header("Suggested Tools")

    if not tools:
        st.caption("No matching tools found in the catalogue for this query.")

    _focus = st.session_state.get("focus_tool")
    for tool in tools:  # loop over each ranked tool result
        focused = bool(tool.get("catalogue_id")) and tool["catalogue_id"] == _focus
        card = st.container(border=True, key="tw_focus_card") if focused else st.container(border=True)
        with card:  # bordered box makes each tool visually distinct
            if focused:
                st.caption("🔎 Selected in the workflow")
            st.subheader(tool["name"])  # tool name as subheading
            st.write(tool["rationale"])  # why this tool was suggested (explainability)

            # tag row: fidelity tier / spatial scale / temporal scale / standards,
            # each labeled so it's clear what kind of value each tag is. Real
            # catalogue entries frequently leave these null, hence the fallback.
            tag_parts = [
                f"`Fidelity: {tool['fidelity_tier'] or '—'}`",
                f"`Spatial: {tool['spatial_scale'] or '—'}`",
                f"`Temporal: {tool['temporal_scale'] or '—'}`",
            ]
            tag_parts += [f"`Standard: {s}`" for s in tool["standards"]]  # one pill per standard
            st.caption("  ·  ".join(tag_parts))

            # pricing + validation: the two numbers a lead engineer checks
            # right after "does it fit" - can I afford it, can I trust it.
            # Pricing is always model-estimated -- the catalogue has no pricing
            # field at all -- so it's captioned as such, never shown as fact.
            price = tool["pricing"]
            price_line = f"{price['currency']} {price['estimate_low']:,.0f}-{price['estimate_high']:,.0f} {price['unit']}"
            col3, col4 = st.columns(2)
            with col3:
                st.write(f"**Est. price:** {price_line}")
                st.caption("AI estimate — not sourced from the catalogue")
            with col4:
                st.write(f"**Validation:** {tool['validation_level'] or '—'}")

            with st.expander("Details", expanded=focused):  # full schema dump, collapsed by default
                st.markdown("**Inputs**")
                for i in tool["inputs"]:
                    st.write(f"- {i}")
                st.markdown("**Outputs**")
                for o in tool["outputs"]:
                    st.write(f"- {o}")
                if tool["known_fail_modes"]:  # also always model-estimated, same as pricing
                    st.markdown("**Known limitations** _(AI estimate — not sourced from the catalogue)_")
                    for f in tool["known_fail_modes"]:
                        st.write(f"- {f}")
                if tool.get("docs_url"):
                    st.markdown(f"[Reference]({tool['docs_url']})")  # traceability link
else:
    # Landing view: eyebrow + rotating headline + the one big search bar,
    # vertically & horizontally centred (styled in styles.css).
    with st.container(key="tw_landing"):
        st.markdown(
            f"<h1 class='tw-hero-title'>{st.session_state.headline}</h1>",
            unsafe_allow_html=True,
        )
        render_search_bar("hero")
