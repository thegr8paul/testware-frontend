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

## Deploy (Streamlit Community Cloud)

- **Entrypoint**: `app.py`. **Python**: 3.11–3.12. Deps come from `requirements.txt`.
- Point the app at a reachable backend by adding this to the app's **Secrets**
  (Settings → Secrets), since Cloud has no `localhost`:

  ```toml
  API_URL = "https://your-rag-backend.example.com"
  ```

  Resolution order is `API_URL` env var → `st.secrets["API_URL"]` → `http://localhost:8000`.
- `mock_api.py` is **local-only** — Cloud runs `app.py` and nothing else. With no
  backend reachable the landing page still loads; a search then shows the
  "Couldn't reach the RAG API" state.
- `saved_workflows.json` is written to the app's ephemeral filesystem and is
  **not** persisted across Cloud restarts.

## Local UI development (offline, no real backend)

`mock_api.py` is a standard-library stub of the RAG backend so you can
iterate on the UI without the real model. Use two terminals:

```bash
make mock        # terminal 1 — fake backend on :8000 (~2s delay)
make streamlit   # terminal 2 — the app
```

The backend URL defaults to `http://localhost:8000` (override with the
`API_URL` env var), so searches hit the mock and the full results UI
renders with canned data. `.streamlit/config.toml` sets `runOnSave = true`,
so saving `app.py` re-runs the page automatically — no manual refresh.

- `MOCK_DELAY=0 make mock` — instant responses, fastest for layout work.
- `make mock_slow` — 20s delay, to see the search-bar loading sweep and
  other loading states.
- Stop the mock (`Ctrl-C`) to test the "Couldn't reach the RAG API" path.
- Drop a real captured backend response into `mock_response.json` (next to
  `mock_api.py`, gitignored) to preview real content instead of the canned
  payload.

### Fast iteration loop

- **Styling lives in `styles.css`**, injected once by `load_css()` in
  `app.py`. Tweak the CSS, save, and the page reloads in under a second — no
  Python change. This is the loop for anything visual.
- The two layout states are driven by `st.session_state.query`:
  - `None` → **landing**: a rotating headline over a big centred search bar
    (`render_search_bar("hero")`), nothing else.
  - set → **results**: slim top bar (`render_search_bar("compact")`) plus the
    result sections.
  Click **New workflow** in the sidebar nav rail to save the current result
  to `saved_workflows.json`, clear everything, and return to the landing
  layout. With `MOCK_DELAY=0` a search round-trips instantly, so hopping
  between the two states is one click each way.
- The three category dropdowns (Industry / Application / Nature) are
  `st.popover`s *inside* the bar — there is no `st.form`, so choosing an
  Industry reruns immediately and the Application list cascades live.
- CSS targets Streamlit-private hooks (`data-testid=…`, `.st-key-…`). They
  are all in `styles.css`, each commented, so a Streamlit upgrade break is
  easy to find. Use browser DevTools → inspect element to discover hooks.
- Theme (warm off-white / near-black "Perplexity-style", black accent) is
  pinned in `.streamlit/config.toml` under `[theme]`. Colour is reserved for
  tags and canvas nodes — never chrome.

> Requires Streamlit ≥ 1.39 (`st.popover(icon=…)`, `.st-key-…` wrappers,
> column `gap` / `vertical_alignment`). `requirements.txt` currently leaves
> `streamlit` unpinned.

## Workflow canvas

The workflow canvas (`components/workflow/`, built on **Drawflow** —
vendored `drawflow.min.js` / `.min.css`, no npm, works offline) renders
between the description and the suggested tools. It's a bidirectional
Streamlit component: it receives the backend's structured `workflow`
(`{nodes, edges}`) plus the list of suggested `catalogue_id`s, and returns
either a clicked node or an edited graph.

- Nodes tagged **DB** map to a real catalogue entry (`catalogue_id`); an
  accent ring marks those also present in the suggested-tools list.
- Clicking a DB node focuses its tool card (ring + expanded details).
- **Editable**: drag a node to move it, drag an output dot to an input dot
  to wire, click a wire then press Delete to remove it. Edits round-trip to
  the backend (debounced `edit` event) and survive reruns; the `/query`
  result is cached per (query, filters) so an edit never triggers a re-POST
  that would discard node positions.
- Pan by dragging the canvas background; **pinch** (or Ctrl/Cmd + wheel) to
  zoom, anchored under the cursor. Plain two-finger scroll passes through to
  the page. The frame button (top-right) fits all nodes.
- To update the vendored lib: re-download from
  `https://cdn.jsdelivr.net/npm/drawflow@0.0.59/dist/` (note: a local one-line
  patch neutralises Drawflow's red `.selected` node background).

## Status

Currently running against mock data in `app.py` while the backend
retrieval pipeline is built out. The result sections are fixed by design:
1. Workflow description
2. Workflow canvas (editable)
3. Suggested tools (rationale, standards, source, alternatives)
4. Export

## Tests

```bash
make pytest
```
