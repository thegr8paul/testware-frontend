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

### Fast iteration loop

- **Styling lives in `styles.css`**, injected once by `load_css()` in
  `app.py`. Tweak the CSS, save, and the page reloads in under a second — no
  Python change. This is the loop for anything visual.
- The two layout states are driven by `st.session_state.query`:
  - `None` → **landing**: big centred search bar (`render_search_bar("hero")`),
    nothing else.
  - set → **results**: slim top bar (`render_search_bar("compact")`) plus the
    numbered sections.
  Click **New search** in the results view to clear everything and return to
  the landing layout. With `MOCK_DELAY=0` a search round-trips instantly, so
  hopping between the two states is one click each way.
- The three category dropdowns (Industry / Application / Nature) are
  `st.popover`s *inside* the bar — there is no `st.form`, so choosing an
  Industry reruns immediately and the Application list cascades live.
- CSS targets Streamlit-private hooks (`data-testid=…`, `.st-key-…`). They
  are all in `styles.css`, each commented, so a Streamlit upgrade break is
  easy to find. Use browser DevTools → inspect element to discover hooks.
- Theme (black & white + one red accent) is pinned in
  `.streamlit/config.toml` under `[theme]`.

> Requires Streamlit ≥ 1.39 (`st.popover(icon=…)`, `.st-key-…` wrappers,
> column `gap` / `vertical_alignment`). `requirements.txt` currently leaves
> `streamlit` unpinned.

## Section 3 — workflow canvas

Section 3 is a read-only node canvas (`components/workflow/`, built on
**Drawflow** — vendored `drawflow.min.js` / `.min.css`, no npm, works
offline). It's a bidirectional Streamlit component: it receives the backend's
structured `workflow` (`{nodes, edges}`) plus the list of suggested
`catalogue_id`s, and returns the clicked node.

- Nodes tagged **DB** map to a real catalogue entry (`catalogue_id`); a red
  ring marks those also present in Section 2's suggestions.
- Clicking a DB node focuses its Section 2 card (ring + expanded details).
- Drag the canvas to pan, wheel/trackpad to zoom. No editing yet.
- To update the vendored lib: re-download from
  `https://cdn.jsdelivr.net/npm/drawflow@0.0.59/dist/`.

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
