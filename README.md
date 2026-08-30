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

## Local UI development (offline, no real backend)

`mock_api.py` is a standard-library stub of the RAG backend so you can
iterate on the UI without the real model. Use two terminals:

```bash
make mock        # terminal 1 — fake backend on :8000 (~2s delay)
make streamlit   # terminal 2 — the app
```

The sidebar "RAG API URL" already defaults to `http://localhost:8000`, so
searches hit the mock and the full results UI renders with canned data.
`.streamlit/config.toml` sets `runOnSave = true`, so saving `app.py`
re-runs the page automatically — no manual refresh.

- `MOCK_DELAY=0 make mock` — instant responses, fastest for layout work.
- `make mock_slow` — 20s delay, to see the "thinking" animation and other
  loading states.
- Stop the mock (`Ctrl-C`) to test the "Couldn't reach the RAG API" path.
- Drop a real captured backend response into `mock_response.json` (next to
  `mock_api.py`, gitignored) to preview real content instead of the canned
  payload.

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
