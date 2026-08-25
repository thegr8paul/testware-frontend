import streamlit as st  # Streamlit for the whole UI
import streamlit.components.v1 as components  # needed to embed raw HTML/JS (mermaid.js) since Streamlit has no native mermaid renderer

# --- MOCK DATA -------------------------------------------------------------
# This stands in for what your RAG pipeline (ChromaDB + LangChain) will
# eventually return. Keep this shape close to your real output so swapping
# in live data later is a find-and-replace, not a redesign.

mock_query = "Digital twin for a hydraulic press with predictive maintenance"

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
st.caption(f"Query: *{mock_query}*")  # shows what was asked, italicized for visual distinction

# --- SECTION 1: DESCRIPTION -------------------------------------------------
st.header("1. Workflow Description")  # fixed section per your spec
st.write(mock_description)  # plain prose explanation of the digital twin workflow

# --- SECTION 2: TOOL SUGGESTIONS --------------------------------------------
st.header("2. Suggested Tools")  # fixed section per your spec

for tool in mock_tools:  # loop over each ranked tool result
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

# --- SECTION 3: FLOWCHART ----------------------------------------------------
st.header("3. Workflow Flowchart")  # fixed section per your spec

mermaid_html = f"""
<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.0/mermaid.min.js"></script>
<div class="mermaid">{mock_flowchart}</div>
<script>mermaid.initialize({{ startOnLoad: true }});</script>
"""  # wraps the mermaid syntax in the JS needed to render it in a browser

# TODO
components.html(mermaid_html, height=300)  # embeds the mermaid diagram inline in the Streamlit page

# --- SECTION 4: EXPORT -------------------------------------------------------
st.header("4. Export")  # placeholder tying UI to your planned LaTeX output step
st.button("Export report as LaTeX/PDF (not yet wired up)")
