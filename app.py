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
        "score": 0.91,  # similarity score from vector search, 0-1
        "rationale": "Strong fit for physics-based hydraulic system modelling with real-time sync.",
        "standards": ["ISO 23247", "IEC 62443"],
        "source_url": "https://example.com/simulink",
        "alternatives": ["ANSYS Twin Builder", "Modelica/OpenModelica"],
    },
    {
        "name": "ChromaDB + LangChain",
        "score": 0.78,
        "rationale": "Handles the retrieval layer for historical maintenance logs feeding the twin.",
        "standards": ["N/A"],
        "source_url": "https://example.com/chromadb",
        "alternatives": ["Weaviate", "Pinecone"],
    },
]

mock_flowchart = """
graph LR
    A[Sensor Data Ingestion] --> B[Data Preprocessing]
    B --> C[Simulation Layer]
    C --> D[Predictive Maintenance Model]
    D --> E[Feedback to Physical Asset]
    E --> A
"""

# --- PAGE CONFIG -------------------------------------------------------------
st.set_page_config(page_title="Digital Twin Model Selector", layout="wide")  # wide layout gives room for tool cards side by side

st.title("Digital Twin Model Selection")  # main page title

# --- SEARCH BAR --------------------------------------------------------------
# This is the real entry point of your architecture (question input -> enhance
# prompt -> query embedding -> similarity search). For now, submitting always
# returns the same mock_tools/mock_flowchart below; swap run_query() for a
# real call to the backend once retrieval is built.

if "query" not in st.session_state:  # session_state persists values across reruns
    st.session_state.query = None  # None means "nothing submitted yet" -> hide results

with st.form(key="search_form"):  # form batches the text input + button into one submit action
    user_query = st.text_input(
        "Describe your digital twin problem",
        placeholder="e.g. Digital twin for a hydraulic press with predictive maintenance",
    )  # free-text prompt input from the user
    submitted = st.form_submit_button("Search")  # triggers a rerun only on click, not on every keystroke

if submitted and user_query.strip():  # only proceed if the button was pressed and the field isn't blank
    st.session_state.query = user_query  # store the submitted query so it survives the rerun

def run_query(query: str):
    """
    Placeholder for the real retrieval call.
    TODO: replace this with an actual request to the RAG backend
    (ChromaDB + LangChain), passing `query` and returning real results
    in the same shape as mock_description / mock_tools / mock_flowchart.
    """
    return mock_description, mock_tools, mock_flowchart  # stubbed until backend is wired up

# --- RESULTS (only shown after a query has been submitted) -------------------
if st.session_state.query:  # gate everything below on having a real submitted query
    st.caption(f"Query: *{st.session_state.query}*")  # shows what was asked, italicized for visual distinction

    description, tools, flowchart = run_query(st.session_state.query)  # fetch results for the current query

    # --- SECTION 1: DESCRIPTION ---------------------------------------------
    st.header("1. Workflow Description")  # fixed section per your spec
    st.write(description)  # plain prose explanation of the digital twin workflow

    # --- SECTION 2: TOOL SUGGESTIONS ------------------------------------------
    st.header("2. Suggested Tools")  # fixed section per your spec

    for tool in tools:  # loop over each ranked tool result
        with st.container(border=True):  # bordered box makes each tool visually distinct
            col1, col2 = st.columns([3, 1])  # left column for name/rationale, right for score
            with col1:
                st.subheader(tool["name"])  # tool name as subheading
                st.write(tool["rationale"])  # why this tool was suggested (explainability)
                st.caption("Standards: " + ", ".join(tool["standards"]))  # certification mapping
                st.markdown(f"[Source]({tool['source_url']})")  # traceability link back to origin
            with col2:
                st.metric("Match", f"{tool['score']*100:.0f}%")  # confidence score, shown prominently

            with st.expander("Alternatives"):  # collapsed by default to avoid clutter
                for alt in tool["alternatives"]:  # list runner-up tools
                    st.write(f"- {alt}")

    # --- SECTION 3: FLOWCHART --------------------------------------------------
    st.header("3. Workflow Flowchart")  # fixed section per your spec

    mermaid_html = f"""
    <script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.0/mermaid.min.js"></script>
    <div class="mermaid">{flowchart}</div>
    <script>mermaid.initialize({{ startOnLoad: true }});</script>
    """  # wraps the mermaid syntax in the JS needed to render it in a browser

    # TODO: components.html is deprecated (removal after 2026-06-01, Streamlit
    # suggests st.iframe — but that expects a URL, not raw HTML, so it's not a
    # drop-in swap). Revisit before the removal date, e.g. via streamlit-mermaid.
    components.html(mermaid_html, height=300)  # embeds the mermaid diagram inline in the Streamlit page

    # --- SECTION 4: EXPORT -------------------------------------------------------
    st.header("4. Export")  # placeholder tying UI to your planned LaTeX output step
    st.button("Export report as LaTeX/PDF (not yet wired up)")
else:
    st.info("Enter a digital twin problem above and hit Search to see suggestions.")  # empty state before first search
