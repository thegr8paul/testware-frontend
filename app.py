import json
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import streamlit as st  # Streamlit for the whole UI
import streamlit.components.v1 as components  # raw HTML/JS embeds (the "thinking" cue) + the workflow component

def _resolve_api_url() -> str:
    """Backend base URL. Precedence: API_URL env var -> [API_URL] in
    Streamlit secrets (how you set it on Streamlit Community Cloud) ->
    localhost for local dev against `make mock` / a local FastAPI."""
    if os.environ.get("API_URL"):
        return os.environ["API_URL"]
    try:
        if "API_URL" in st.secrets:
            return str(st.secrets["API_URL"])
    except Exception:  # no secrets.toml at all -- fine, fall through
        pass
    return "http://localhost:8000"


DEFAULT_API_URL = _resolve_api_url()

# Section 3's node canvas -- a bidirectional component (Drawflow, vendored).
# Returns {node, catalogue_id, ts} when a node is clicked, else None.
_WF_DIR = Path(__file__).with_name("components") / "workflow"
workflow_canvas = components.declare_component("tw_workflow", path=str(_WF_DIR))

# Read Me / demo-day deck -- renders presentation.md as animated slides.
# Guarded: if the component assets are ever missing on a deploy, Read Me
# falls back to plain Markdown instead of taking down the whole app.
_DECK_DIR = Path(__file__).with_name("components") / "deck"
try:
    deck_view = components.declare_component("tw_deck", path=str(_DECK_DIR))
except Exception:  # noqa: BLE001
    deck_view = None

# Search-bar facets (curated -- see facets.json "_provenance"). Loaded once.
_FACETS = json.loads(Path(__file__).with_name("facets.json").read_text())
INDUSTRY_TAXONOMY = _FACETS["industries"]
NATURE_OPTIONS = _FACETS["nature_options"]

INDUSTRY_ICON = ":material/factory:"
APPLICATION_ICON = ":material/tune:"
NATURE_ICON = ":material/science:"

# Landing headline -- one is picked at random per session (re-rolls on
# "New workflow"). Professional but with some energy.
HEADLINES = [
    "Let's twin.",
    "What are we twinning today?",
    "Describe the system. Get its twin.",
    "What do you want to model?",
    "Let's build your digital twin.",
    "What should we clone today?",
    "From description to digital twin.",
    "Point me at a system.",
    "What are we simulating today?",
    "Spin up a twin.",
]

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

# Loading cue: a grey shimmer sweep over the whole compact search bar. Rendered
# into `status_slot` while run_query() blocks; status_slot.empty() removes this
# <style> node so the sweep stops. No text.
_BAR_LOADING_CSS = (
    "<style>"
    "@keyframes tw-bar-sweep{0%{background-position:220% 0}100%{background-position:-220% 0}}"
    ".st-key-tw_searchbar_compact::after{content:'';position:absolute;inset:0;"
    "border-radius:inherit;pointer-events:none;z-index:6;"
    "background:linear-gradient(100deg,transparent 38%,rgba(17,17,17,0.10) 50%,transparent 62%);"
    "background-size:220% 100%;animation:tw-bar-sweep 2.5s linear infinite;}"
    "</style>"
)

# --- PAGE CONFIG -----------------------------------------------------------
st.set_page_config(page_title="Digital Twin Model Selector", layout="wide")  # wide layout gives room for tool cards side by side


def load_css():
    """Inject styles.css once. Kept in a separate file so visual tweaks are a
    save-and-reload loop with no Python change (see README)."""
    css = Path(__file__).with_name("styles.css").read_text()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


load_css()

# Fixed backend URL -- override with the API_URL env var. (Used to be a
# sidebar text input; the sidebar is now a nav rail.)
api_url = DEFAULT_API_URL.rstrip("/")

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
st.session_state.setdefault("headline", random.choice(HEADLINES))
# The app has three top-level areas, chosen in the sidebar:
#   "chat"          -> the query interface + its workflow output
#   "presentation"  -> the demo-day deck (presentation.md)
#   "examples"      -> the curated mock workflows (examples/*.json)
st.session_state.setdefault("area", "chat")


def _current_categories() -> dict:
    """The three picker values as structured fields -- "(Any)" dropped. Only
    ever folded into the query text and shown as chips."""
    picks = {
        "industry": st.session_state.industry,
        "application": st.session_state.application,
        "nature_of_project": st.session_state.nature,
    }
    return {k: v for k, v in picks.items() if v != "(Any)"}


# --- Enhanced query ---------------------------------------------------------
# rag-service's POST /query takes ONE string (rag/schemas.py: QueryRequest,
# min 3 / max 1000 chars) and reuses it for BOTH the vector-retrieval
# embedding AND every generation prompt (answer / diagram / tools). So the
# recipe is: the user's own words first and verbatim (retrieval leans on
# them), then the picked categories, then one short instruction that steers
# the answer toward what the UI shows. Everything below is parametric --
# tune the constants, not the f-string.

_QUERY_MAX = 1000  # QueryRequest.query max_length; longer -> HTTP 422
_CATEGORY_LABELS = {
    "industry": "Industry",
    "application": "Application",
    "nature_of_project": "Nature of project",
}
# Appended last. Kept to one sentence on purpose -- it is embedded for
# retrieval too, so a longer instruction would dilute the user's problem
# statement. Set to "" to send just the query + context.
_OUTPUT_STEER = (
    "Answer as a concrete end-to-end digital-twin workflow: name a specific "
    "catalogue tool for each step, note its fidelity tier and any relevant "
    "standards, and give a rough budget and timeline."
)


def build_enhanced_query(raw_query: str, categories: dict) -> str:
    """Compose the single string sent to the backend: the raw prompt, then the
    set categories as a labelled block, then `_OUTPUT_STEER` -- all kept within
    `_QUERY_MAX`. Only the raw prompt is trimmed (with an ellipsis) if the
    budget is tight; the context block and steer are short and fixed.

    `categories` uses the `_current_categories()` shape -- `{industry,
    application, nature_of_project}` with unset values already dropped; an
    empty dict just yields "<query>\\n\\n<steer>".
    """
    raw = (raw_query or "").strip()

    blocks = []
    ctx = [f"- {_CATEGORY_LABELS.get(k, k)}: {v}"
           for k, v in categories.items() if v and v != "(Any)"]
    if ctx:
        blocks.append("Context:\n" + "\n".join(ctx))
    if _OUTPUT_STEER:
        blocks.append(_OUTPUT_STEER)
    tail = "\n\n".join(blocks)

    if not tail:
        return raw[:_QUERY_MAX]
    budget = _QUERY_MAX - len(tail) - 2  # 2 = the "\n\n" that joins raw to tail
    if budget <= 0:                      # pathological: tail alone too long
        return tail[:_QUERY_MAX]
    if len(raw) > budget:
        raw = raw[: budget - 1].rstrip() + "…"
    return f"{raw}\n\n{tail}"


SAVED_WORKFLOWS_PATH = Path(__file__).with_name("saved_workflows.json")


def _save_workflow(result: dict | None) -> bool:
    """Append the on-screen result (query + categories + workflow + tools +
    description) to saved_workflows.json. No-op if there is no workflow yet."""
    if not result or not (result.get("workflow") or {}).get("nodes"):
        return False
    try:
        existing = json.loads(SAVED_WORKFLOWS_PATH.read_text()) if SAVED_WORKFLOWS_PATH.exists() else []
        if not isinstance(existing, list):
            existing = []
    except (json.JSONDecodeError, OSError):
        existing = []
    existing.append({**result, "saved_at": datetime.now(timezone.utc).isoformat()})
    SAVED_WORKFLOWS_PATH.write_text(json.dumps(existing, indent=2))
    return True


EXAMPLES_DIR = Path(__file__).with_name("examples")


@st.cache_data(show_spinner=False)
def _load_examples() -> list[dict]:
    """Curated example workflows shipped with the app (examples/*.json), each a
    single saved-result payload: {query, categories, description, tools,
    workflow}. Sorted by filename so 01-, 02-, ... controls display order.
    These are read-only seeds -- opening one drops straight into the results
    view with no backend call (see the gallery block below)."""
    out: list[dict] = []
    if not EXAMPLES_DIR.is_dir():
        return out
    for path in sorted(EXAMPLES_DIR.glob("*.json")):
        try:
            ex = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if ex.get("query") and (ex.get("workflow") or {}).get("nodes"):
            ex["_slug"] = path.stem
            out.append(ex)
    return out


def _open_example(ex: dict) -> None:
    """Load a curated example into session as if it were a query result:
    pre-seed st.session_state.results with a cache key that matches the LAYOUT
    block's, so it's reused instead of POSTing to the backend. Mutates state
    only -- the caller reruns (or Streamlit auto-reruns after an on_change)."""
    cats = dict(ex.get("categories") or {})
    st.session_state.query = ex["query"]
    st.session_state.query_input = ex["query"]          # compact search field
    st.session_state.categories = cats
    st.session_state.industry = cats.get("industry") or "(Any)"
    st.session_state.application = cats.get("application") or "(Any)"
    st.session_state.nature = cats.get("nature_of_project") or "(Any)"
    st.session_state.results = {
        "key": (ex["query"], json.dumps(cats, sort_keys=True)),
        "description": ex.get("description", ""),
        "tools": ex.get("tools", []),
        "workflow": ex["workflow"],
    }
    st.session_state.focus_tool = None
    st.session_state.area = "examples"


def _example_short(ex: dict) -> str:
    """A compact label for the sidebar example picker, e.g.
    '02-ev-battery-pack-thermal' -> 'EV battery pack thermal'."""
    stem = re.sub(r"^\d+[-_]?", "", ex.get("_slug", "") or "")
    words = stem.replace("_", "-").split("-")
    _acronyms = {"ev", "ai", "ml", "cfd", "hpc", "iot"}
    out = " ".join(w.upper() if w in _acronyms else w for w in words if w).strip()
    return (out[:1].upper() + out[1:]) if out else ex.get("query", "example")


def _example_payload(result: dict | None) -> dict:
    """A live result narrowed to the examples/*.json shape (runtime-only keys
    like the result-cache 'key' and '_slug' dropped)."""
    result = result or {}
    return {
        "query": result.get("query", ""),
        "categories": result.get("categories", {}) or {},
        "description": result.get("description", ""),
        "tools": result.get("tools", []) or [],
        "workflow": result.get("workflow") or {"nodes": [], "edges": []},
    }


def _write_example(name: str, result: dict | None) -> Path:
    """Persist the on-screen workflow as examples/NN-<slug>.json so it ships
    with the app as a permanent pitch example. NN auto-increments. Only useful
    where the disk survives (local dev / an always-on host); on Streamlit
    Community Cloud copy the JSON into a new repo file instead."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "workflow"
    nums = [int(m.group(1)) for p in EXAMPLES_DIR.glob("*.json")
            if (m := re.match(r"(\d+)-", p.name))]
    nn = f"{(max(nums) + 1) if nums else 1:02d}"
    EXAMPLES_DIR.mkdir(exist_ok=True)
    path = EXAMPLES_DIR / f"{nn}-{slug}.json"
    path.write_text(json.dumps(_example_payload(result), indent=2) + "\n")
    _load_examples.clear()  # bust the cache -> the new example shows without a restart
    return path


def _iter_ndjson(resp):
    for raw in resp.iter_lines(decode_unicode=True):
        if raw:
            yield json.loads(raw)


def run_query_stream(query: str, categories: dict, status_slot):
    """Streaming replacement for run_query(). Returns
    (description, tools, workflow, ok) -- renders the description
    progressively via st.write_stream() instead of blocking on the whole
    response, and clears the search-bar shimmer as soon as real content
    starts arriving instead of only once everything is done. `ok` is False
    whenever the connection dropped at any point, so the caller knows this
    result is degraded rather than a clean, cacheable success.
    """
    try:
        resp = requests.post(
            f"{api_url}/query/stream",
            json={"query": build_enhanced_query(query, categories)},
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
        chunks = _iter_ndjson(resp)

        def _answer_tokens():
            for chunk in chunks:
                if chunk["stage"] == "answer_chunk":
                    for word in re.finditer(r"\S+\s*", chunk["text"]):
                        yield word.group()
                        time.sleep(0.05)   # ~50 words/sec — tune to taste
                elif chunk["stage"] == "answer_done":
                    return

        status_slot.empty()  # stop the shimmer now that real content is arriving
        description = st.write_stream(_answer_tokens())
    except requests.RequestException as exc:
        # Nothing streamed yet -- the connection itself never came up.
        status_slot.empty()
        msg = f"Couldn't reach the RAG API at {api_url} — is it running? ({exc})"
        st.write(msg)
        return msg, [], {"nodes": [], "edges": []}, False

    tools: list = []
    workflow: dict = {"nodes": [], "edges": []}

    st.write("")  # spacing so these read as separate from the answer above
    tools_status = st.status("Building tool suggestions…")
    workflow_status = st.status("Building workflow diagram…")

    tools_done = False
    workflow_done = False
    try:
        for chunk in chunks:
            if chunk["stage"] == "tools":
                tools = chunk["tools"]
                if chunk.get("error"):
                    st.caption(chunk["error"])
                tools_status.update(label="Tool suggestions ready", state="complete")
                tools_done = True
            elif chunk["stage"] == "workflow":
                workflow = chunk.get("workflow") or {"nodes": [], "edges": []}
                if chunk.get("error"):
                    st.caption(chunk["error"])
                workflow_status.update(label="Workflow diagram ready", state="complete")
                workflow_done = True
    except requests.RequestException:
        # The answer already streamed fine -- keep it, don't discard it for a
        # generic connection-error message. Only tools/workflow are lost, so
        # finalize whichever status is still spinning instead of leaving it
        # stuck, and tell the caller this run shouldn't be treated as done.
        if not tools_done:
            tools_status.update(label="Tool suggestions unavailable — connection dropped", state="error")
        if not workflow_done:
            workflow_status.update(label="Workflow diagram unavailable — connection dropped", state="error")
        return description, tools, workflow, False

    return description, tools, workflow, True


def _pop_label(field_name: str, value: str) -> str:
    """Popover label: the picked value, or the field name when unset -- so
    active filters are visible on the closed bar."""
    return field_name if value == "(Any)" else value


def render_search_bar(mode: str):
    """The one search bar. `mode` is "hero" (big, centered -- landing) or
    "compact" (slim, top -- results view). Three in-bar pickers: Industry,
    Application (cascades within Industry), Nature of project -- all from
    facets.json. Returns the status slot the caller uses to trigger the
    loading shimmer while run_query() blocks.
    """
    # In the results view, show the executed query inside the input field
    # (seed the widget state once if a fresh session lost it).
    if mode == "compact" and "query_input" not in st.session_state and st.session_state.get("query"):
        st.session_state.query_input = st.session_state.query

    with st.container(key=f"tw_searchbar_{mode}"):
        # Row 1: the text field + submit button, batched inside a form so a
        # value only commits (and triggers a search) on an actual submit --
        # Enter in the field or the button click -- never on merely losing
        # focus (e.g. clicking a popover), which a bare st.text_input would
        # also treat as a commit and search on.
        with st.form(key=f"tw_searchform_{mode}", border=False):
            query_text = st.text_input(
                "Describe your digital twin problem",  # kept for a11y; hidden below
                key="query_input",
                label_visibility="collapsed",
                placeholder="e.g. Digital twin for a hydraulic press with predictive maintenance",
            )
            submitted = st.form_submit_button(
                "",
                icon=":material/search:",
                type="primary",
                key="tw_search_btn",
                help="Search",
            )

        # Row 2: Industry / Application / Nature-of-project icon popovers, plus the
        # empty area the caller uses to trigger the loading shimmer
        # while run_query() blocks.
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
            # Application options cascade from the picked Industry; "(Any)"
            # -> the de-duplicated union across all industries.
            if st.session_state.industry == "(Any)":
                application_options = ["(Any)"] + sorted(
                    {app for apps in INDUSTRY_TAXONOMY.values() for app in apps}
                )
            else:
                application_options = ["(Any)"] + INDUSTRY_TAXONOMY[st.session_state.industry]
            # Drop a stale Application pick before the selectbox renders.
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
                help=_pop_label("Nature of project", st.session_state.nature),
            ):
                st.selectbox(
                    "Nature of project",
                    options=["(Any)"] + list(NATURE_OPTIONS),
                    key="nature",
                )

        status_slot = btn_cols[3].empty()

    # Inside a form, `submitted` is only True on an actual submit (button
    # click or Enter in the field) -- never on the field merely losing focus.
    typed = query_text.strip()
    if typed and submitted:
        st.session_state.query = query_text
        st.session_state.categories = _current_categories()
        st.rerun()

    return status_slot


def _render_workflow_result(*, allow_search: bool, allow_save: bool) -> None:
    """The workflow output: description + editable canvas + tool cards. Shared
    by the Chat area (allow_search/allow_save on -- live query, can be saved as
    an example) and the Examples area (both off -- a curated, pre-seeded
    result, never a backend call)."""
    status_slot = render_search_bar("compact") if allow_search else None

    # applied category filters as chips, for transparency
    applied = [f"{k.replace('_', ' ').title()}: {v}"
               for k, v in st.session_state.categories.items() if v]
    if applied:
        chips = "".join(f"<span class='tw-chip'>{a}</span>" for a in applied)
        st.markdown(f"<div class='tw-chips'>{chips}</div>", unsafe_allow_html=True)

    # Cache the fetch for the current (query, categories). Reruns triggered by
    # UI churn -- clicking a workflow node, opening a popover -- then reuse the
    # result instead of re-POSTing (which, being LLM-backed, would return a
    # different graph and rebuild the canvas, losing any dragged node positions).
    # Examples pre-seed `results` with a matching key, so this never fetches.
    _cache_key = (st.session_state.query,
                  json.dumps(st.session_state.categories, sort_keys=True))
    _cache = st.session_state.get("results")
    if not (_cache and _cache.get("key") == _cache_key):
        if status_slot is not None:
            with status_slot:
                st.markdown(_BAR_LOADING_CSS, unsafe_allow_html=True)  # shimmer only on a real fetch
        st.header("Workflow Description")
        description, tools, workflow, ok = run_query_stream(
            st.session_state.query, st.session_state.categories, status_slot
        )
        _cache = {"key": _cache_key, "description": description,
                  "tools": tools, "workflow": workflow, "ok": ok}
        st.session_state.results = _cache
    else:
        # Cache hit -- nothing was fetched this rerun, so there's nothing left
        # to stream. Render the description plainly from the cached value.
        description = _cache["description"]
        st.header("Workflow Description")
        st.write(description)
        # A previous fetch dropped mid-stream -- offer an explicit retry
        # instead of forcing a full page refresh to try again.
        if allow_search and _cache.get("ok") is False:
            if st.button("Retry", icon=":material/refresh:", key="tw_retry"):
                st.session_state.pop("results", None)
                st.rerun()

    tools = _cache["tools"]
    workflow = _cache["workflow"]

    # Stash the current result so "New workflow" / "Save as example" can use it.
    st.session_state.last_result = {
        "query": st.session_state.query,
        "categories": dict(st.session_state.categories),
        "description": description,
        "tools": tools,
        "workflow": workflow,
    }

    # --- SECTION: WORKFLOW CANVAS ---------------------------------------------
    st.header("Workflow")
    st.caption(
        "Suggested pipeline. Nodes tagged **DB** map to a catalogue entry; an "
        "accent ring marks tools also in the list below. Click a node to focus "
        "its card. Drag a node to move it; drag an output dot to an input dot to "
        "wire; click a wire then Delete (or its ×) to remove it. Drag canvas to "
        "pan, wheel to zoom."
    )
    _wf_suggested = [t["catalogue_id"] for t in tools if t.get("catalogue_id")]
    if workflow.get("nodes"):
        _sel = workflow_canvas(
            workflow=workflow, suggested=_wf_suggested, key="tw_wf", default=None
        )
        if isinstance(_sel, dict):
            if _sel.get("kind") == "edit" and _sel.get("workflow"):
                # User re-wired / moved nodes on the canvas -- make that the new
                # truth for this query. The component recognises its own echo
                # (matching heldSig) so this doesn't trigger a canvas rebuild.
                st.session_state.results["workflow"] = _sel["workflow"]
                st.session_state.last_result["workflow"] = _sel["workflow"]
            elif _sel.get("catalogue_id"):
                if st.session_state.get("focus_tool") != _sel["catalogue_id"]:
                    st.session_state.focus_tool = _sel["catalogue_id"]
                    st.rerun()
    else:
        st.caption("No workflow available for this query.")

    # --- SECTION: SAVE AS PITCH EXAMPLE (Chat area only) ------------------
    # Capture what's on screen -- query + categories + description + tools +
    # the graph INCLUDING any canvas edits -- as examples/NN-<slug>.json, so a
    # good workflow can be kept and reused as a demo example. Writing to disk
    # only sticks where the disk persists (local dev / always-on host); on
    # Streamlit Community Cloud, copy the JSON into a new repo file instead.
    if allow_save and workflow.get("nodes"):
        with st.expander("Save this workflow as a pitch example"):
            _ex_name = st.text_input(
                "Example name",
                value=(st.session_state.query or "")[:60],
                key="tw_ex_name",
                help="Becomes the filename: examples/NN-<name>.json",
            )
            _save_col, _hint_col = st.columns([1, 3], vertical_alignment="center")
            with _save_col:
                if st.button("Save to examples/", key="tw_ex_save",
                             icon=":material/bookmark_add:", use_container_width=True):
                    try:
                        _p = _write_example(_ex_name, st.session_state.last_result)
                        st.success(f"Wrote `examples/{_p.name}` — `git add` + commit it to keep it.")
                    except OSError as _e:
                        st.error(f"Couldn't write the file: {_e}")
            with _hint_col:
                st.caption(
                    "Commit & push the file and it shows up in the sidebar "
                    "**Examples** list for everyone. On Streamlit Cloud the disk "
                    "resets on redeploy — use the JSON below instead: copy it "
                    "into a new `examples/NN-name.json` in the repo."
                )
            st.code(
                json.dumps(_example_payload(st.session_state.last_result), indent=2),
                language="json",
            )

    # --- SECTION: TOOL SUGGESTIONS ------------------------------------------
    st.header("Suggested Tools")

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


# --- SIDEBAR (three-area nav) -------------------------------------------------
# One switch for the whole app: Chat / Presentation / Examples. Anything
# area-specific (start a new chat, pick which example) sits right under it so
# each area stays self-contained.
_AREAS = {"Chat": "chat", "Presentation": "presentation", "Examples": "examples"}

with st.sidebar:
    _prev_area = st.session_state.get("area", "chat")
    _area_label = st.radio(
        "Area",
        list(_AREAS),
        index=list(_AREAS.values()).index(_prev_area),
        key="sb_area",
        label_visibility="collapsed",
    )
    area = _AREAS[_area_label]
    st.session_state.area = area
    # Leaving Examples for Chat: don't drag the loaded example into the chat
    # space -- reset to a clean landing and rerun so setdefault() re-seeds
    # `query` before the main area reads it.
    if _prev_area == "examples" and area == "chat" and \
            st.session_state.get("query") in {e["query"] for e in _load_examples()}:
        for _k in ("query", "query_input", "industry", "application", "nature",
                   "categories", "focus_tool", "last_result", "results"):
            st.session_state.pop(_k, None)
        st.rerun()

    st.divider()

    if area == "chat":
        if st.button(
            "New workflow",
            icon=":material/add:",
            key="sb_new_workflow",
            use_container_width=True,
            help="Save the current workflow and start a new one",
        ):
            if _save_workflow(st.session_state.get("last_result")):
                st.toast("Workflow saved", icon=":material/check:")
            for _k in ("query", "query_input", "industry", "application", "nature",
                       "categories", "focus_tool", "last_result", "results", "headline"):
                st.session_state.pop(_k, None)
            st.rerun()

    elif area == "examples":
        _exs = _load_examples()
        if not _exs:
            st.caption("No examples found (examples/*.json).")
        else:
            _by_q = {e["query"]: e for e in _exs}
            _loaded = st.session_state.get("query") if st.session_state.get("query") in _by_q \
                else _exs[0]["query"]
            _pick = st.radio(
                "Example",
                list(_by_q),
                index=list(_by_q).index(_loaded),
                format_func=lambda q: _example_short(_by_q[q]),
                key="sb_example_pick",
                label_visibility="collapsed",
            )
            if st.session_state.get("query") != _pick:
                _open_example(_by_q[_pick])
                st.rerun()

    # area == "presentation": nothing to configure

    st.divider()
    st.button("Settings", icon=":material/settings:", key="sb_settings",
              use_container_width=True, disabled=True)
    st.button("Help", icon=":material/help:", key="sb_help",
              use_container_width=True, disabled=True)


# --- MAIN AREA -------------------------------------------------------------
# Dispatch on the sidebar's `area`. Presentation and Examples fully replace
# the main pane (st.stop()); Chat is the default.

if area == "presentation":
    # The demo-day deck: presentation.md rendered as animated slides. Edit the
    # slides in presentation.md (next to this file) -- Markdown, split by `---`;
    # see the header comment in that file. Push and Streamlit Cloud redeploys.
    _pres = Path(__file__).with_name("presentation.md")
    _md = _pres.read_text() if _pres.exists() else "# Presentation\n\n_presentation.md not found._"
    with st.container(key="tw_readme"):
        if deck_view is not None:
            deck_view(markdown=_md, key="tw_deck")
        else:
            st.markdown(_md)  # fallback: deck component unavailable
    st.stop()

if area == "examples":
    # Curated mock workflows. The sidebar radio keeps exactly one loaded via
    # _open_example(), which pre-seeds st.session_state.results with a matching
    # cache key -- so _render_workflow_result() never calls the backend here.
    _exs = _load_examples()
    if not _exs:
        st.info("No example workflows found (examples/*.json).")
        st.stop()
    if st.session_state.get("query") not in {e["query"] for e in _exs}:
        _open_example(_exs[0])  # first render of the area -- load one
        st.rerun()
    st.caption(
        "Example workflow — curated, no backend call. Switch examples in the sidebar."
    )
    _render_workflow_result(allow_search=False, allow_save=False)
    st.stop()


# --- CHAT AREA -----------------------------------------------------------------
if st.session_state.query:
    _render_workflow_result(allow_search=True, allow_save=True)
else:
    # Landing view: eyebrow + rotating headline + the one big search bar,
    # vertically & horizontally centred (styled in styles.css).
    with st.container(key="tw_landing"):
        st.markdown(
            f"<h1 class='tw-hero-title'>{st.session_state.headline}</h1>",
            unsafe_allow_html=True,
        )
        render_search_bar("hero")
