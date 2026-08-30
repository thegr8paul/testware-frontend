import os
from pathlib import Path

import requests
import streamlit as st  # Streamlit for the whole UI
import streamlit.components.v1 as components  # raw HTML/JS embeds (the "thinking" cue) + the workflow component

DEFAULT_API_URL = os.environ.get("API_URL", "http://localhost:8000")

# Section 3's node canvas -- a bidirectional component (Drawflow, vendored).
# Returns {node, catalogue_id, ts} when a node is clicked, else None.
_WF_DIR = Path(__file__).with_name("components") / "workflow"
workflow_canvas = components.declare_component("tw_workflow", path=str(_WF_DIR))

INDUSTRY_TAXONOMY = {
    "Manufacturing": ["Predictive maintenance", "Process optimisation", "Quality inspection"],
    "Energy": ["Grid simulation", "Renewable asset monitoring", "Plant performance modelling"],
    "Aerospace": ["Structural health monitoring", "Flight system simulation", "Fleet lifecycle management"],
    "Automotive": ["Vehicle dynamics simulation", "Battery/powertrain modelling", "Production line twin"],
    "Healthcare": ["Patient-specific modelling", "Medical device simulation", "Hospital operations twin"],
    "Other / not listed": ["General / unspecified"],
}
NATURE_OPTIONS = ["OEM commercial", "Private hobby", "Research", "Market analysis"]

# Monochrome Material icons for the three in-bar category pickers.
INDUSTRY_ICON = ":material/factory:"
APPLICATION_ICON = ":material/tune:"
NATURE_ICON = ":material/science:"

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

# --- PAGE CONFIG -----------------------------------------------------------
st.set_page_config(page_title="Digital Twin Model Selector", layout="wide")  # wide layout gives room for tool cards side by side


def load_css():
    """Inject styles.css once. Kept in a separate file so visual tweaks are a
    save-and-reload loop with no Python change (see README)."""
    css = Path(__file__).with_name("styles.css").read_text()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


load_css()

with st.sidebar:
    st.header("Settings")
    api_url = st.text_input(
        "RAG API URL",
        value=DEFAULT_API_URL,
        help="Points at rag/api.py — local FastAPI or a cloudflared tunnel URL.",
    ).rstrip("/")

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


def _current_categories() -> dict:
    """The three dropdown values as clean structured fields ("(Any)" -> None).
    Same shape the old `selected_categories` dict had, so build_enhanced_query()
    is unchanged."""
    return {
        "industry": None if st.session_state.industry == "(Any)" else st.session_state.industry,
        "application": None if st.session_state.application == "(Any)" else st.session_state.application,
        "nature_of_project": None if st.session_state.nature == "(Any)" else st.session_state.nature,
    }


def build_enhanced_query(raw_query: str, categories: dict) -> str:
    """Fold the selected dropdown tags into the query text sent to the backend.

    Each tag is optional -- an unset dropdown is stored as None in `categories`
    and skipped here. With nothing selected, the raw query is returned as-is.
    The backend embeds this same string for retrieval and reuses it for
    generation, so the tags inform both.
    """
    labels = {
        "industry": "Industry",
        "application": "Application",
        "nature_of_project": "Nature of project",
    }
    parts = [f"{labels[key]}: {value}" for key, value in categories.items() if value]
    if not parts:
        return raw_query
    return f"{raw_query}\n\nContext — " + "; ".join(parts)


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


def render_thinking(height: int = 44):
    """Claude-style 'thinking' cue shown while run_query() blocks.

    Rendered via components.html so its JS keeps animating in the browser
    while the Python thread is stuck on the blocking request. Self-contained
    -- no CDN. The word swaps at a random 4-15s interval; the shimmer sweep
    is pure CSS and freezes under prefers-reduced-motion.
    """
    thinking_html = """
    <style>
      .tw-think {
        font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, sans-serif;
        font-size: 0.95rem; font-weight: 600; letter-spacing: .2px;
        background: linear-gradient(90deg, #9aa0a6 0%, #9aa0a6 35%, #f5f5f5 50%, #9aa0a6 65%, #9aa0a6 100%);
        background-size: 220% 100%;
        -webkit-background-clip: text; background-clip: text;
        color: transparent;
        animation: tw-sweep 1.8s linear infinite;
      }
      @keyframes tw-sweep { 0% { background-position: 120% 0; } 100% { background-position: -120% 0; } }
      @media (prefers-reduced-motion: reduce) {
        .tw-think { animation: none; background: none; -webkit-background-clip: border-box;
                    background-clip: border-box; color: #9aa0a6; }
      }
    </style>
    <span class="tw-think" id="tw-think">Thinking</span>
    <script>
      (function () {
        const WORDS = ["Thinking", "Musing", "Analyzing catalogue", "Evaluating models",
                       "Retrieving context", "Choosing tools", "Composing answer"];
        let i = 0;
        const el = document.getElementById("tw-think");
        function tick() {
          i = (i + 1) % WORDS.length;
          if (el) el.textContent = WORDS[i];
          setTimeout(tick, 4000 + Math.random() * 11000);
        }
        setTimeout(tick, 4000 + Math.random() * 11000);
      })();
    </script>
    """
    components.html(thinking_html, height=height)


def _pop_label(field_name: str, value: str) -> str:
    """Popover label: the picked value, or the field name when unset -- so
    active filters are visible on the closed bar."""
    return field_name if value == "(Any)" else value


def render_search_bar(mode: str):
    """The one search bar. `mode` is "hero" (big, centered -- landing) or
    "compact" (slim, top -- results view). The three category dropdowns live
    inside it as icon popovers; there is no st.form, so picking an Industry
    reruns immediately and the Application list cascades live.
    """
    collapsed = mode == "compact"

    with st.container(key=f"tw_searchbar_{mode}"):
        # Row 1: the text field. The Search icon-button is rendered right
        # after it and then CSS-positioned to sit *inside* the field on the
        # right (Streamlit can't put a widget inside st.text_input directly).
        query_text = st.text_input(
            "Describe your digital twin problem",
            key="query_input",
            label_visibility="collapsed" if collapsed else "visible",
            placeholder="e.g. Digital twin for a hydraulic press with predictive maintenance",
        )
        submitted = st.button(
            "",
            icon=":material/search:",
            type="primary",
            key="tw_search_btn",
            help="Search",
        )

        # Row 2: the three category dropdowns as icon-only popovers,
        # nebeneinander directly under the bar. No text labels.
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
            # Application options depend on the selected Industry. "(Any)"
            # falls back to the de-duplicated union across all industries.
            if st.session_state.industry == "(Any)":
                application_options = ["(Any)"] + sorted(
                    {app for apps in INDUSTRY_TAXONOMY.values() for app in apps}
                )
            else:
                application_options = ["(Any)"] + INDUSTRY_TAXONOMY[st.session_state.industry]
            # If a prior Application pick is no longer valid for the new
            # Industry, drop it before the selectbox renders.
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
                help=_pop_label("Nature", st.session_state.nature),
            ):
                st.selectbox(
                    "Nature of project",
                    options=["(Any)"] + NATURE_OPTIONS,
                    key="nature",
                )

    if submitted and query_text.strip():
        st.session_state.query = query_text
        st.session_state.categories = _current_categories()
        st.rerun()


# --- LAYOUT -----------------------------------------------------------------
if st.session_state.query:
    # Results view: slim bar at the top, everything below it.
    render_search_bar("compact")
    if st.button("New search", key="tw_new_search"):
        # Reset back to a clean landing: drop the submitted query and every
        # widget's stored value (del is the supported way to reset a keyed
        # widget). setdefault() at the top re-seeds them next run.
        for _k in ("query", "query_input", "industry", "application", "nature", "categories", "focus_tool"):
            st.session_state.pop(_k, None)
        st.rerun()

    st.caption(f"Query: *{st.session_state.query}*")  # shows what was asked, italicized for visual distinction

    # applied category filters as chips, for transparency
    applied = [f"{k.replace('_', ' ').title()}: {v}" for k, v in st.session_state.categories.items() if v]
    if applied:
        chips = "".join(f"<span class='tw-chip'>{a}</span>" for a in applied)
        st.markdown(f"<div class='tw-chips'>{chips}</div>", unsafe_allow_html=True)

    thinking = st.empty()
    with thinking:
        render_thinking()  # animated cue; keeps moving in the browser while run_query() blocks
    description, tools, workflow = run_query(
        st.session_state.query, st.session_state.categories
    )  # fetch results for the current query + category selections
    thinking.empty()  # clear the cue once the answer (or error) is back

    # --- SECTION 1: DESCRIPTION ---------------------------------------------
    st.header("1. Workflow Description")  # fixed section per your spec
    st.write(description)  # plain prose explanation of the digital twin workflow

    # --- SECTION 2: TOOL SUGGESTIONS ------------------------------------------
    st.header("2. Suggested Tools")  # fixed section per your spec

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

    # --- SECTION 3: WORKFLOW CANVAS -------------------------------------------
    st.header("3. Workflow")  # fixed section per your spec
    st.caption(
        "Suggested pipeline. Nodes tagged **DB** map to a catalogue entry; a "
        "red ring marks tools in the list above. Click a node to focus its "
        "card. Drag to pan, wheel to zoom."
    )

    _wf_suggested = [t["catalogue_id"] for t in tools if t.get("catalogue_id")]
    if workflow.get("nodes"):
        _sel = workflow_canvas(
            workflow=workflow, suggested=_wf_suggested, key="tw_wf", default=None
        )
        if isinstance(_sel, dict) and _sel.get("catalogue_id"):
            if st.session_state.get("focus_tool") != _sel["catalogue_id"]:
                st.session_state.focus_tool = _sel["catalogue_id"]
                st.rerun()
    else:
        st.caption("No workflow available for this query.")
else:
    # Landing view: title + one big centered search bar, nothing else.
    st.markdown(
        "<h1 class='tw-hero-title'>Digital Twin Model Selection</h1>",
        unsafe_allow_html=True,
    )
    render_search_bar("hero")
    st.caption(
        "Optional: use the icons in the bar to narrow by industry, application, "
        "or project nature. You can also search on free text alone."
    )
