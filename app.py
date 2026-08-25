import streamlit as st  # Streamlit for the whole UI
import streamlit.components.v1 as components  # needed to embed raw HTML/JS (mermaid.js) since Streamlit has no native mermaid renderer

# --- MOCK DATA -------------------------------------------------------------
# This stands in for what your RAG pipeline (ChromaDB + LangChain) will
# eventually return. Keep this shape close to your real output so swapping
# in live data later is a find-and-replace, not a redesign.

mock_description = (
    "A digital twin workflow for this use case typically starts with sensor "
    "data ingestion from the physical asset, moves through a simulation "
    "layer (physics-based or data-driven), and closes the loop with a "
    "predictive maintenance model feeding back into the live system."
)

mock_tools = [
    {
        "name": "MATLAB Simulink",
        # -- retrieval-time fields (per-query, not part of the static schema) --
        "score": 0.91,  # similarity score from vector search, 0-1
        "rationale": "Strong fit for physics-based hydraulic system modelling with real-time sync.",
        # -- status pills, pulled from _provenance_and_lifecycle / _taxonomy_classification --
        "development_status": "stable",
        "access_type": "commercial",
        "fidelity_tier": "continuum",
        # -- scale tags, from _domain_and_model_specifics.spatial_scale / temporal_scale
        # (real catalogue data stores these as free-text ranges, not numeric min/max) --
        "spatial_scale": "~1 mm – ~10 m",
        "temporal_scale": "~1 ms – ~1 year",
        # -- pricing, agreed shape ahead of Mitesh adding it to the schema --
        "pricing": {
            "model": "subscription",
            "estimate_low": 2500,
            "estimate_high": 8000,
            "currency": "USD",
            "unit": "per seat/year",
            "notes": "Academic pricing available at a discount.",
        },
        # -- validation, from _domain_and_model_specifics.validation_status --
        "validation_level": "experimental-correlation",
        "known_fail_modes": ["Struggles with highly stochastic sensor noise without pre-filtering."],
        # -- io spec, from _domain_and_model_specifics.inputs/outputs --
        "inputs": ["Sensor time-series (pressure, temperature)", "CAD/geometry reference"],
        "outputs": ["Predicted component wear (time-series)", "Remaining useful life estimate"],
        # -- standards, from _ecosystem_and_interoperability.interop_standards
        # (real catalogue data is a flat list of format/interop descriptions, not certifications) --
        "standards": ["ISO 23247", "IEC 62443"],
        "source_url": "https://example.com/simulink",
        "docs_url": "https://example.com/simulink/docs",
        "alternatives": ["ANSYS Twin Builder", "Modelica/OpenModelica"],
    },
    {
        "name": "ChromaDB + LangChain",
        "score": 0.78,
        "rationale": "Handles the retrieval layer for historical maintenance logs feeding the twin.",
        "development_status": "stable",
        "access_type": "open_source",
        "fidelity_tier": "system-level",
        "spatial_scale": "N/A",
        "temporal_scale": "~10 ms – ~5 years",
        "pricing": {
            "model": "open_source",
            "estimate_low": 0,
            "estimate_high": 0,
            "currency": "USD",
            "unit": "self-hosted",
            "notes": "Hosting/infra cost only; no license fee.",
        },
        "validation_level": "benchmark-suite",
        "known_fail_modes": ["Retrieval quality drops with sparse or inconsistent maintenance log formats."],
        "inputs": ["Historical maintenance logs (text)", "Query embeddings"],
        "outputs": ["Ranked relevant log excerpts", "Contextual retrieval for downstream model"],
        "standards": ["N/A"],
        "source_url": "https://example.com/chromadb",
        "docs_url": "https://example.com/chromadb/docs",
        "alternatives": ["Weaviate", "Pinecone"],
    },
]

mock_pipeline_diagram = """
sequenceDiagram
    participant Sensor as Sensor Interface
    participant Prep as Preprocessing
    participant Sim as Simulation Core (Simulink)
    participant RAG as Retrieval Layer (ChromaDB)
    participant Twin as Digital Twin State
    Sensor->>Prep: Raw time-series data
    Prep->>Sim: Cleaned signals
    RAG->>Sim: Historical maintenance context
    Sim->>Twin: Predicted wear + RUL estimate
    Twin->>Sensor: Feedback to live asset
"""  # shows WHEN each tool acts - the roadmap for assembling the pipeline

mock_architecture_diagram = """
classDiagram
    class PhysicalAsset {
        +sensorFeed
    }
    class SensorInterface {
        +ingest()
    }
    class SimulationCore {
        +runModel()
    }
    class RetrievalLayer {
        +queryHistory()
    }
    class DigitalTwinState {
        +predictedWear
        +remainingUsefulLife
    }
    PhysicalAsset --> SensorInterface
    SensorInterface --> SimulationCore
    RetrievalLayer --> SimulationCore
    SimulationCore --> DigitalTwinState
    DigitalTwinState --> PhysicalAsset : feedback
"""  # shows WHAT the components are and how they relate - the static architecture

# --- CATEGORY TAXONOMY -------------------------------------------------------
# Starter taxonomy for the cascading dropdowns. Industry -> Application is a
# real dependency (Application options change per Industry); "Nature of
# project" is a fixed list applied the same way regardless of Industry/App.
# TODO: revisit/expand once real domain coverage requirements are clearer.
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
st.set_page_config(page_title="Digital Twin Model Selector", layout="wide")  # wide layout gives room for tool cards side by side

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
# prompt -> query embedding -> similarity search). For now, submitting always
# returns the same mock_tools/mock_flowchart below; swap run_query() for a
# real call to the backend once retrieval is built.

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

def run_query(query: str, categories: dict):
    """
    Placeholder for the real retrieval call.
    TODO: replace this with an actual request to the RAG backend
    (ChromaDB + LangChain), passing `query` + `categories` and returning real
    results in the same shape as mock_description / mock_tools /
    mock_pipeline_diagram / mock_architecture_diagram.
    `categories` is {"industry": ..., "application": ..., "nature_of_project": ...},
    any of which may be None if left unselected -- this is where the backend's
    "enhanced prompt" step would fold them into the query before embedding.
    """
    return mock_description, mock_tools, mock_pipeline_diagram, mock_architecture_diagram  # stubbed until backend is wired up

# --- RESULTS (only shown after a query has been submitted) -------------------
if st.session_state.query:  # gate everything below on having a real submitted query
    st.caption(f"Query: *{st.session_state.query}*")  # shows what was asked, italicized for visual distinction

    # show which category filters (if any) were applied, for transparency
    applied = [f"{k.replace('_', ' ').title()}: {v}" for k, v in st.session_state.categories.items() if v]
    if applied:
        st.caption("Filters: " + "  ·  ".join(applied))

    description, tools, pipeline_diagram, architecture_diagram = run_query(
        st.session_state.query, st.session_state.categories
    )  # fetch results for the current query + category selections

    # --- SECTION 1: DESCRIPTION ---------------------------------------------
    st.header("1. Workflow Description")  # fixed section per your spec
    st.write(description)  # plain prose explanation of the digital twin workflow

    # --- SECTION 2: TOOL SUGGESTIONS ------------------------------------------
    st.header("2. Suggested Tools")  # fixed section per your spec

    for tool in tools:  # loop over each ranked tool result
        with st.container(border=True):  # bordered box makes each tool visually distinct
            st.subheader(tool["name"])  # tool name as subheading
            st.write(tool["rationale"])  # why this tool was suggested (explainability)

            # tag row: fidelity tier / spatial scale / temporal scale / standards,
            # each labeled so it's clear what kind of value each tag is
            tag_parts = [
                f"`Fidelity: {tool['fidelity_tier']}`",
                f"`Spatial: {tool['spatial_scale']}`",
                f"`Temporal: {tool['temporal_scale']}`",
            ]
            tag_parts += [f"`Standard: {s}`" for s in tool["standards"]]  # one pill per standard
            st.caption("  ·  ".join(tag_parts))

            # pricing + validation: the two numbers a lead engineer checks
            # right after "does it fit" - can I afford it, can I trust it
            price = tool["pricing"]
            if price["model"] == "open_source":
                price_line = "Free (open source)"
            else:
                price_line = f"{price['currency']} {price['estimate_low']:,}-{price['estimate_high']:,} {price['unit']}"
            col3, col4 = st.columns(2)
            with col3:
                st.write(f"**Est. price:** {price_line}")
            with col4:
                st.write(f"**Validation:** {tool['validation_level']}")

            with st.expander("Details"):  # full schema dump, collapsed by default
                st.markdown("**Inputs**")
                for i in tool["inputs"]:
                    st.write(f"- {i}")
                st.markdown("**Outputs**")
                for o in tool["outputs"]:
                    st.write(f"- {o}")
                st.markdown(f"[Reference]({tool['source_url']})")  # traceability link

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
        render_mermaid(pipeline_diagram)
    with tab_architecture:
        st.caption("Static structure: the components and how they relate.")
        render_mermaid(architecture_diagram)

    # --- SECTION 4: EXPORT -------------------------------------------------------
    st.header("4. Export")  # placeholder tying UI to your planned LaTeX output step
    st.button("Export report as LaTeX/PDF (not yet wired up)")
else:
    st.info("Enter a digital twin problem above and hit Search to see suggestions.")  # empty state before first search
