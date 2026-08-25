# Digital Twin Model Selector — Frontend

Streamlit frontend for the digital twin model-selection engine (Le Wagon
capstone). Given a query about a digital twin problem, the app surfaces:
a workflow description, ranked tool suggestions with rationale and
certification standards, a flowchart of the proposed workflow, and an
export-to-LaTeX action.

This repo covers the frontend only. Retrieval (ChromaDB + LangChain) and
the cataloguing pipeline live in the companion backend repo.

## Setup

```bash
git clone <this-repo-url>
cd digital-twin-selector-frontend
make install_requirements
```

## Run locally

```bash
make streamlit
```

## Status

Currently running against mock data in `app.py` while the backend
retrieval pipeline is built out. Sections are fixed by design:
1. Workflow description
2. Suggested tools (score, rationale, standards, source, alternatives)
3. Workflow flowchart
4. Export

## Tests

```bash
make pytest
```
