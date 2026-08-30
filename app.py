import os

import requests
import streamlit as st  # Streamlit for the whole UI
import streamlit.components.v1 as components  # needed to embed raw HTML/JS (mermaid.js) since Streamlit has no native mermaid renderer

DEFAULT_API_URL = os.environ.get("API_URL", "http://localhost:8000")

INDUSTRY_TAXONOMY = {
    "Manufacturing": ["Predictive maintenance", "Process optimisation", "Quality inspection"],
    "Energy": ["Grid simulation", "Renewable asset monitoring", "Plant performance modelling"],
    "Aerospace": ["Structural health monitoring", "Flight system simulation", "Fleet lifecycle management"],
    "Automotive": ["Vehicle dynamics simulation", "Battery/powertrain modelling", "Production line twin"],
    "Healthcare": ["Patient-specific modelling", "Medical device simulation", "Hospital operations twin"],
    "Other / not listed": ["General / unspecified"],
}
NATURE_OPTIONS = ["OEM commercial", "Private hobby", "Research", "Market analysis"]

# --- PAGE CONFIG -------------------------------------------------------------
st.set_page_config(page_title="Digital Twin Model Selector V1", layout="wide")  # wide layout gives room for tool cards side by side

with st.sidebar:
    st.header("Settings")
    api_url = st.text_input(
        "RAG API URL",
        value=DEFAULT_API_URL,
        help="Points at rag/api.py — local FastAPI or a cloudflared tunnel URL.",
    ).rstrip("/")

st.title("Digital Twin Model Selection")  # main page title

# --- CASCADING CATEGORY DROPDOWNS ---------------------------------------------
# These live OUTSIDE the st.form below on purpose: a form only reruns the app
# on submit, so if Industry lived inside the form, picking a new Industry
# wouldn't refresh the Application list until Search was clicked. Keeping
# them here means each dropdown updates immediately as you make a choice.
# All three are optional -- a user can still search on free text alone.
st.caption("Optionally narrow your search (all fields optional):")
col_industry, col_application, col_nature = st.columns(3)

with col_industry:
    industry = st.selectbox(
        "Industry",
        options=["(Any)"] + list(INDUSTRY_TAXONOMY.keys()),
    )  # top of the cascade; "(Any)" means no filter applied

with col_application:
    # Application options depend on the selected Industry. When Industry is
    # "(Any)", fall back to the full de-duplicated list across all industries
    # so the field still offers something useful.
    if industry == "(Any)":
        application_options = ["(Any)"] + sorted({app for apps in INDUSTRY_TAXONOMY.values() for app in apps})
    else:
        application_options = ["(Any)"] + INDUSTRY_TAXONOMY[industry]
    application = st.selectbox("Application", options=application_options)

with col_nature:
    nature = st.selectbox("Nature of project", options=["(Any)"] + NATURE_OPTIONS)

# Bundle selections into one dict so run_query() gets clean structured fields
# rather than having to re-parse them out of the free-text query later. Your
# backend's "enhanced prompt" step can decide how to fold these in.
selected_categories = {
    "industry": None if industry == "(Any)" else industry,
    "application": None if application == "(Any)" else application,
    "nature_of_project": None if nature == "(Any)" else nature,
}

# --- SEARCH BAR --------------------------------------------------------------
# This is the real entry point of your architecture (question input -> enhance
# prompt -> query embedding -> similarity search). run_query() below calls the
# real backend.

if "query" not in st.session_state:  # session_state persists values across reruns
    st.session_state.query = None  # None means "nothing submitted yet" -> hide results
if "categories" not in st.session_state:
    st.session_state.categories = {}  # persists the submitted dropdown selections alongside the query

with st.form(key="search_form"):  # form batches the text input + button into one submit action
    user_query = st.text_input(
        "Describe your digital twin problem",
        placeholder="e.g. Digital twin for a hydraulic press with predictive maintenance",
    )  # free-text prompt input from the user
    submitted = st.form_submit_button("Search")  # triggers a rerun only on click, not on every keystroke

if submitted and user_query.strip():  # only proceed if the button was pressed and the field isn't blank
    st.session_state.query = user_query  # store the submitted query so it survives the rerun
    st.session_state.categories = selected_categories  # store the dropdown selections alongside it

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
        pipeline_diagram = data["pipeline_diagram"]
        architecture_diagram = data["architecture_diagram"]
    except requests.RequestException as exc:
        description = f"Couldn't reach the RAG API at {api_url} — is it running? ({exc})"
        tools = []
        pipeline_diagram = ""
        architecture_diagram = ""

    return description, tools, pipeline_diagram, architecture_diagram

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

# --- RESULTS (only shown after a query has been submitted) -------------------
if st.session_state.query:  # gate everything below on having a real submitted query
    st.caption(f"Query: *{st.session_state.query}*")  # shows what was asked, italicized for visual distinction

    # show which category filters (if any) were applied, for transparency
    applied = [f"{k.replace('_', ' ').title()}: {v}" for k, v in st.session_state.categories.items() if v]
    if applied:
        st.caption("Filters: " + "  ·  ".join(applied))

    thinking = st.empty()
    with thinking:
        render_thinking()  # animated cue; keeps moving in the browser while run_query() blocks
    description, tools, pipeline_diagram, architecture_diagram = run_query(
        st.session_state.query, st.session_state.categories
    )  # fetch results for the current query + category selections
    thinking.empty()  # clear the cue once the answer (or error) is back

    # --- SECTION 1: DESCRIPTION ---------------------------------------------
    st.header("1. Workflow Description V1")  # fixed section per your spec
    st.write(description)  # plain prose explanation of the digital twin workflow

    # --- SECTION 2: TOOL SUGGESTIONS ------------------------------------------
    st.header("2. Suggested Tools")  # fixed section per your spec

    if not tools:
        st.caption("No matching tools found in the catalogue for this query.")

    for tool in tools:  # loop over each ranked tool result
        with st.container(border=True):  # bordered box makes each tool visually distinct
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

            with st.expander("Details"):  # full schema dump, collapsed by default
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

    # --- SECTION 3: WORKFLOW DIAGRAMS -------------------------------------------
    st.header("3. Workflow Diagram")  # fixed section per your spec

    def render_mermaid(diagram: str, height: int = 320):
        """Shared helper so both tabs embed mermaid the same way instead of
        duplicating the components.html block."""
        mermaid_html = f"""
        <script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.0/mermaid.min.js"></script>
        <div class="mermaid">{diagram}</div>
        <script>mermaid.initialize({{ startOnLoad: true }});</script>
        """  # wraps the mermaid syntax in the JS needed to render it in a browser
        # TODO: components.html is deprecated (removal after 2026-06-01, Streamlit
        # suggests st.iframe — but that expects a URL, not raw HTML, so it's not a
        # drop-in swap). Revisit before the removal date, e.g. via streamlit-mermaid.
        components.html(mermaid_html, height=height)  # embeds the mermaid diagram inline in the Streamlit page

    tab_pipeline, tab_architecture = st.tabs(["Pipeline", "Architecture"])  # two views of the same workflow
    with tab_pipeline:
        st.caption("Sequence of steps: what happens, in what order, when the system runs.")
        if pipeline_diagram:
            render_mermaid(pipeline_diagram)
        else:
            st.caption("No diagram available for this query.")
    with tab_architecture:
        st.caption("Static structure: the components and how they relate.")
        if architecture_diagram:
            render_mermaid(architecture_diagram)
        else:
            st.caption("No diagram available for this query.")

    # --- SECTION 4: EXPORT -------------------------------------------------------
    st.header("4. Export")  # placeholder tying UI to your planned LaTeX output step
    st.button("Export report as LaTeX/PDF (not yet wired up)")
else:
    st.info("Enter a digital twin problem above and hit Search to see suggestions.")  # empty state before first search
