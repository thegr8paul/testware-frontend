# Frontend refresh — handoff notes

Branch `feat/frontend-refresh` → PR #2. This is a summary for anyone picking
up the frontend after the refresh. See the PR description for the narrative
and `git log 9c2589a..feat/frontend-refresh` for the commits.

## TL;DR of what changed

| Area | Before | After |
|---|---|---|
| Theme | Black & white + Streamlit-red accent | Warm off-white / near-black "Perplexity-style", black accent (`.streamlit/config.toml` + `styles.css`) |
| Layout | Numbered sections 1–4, sidebar with a "RAG API URL" text field | Sidebar is a nav rail ("New workflow" + disabled placeholders); backend URL is config, not a widget |
| Section order | 1 Description · 2 Tools · 3 Canvas · 4 Export | 1 Description · **2 Canvas** · 3 Tools · 4 Export |
| Workflow canvas | Read-only; returns the clicked node | **Editable** (move / wire / delete); returns a clicked node **or** an edited graph |
| Facets | Hardcoded dict in `app.py` (6 industries) | `facets.json` (15 industries, 8 use cases) |
| Loading cue | Full-screen shimmer with rotating words (`render_thinking()`) | Subtle sweep on the search bar (`_BAR_LOADING_CSS`) |
| Backend URL | `os.environ["API_URL"]` only | env var → `st.secrets["API_URL"]` → localhost |

## Where things live now (`app.py`)

- `_resolve_api_url()` — backend URL precedence (env → secrets → localhost).
- `_FACETS` / `INDUSTRY_TAXONOMY` / `NATURE_OPTIONS` — loaded from `facets.json`.
- `HEADLINES` + `st.session_state.headline` — the rotating landing headline
  (re-rolled by "New workflow").
- `_BAR_LOADING_CSS` — the search-bar loading sweep, rendered into a
  `status_slot` that `render_search_bar()` returns and `.empty()`s when the
  fetch finishes.
- `_save_workflow(result)` — appends the on-screen result to
  `saved_workflows.json` (git-ignored, ephemeral).
- Result caching — `run_query()` is only called when
  `(query, json.dumps(categories, sort_keys=True))` changes; otherwise the
  cached `description / tools / workflow` is reused. **Why:** the backend
  returns a different graph each POST, which would rebuild the canvas and
  discard the user's dragged node positions.
- `last_result` in session — the payload `_save_workflow()` persists.

## Workflow canvas component contract (`components/workflow/`)

Streamlit → component `args`:
- `workflow`: `{nodes: [...], edges: [...]}` — the backend shape. Node fields
  read: `id, type, label, inputs[], outputs[], catalogue_id, catalogue_title,
  x, y`. Edge fields: `source, target, source_port, target_port, label`.
  `type` ∈ `input | process | model | decision | merge | output | database`.
- `suggested`: list of `catalogue_id`s (from the tools list) → draws the
  accent ring.

Component → Streamlit return value (`_sel` in `app.py`):
- **Node click** → `{node, catalogue_id, ts}` → sets `focus_tool`, which
  highlights/expands the matching tool card.
- **Graph edit** (drag / wire / delete, debounced 140 ms) →
  `{kind: "edit", workflow: {...}, ts}` → written back into
  `st.session_state.results["workflow"]` and `last_result`. The component
  recognises its own echo via a content signature, so this does **not**
  trigger a rebuild.

Ports: `source_port` / `target_port` are 0-based indices into the node's
`outputs` / `inputs`; out-of-range indices are clamped, missing endpoints
drop the edge — a malformed graph renders messy but never errors.

Backend note (not in this PR): the RAG service already emits this exact
`workflow` shape from `rag/core/workflow.py`. To get richer digital-twin
graphs the levers are its prompt (`rag/prompts/workflow.py`, currently
zero-shot) and a validation pass — no frontend change needed.

## Read Me / demo-day deck (`components/deck/`)

Sidebar → **Read Me** opens a full-page animated slide deck (`show_readme`
flag in `app.py`; `deck_view` custom component). The deck renders
**`presentation.md`** — no code needed to edit it:

- Slides are separated by a line of `---`.
- `####` eyebrow · `##` title (`*asterisks*` = accent colour) · `###` sub-line
  · `-` bullet · `>` quote · `![caption](file)` image.
- Images: drop files in `components/deck/` and reference by name, or use a
  full `https://` URL. `placeholder-a.svg` / `placeholder-b.svg` are stand-ins.
- Layout per slide is inferred (slide 1 = title, heading-only = section, has
  an image = media, has a quote = quote, else content). Force it with an HTML
  comment whose text is `layout: NAME` (title | section | content | media |
  split | quote).

One colour theme only — the app's warm-cream / Source Sans 3 — plus a faint
connecting-node canvas and staged slide entrances. The parser lives in
`components/deck/index.html` (`parse()` / `infer()` / `blockEl()`); it is a
deliberately tiny Markdown subset, not a full renderer.

For presenting outside the app there is also a standalone six-direction
design-exploration deck (Claude artifact) — the in-app deck is the "Signal"
direction from it, locked to the app theme.

## Gotchas

- `styles.css` targets Streamlit-private hooks (`[data-testid=…]`,
  `.st-key-<key>`); a Streamlit upgrade can break them. Each is commented.
- `components/workflow/drawflow.min.css` has a one-line local patch
  (`.drawflow-node.selected{}` — red background removed). Re-applying a
  vendor download will clobber it.
- Trackpad zoom is a custom handler in `components/workflow/index.html`
  (`installWheel()`); pinch / Ctrl+wheel zooms, plain scroll passes through.
- No automated tests yet (`make pytest` collects 0).

## Continuing the work

1. Merge PR #2 into `thegr8paul/testware-frontend@main`.
2. In the parent repo `ivitsh/testware-dev`: bump the submodule pointer
   (`git -C frontend/testware-frontend checkout main && git pull`, then commit
   `frontend/testware-frontend`) on a branch off the current `main`, open a PR.
3. To deploy: Streamlit Community Cloud, entrypoint `app.py`, set `API_URL` in
   Secrets (see README "Deploy").
