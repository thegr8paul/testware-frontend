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

# Read Me / demo-day deck -- renders presentation.md as continuously
# scrollable sections (the Dashboard). Guarded: if the component assets are
# ever missing on a deploy, it falls back to plain Markdown instead of
# taking down the whole app.
_DECK_DIR = Path(__file__).with_name("components") / "deck"
try:
    deck_view = components.declare_component("tw_deck", path=str(_DECK_DIR))
except Exception:  # noqa: BLE001
    deck_view = None

# Theme bridge -- an invisible, one-shot component that hydrates
# st.session_state.theme from localStorage on load (see the theme bootstrap
# block below load_css()). Guarded the same way as deck_view.
_THEME_DIR = Path(__file__).with_name("components") / "theme_bridge"
try:
    theme_bridge = components.declare_component("tw_theme_bridge", path=str(_THEME_DIR))
except Exception:  # noqa: BLE001
    theme_bridge = None

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

# testware.dev wordmark, header top-left. Inline SVG + text (not raster
# assets) so it recolors automatically with the theme toggle via
# currentColor / the --tw-* CSS variables in styles.css -- no light/dark PNG
# pair to maintain. Mark: an open-square/bracket outline, gap mid-right edge.
LOGO_HTML = """
<div class="tw-logo">
  <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
    <path d="M20,9 V4 H4 V20 H20 V15" fill="none" stroke="currentColor"
          stroke-width="2.3" stroke-linejoin="miter" stroke-linecap="square"/>
  </svg>
  <span class="tw-wordmark">testware<i>.dev</i></span>
</div>
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
    "background:linear-gradient(100deg,transparent 38%,var(--tw-shimmer) 50%,transparent 62%);"
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
    st.markdown("<style>footer {visibility: hidden;}</style>", unsafe_allow_html=True)


load_css()

# --- THEME (light/dark) -----------------------------------------------------
# st.session_state.theme is the single source of truth ("light" | "dark").
# On first load, the theme_bridge component reports back the last-saved
# choice from localStorage (if any) so a returning visitor's preference
# survives a reload; the header's toggle button just flips this value.
# Every rerun, st.html() (real DOM, unlike sanitized st.markdown) re-syncs
# the <html data-theme> attribute + localStorage from whatever this holds --
# that's what the top-level CSS variables in styles.css key off of, and
# what's passed as `theme=` into the deck / workflow-canvas components below
# so their own iframe-local palettes flip in sync.
st.session_state.setdefault("theme", "light")
if theme_bridge is not None:
    _stored_theme = theme_bridge(key="tw_theme_bridge", default=None)
    if _stored_theme in ("light", "dark") and st.session_state.get("_theme_hydrated") != _stored_theme:
        st.session_state.theme = _stored_theme
        st.session_state["_theme_hydrated"] = _stored_theme
st.html(
    "<script>"
    f"document.documentElement.setAttribute('data-theme', '{st.session_state.theme}');"
    f"try{{localStorage.setItem('tw-theme', '{st.session_state.theme}')}}catch(e){{}}"
    "</script>",
    unsafe_allow_javascript=True,
)

# Fixed backend URL -- override with the API_URL env var.
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


def _current_categories() -> dict:
    """The three picker values as structured fields -- "(Any)" dropped. Only
    ever folded into the query text and shown as chips."""
    picks = {
        "industry": st.session_state.industry,
        "application": st.session_state.application,
        "nature_of_project": st.session_state.nature,
    }
    return {k: v for k, v in picks.items() if v != "(Any)"}


# --- Enhanced query -----------------------------------------------------------
# rag-service's POST /query takes ONE string (rag/schemas.py: QueryRequest,
# min 3 / max 1000 chars) and reuses it for BOTH the vector-retrieval
# embedding AND every generation prompt (answer / diagram / tools). So this
# is not "raw query + appended notes" -- it's one prewritten instruction
# prompt with the raw query and the three dropdown categories filled in as
# parameters, and it is this whole string, not the bare search-bar text,
# that goes over the wire. The instructions are the team's own asks:
#  1. workflow description length
#  2. cap + ground the suggested tools in the catalogue
#  3. build the workflow by combining those same tools
#  4. two-paragraph shape for the description
# Tune the constants below, not the template's structure.

_QUERY_MAX = 1000  # QueryRequest.query max_length; longer -> HTTP 422
_CATEGORY_LABELS = {
    "industry": "Industry",
    "application": "Application",
    "nature_of_project": "Nature of project",
}
_MAX_TOOLS = 6          # instruction 2
_DESC_WORDS = "200-300"  # instruction 1

_PROMPT_TEMPLATE = (
    "Digital-twin project request submitted via testware.dev.\n\n"
    'User prompt: "{query}"\n'
    "{context}"
    "\n"
    "Instructions for this answer:\n"
    "1. Write the workflow description in exactly two paragraphs, "
    "{desc_words} words total.\n"
    "2. Suggest up to {max_tools} relevant products/methods from the "
    "catalogue only -- never invent a tool.\n"
    "3. Build the workflow (flowchart) by combining those same suggested "
    "products, in a logical order."
)


def build_enhanced_query(raw_query: str, categories: dict) -> str:
    """Fill `_PROMPT_TEMPLATE`'s parameters -- {query} (the search-bar text)
    and {context} (the set dropdown categories, `_current_categories()`
    shape) -- and return the finished instruction prompt. This return value
    IS what's POSTed as `query`, not the bare search-bar text.

    Only {query} is ever trimmed (with an ellipsis), and only if the result
    would exceed `_QUERY_MAX`; the instructions and context are short and
    fixed, so they're always sent intact.
    """
    ctx = [f"{_CATEGORY_LABELS.get(k, k)}: {v}"
           for k, v in categories.items() if v and v != "(Any)"]
    context = ("Context: " + " | ".join(ctx) + "\n") if ctx else ""

    fixed_len = len(_PROMPT_TEMPLATE.format(
        query="", context=context, desc_words=_DESC_WORDS, max_tools=_MAX_TOOLS
    ))
    query = (raw_query or "").strip()
    budget = _QUERY_MAX - fixed_len
    if budget <= 0:      # pathological: instructions alone don't fit -- shouldn't happen
        return _PROMPT_TEMPLATE.format(
            query="", context=context, desc_words=_DESC_WORDS, max_tools=_MAX_TOOLS
        )[:_QUERY_MAX]
    if len(query) > budget:
        query = query[: budget - 1].rstrip() + "…"

    return _PROMPT_TEMPLATE.format(
        query=query, context=context, desc_words=_DESC_WORDS, max_tools=_MAX_TOOLS
    )


# Worked example -- what actually goes over the wire for a filled-in search
# (all three categories set). 571 of the 1000-char budget; the rest is
# headroom for a longer prompt. Kept here as living documentation, not
# executed -- see tests/ or run build_enhanced_query() directly to reproduce.
_EXAMPLE_ENHANCED_QUERY = """\
Digital-twin project request submitted via testware.dev.

User prompt: "Predictive-maintenance digital twin for a 400-tonne hydraulic press"
Context: Industry: Manufacturing & Industrial | Application: Predictive maintenance | Nature of project: Consulting / services

Instructions for this answer:
1. Write the workflow description in exactly two paragraphs, 200-300 words total.
2. Suggest up to 6 relevant products/methods from the catalogue only -- never invent a tool.
3. Build the workflow (flowchart) by combining those same suggested products, in a logical order.\
"""  # noqa: E501 -- fixture text, not code


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


def _example_short(ex: dict) -> str:
    """A compact label for the sidebar example picker, e.g.
    '02-ev-battery-pack-thermal' -> 'EV battery pack thermal'."""
    stem = re.sub(r"^\d+[-_]?", "", ex.get("_slug", "") or "")
    words = stem.replace("_", "-").split("-")
    _acronyms = {"ev", "ai", "ml", "cfd", "hpc", "iot", "icme", "ifc"}
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
        with st.container(key="tw_answer"):
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
                placeholder="Build digital twin of complex asset, system, or process",
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


def _render_tool_cards(tools: list, focus_id: str | None = None) -> None:
    """Ranked tool-result cards. Shared by the live Chat result and each
    Examples panel. `focus_id` highlights + expands the card whose
    catalogue_id matches (Chat only -- Examples pass None)."""
    if not tools:
        st.caption("No matching tools found in the catalogue for this query.")
        return
    for tool in tools:  # loop over each ranked tool result
        focused = bool(tool.get("catalogue_id")) and tool["catalogue_id"] == focus_id
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


def _render_workflow_result() -> None:
    """The Chat section's output for a live query: description + editable
    canvas + tool cards."""
    status_slot = render_search_bar("compact")

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
    _cache_key = (st.session_state.query,
                  json.dumps(st.session_state.categories, sort_keys=True))
    _cache = st.session_state.get("results")
    if not (_cache and _cache.get("key") == _cache_key):
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
        st.header("Digital Twin Specification")
        with st.container(key="tw_answer"):
            st.write(description)
        # A previous fetch dropped mid-stream -- offer an explicit retry
        # instead of forcing a full page refresh to try again.
        if _cache.get("ok") is False:
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
        "An interactive multi-node pipeline can be used to add, remove, and modify connections between recommended tools."
        # "accent ring marks tools also in the list below. Click a node to focus "
        # "its card. Drag a node to move it; drag an output dot to an input dot to "
        # "wire; click a wire then Delete (or its ×) to remove it. Drag canvas to "
        # "pan, wheel to zoom."
    )
    _wf_suggested = [t["catalogue_id"] for t in tools if t.get("catalogue_id")]
    if workflow.get("nodes"):
        _sel = workflow_canvas(
            workflow=workflow, suggested=_wf_suggested, key="tw_wf", default=None,
            theme=st.session_state.theme,
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

    # --- SECTION: SAVE AS PITCH EXAMPLE -----------------------------------
    # Capture what's on screen -- query + categories + description + tools +
    # the graph INCLUDING any canvas edits -- as examples/NN-<slug>.json, so a
    # good workflow can be kept and reused as a demo example. Writing to disk
    # only sticks where the disk persists (local dev / always-on host); on
    # Streamlit Community Cloud, copy the JSON into a new repo file instead.
    if workflow.get("nodes"):
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
    _render_tool_cards(tools, st.session_state.get("focus_tool"))


# --- HEADER ------------------------------------------------------------------
# Sticky top bar: logo (left) + theme toggle / LinkedIn / New workflow /
# Settings / Help (right). Replaces the old sidebar nav rail -- the app is
# one continuously-scrolling page now (Chat, then Dashboard, then Examples).
LINKEDIN_URL = "https://www.linkedin.com/company/testware-dev"


def _theme_toggle_button() -> None:
    is_dark = st.session_state.theme == "dark"
    icon = ":material/light_mode:" if is_dark else ":material/dark_mode:"
    if st.button("", icon=icon, key="tw_theme_toggle",
                 help="Switch to light mode" if is_dark else "Switch to dark mode"):
        st.session_state.theme = "light" if is_dark else "dark"
        st.rerun()


def _new_workflow_button() -> None:
    if st.button("", icon=":material/add:", key="tw_new_workflow",
                 help="Save the current workflow and start a new one"):
        if _save_workflow(st.session_state.get("last_result")):
            st.toast("Workflow saved", icon=":material/check:")
        for _k in ("query", "query_input", "industry", "application", "nature",
                   "categories", "focus_tool", "last_result", "results", "headline"):
            st.session_state.pop(_k, None)
        st.rerun()


def render_header() -> None:
    with st.container(key="tw_header", horizontal=True,
                       horizontal_alignment="distribute", vertical_alignment="center"):
        st.markdown(LOGO_HTML, unsafe_allow_html=True)
        with st.container(key="tw_header_actions", horizontal=True, gap="small",
                           vertical_alignment="center"):
            _theme_toggle_button()
            st.link_button("", url=LINKEDIN_URL, icon=":material/link:",
                            key="tw_linkedin", help="LinkedIn")
            _new_workflow_button()
            st.button("", icon=":material/settings:", key="sb_settings",
                      disabled=True, help="Settings — coming soon")
            st.button("", icon=":material/help:", key="sb_help",
                      disabled=True, help="Help — coming soon")


def render_examples_section() -> None:
    """The page's third area: curated example workflows (examples/*.json)
    shown one at a time, exactly as a generated result would look --
    description, editable flowchart canvas, and the suggested-tool cards.
    The chevrons + dots step between examples. Canvas edits are session-only
    and kept per example; they never write back to the JSON files on disk.

    These example workflows are illustrative saved generations for the
    pitch, not delivered projects -- the copy in each file says so."""
    st.header("Examples")
    _exs = _load_examples()
    if not _exs:
        st.caption("No examples found (examples/*.json).")
        return

    n = len(_exs)
    st.session_state.setdefault("tw_examples_idx", 0)
    idx = max(0, min(int(st.session_state["tw_examples_idx"]), n - 1))
    st.session_state["tw_examples_idx"] = idx
    ex = _exs[idx]

    # prev / dots + counter / next
    with st.container(key="tw_examples_nav", horizontal=True,
                       vertical_alignment="center"):
        if st.button("", icon=":material/chevron_left:", key="tw_ex_prev",
                     disabled=idx == 0, help="Previous example"):
            st.session_state["tw_examples_idx"] = idx - 1
            st.rerun()
        _dots = "".join(
            f"<span class='tw-ex-dot{' on' if i == idx else ''}'></span>"
            for i in range(n)
        )
        st.markdown(
            f"<div class='tw-ex-dots'>{_dots}</div>"
            f"<div class='tw-ex-count'>{idx + 1} / {n}</div>",
            unsafe_allow_html=True,
        )
        if st.button("", icon=":material/chevron_right:", key="tw_ex_next",
                     disabled=idx == n - 1, help="Next example"):
            st.session_state["tw_examples_idx"] = idx + 1
            st.rerun()

    # The active example. Keyed by slug so switching fully remounts the panel
    # (fresh canvas, clean fade-in -- see styles.css .st-key-tw_example_panel_*).
    _edits = st.session_state.setdefault("dashboard_example_edits", {})
    with st.container(key=f"tw_example_panel_{ex['_slug']}"):
        st.subheader(_example_short(ex))
        if ex.get("description"):
            st.write(ex["description"])

        st.markdown("#### Workflow")
        _wf = _edits.get(ex["_slug"], ex["workflow"])
        _suggested = [t["catalogue_id"] for t in ex.get("tools", [])
                      if t.get("catalogue_id")]
        _sel = workflow_canvas(
            workflow=_wf, suggested=_suggested, key=f"tw_wf_ex_{ex['_slug']}",
            default=None, theme=st.session_state.theme,
        )
        if isinstance(_sel, dict) and _sel.get("kind") == "edit" and _sel.get("workflow"):
            _edits[ex["_slug"]] = _sel["workflow"]

        st.markdown("#### Suggested tools")
        _render_tool_cards(ex.get("tools", []))


_SCROLL_SETTLE_JS = """
<script>
(function () {
  if (window.__twScrollSettle) return;   // once per page load, survives reruns
  window.__twScrollSettle = true;

  var HEADER = 80;   // == deck HEADER_OFFSET; the line areas align their top to
  var IDS = ["tw_section_chat", "tw_section_dashboard", "tw_section_examples"];

  function scroller() {
    var c = [
      document.querySelector('[data-testid="stAppViewContainer"]'),
      document.querySelector('[data-testid="stMain"]'),
      document.scrollingElement, document.documentElement, document.body
    ];
    for (var i = 0; i < c.length; i++) {
      if (c[i] && c[i].scrollHeight - c[i].clientHeight > 4) return c[i];
    }
    return document.scrollingElement || document.documentElement;
  }
  function isWin(el) {
    return el === document.scrollingElement || el === document.documentElement
        || el === document.body;
  }
  function pos(el) { return isWin(el) ? (window.scrollY || window.pageYOffset) : el.scrollTop; }
  function go(el, top) {
    if (isWin(el)) window.scrollTo({ top: top, behavior: "smooth" });
    else el.scrollTo({ top: top, behavior: "smooth" });
  }

  var t, settling = false, lastPos = null, lastDir = 0;
  var SNAP_NEAR = 150;   // px: "almost aligned" -> finish it
  var FILL = 0.82;       // one area covering this much of the viewport == settled

  function settle() {
    if (settling) return;
    var areas = IDS.map(function (id) { return document.querySelector('.st-key-' + id); })
                   .filter(Boolean);
    if (areas.length < 2) return;
    var vh = window.innerHeight;
    var usable = vh - HEADER;
    var sc = scroller();
    var cur = pos(sc);
    var down = lastDir >= 0;

    // Per area: signed offset of its TOP from the header line, and how much
    // of the usable viewport it currently covers.
    var info = areas.map(function (a, ai) {
      var r = a.getBoundingClientRect();
      var covTop = Math.max(r.top, HEADER);
      var covBot = Math.min(r.bottom, vh);
      return { i: ai, off: r.top - HEADER, frac: Math.max(0, covBot - covTop) / usable };
    });

    // The first area (the searchbar / chat) has nothing above it, so its
    // rest position is scroll 0 -- the very top -- not "top aligned to the
    // header line". Aligning it to HEADER like the other seams leaves you
    // parked ~one header-height below 0 after scrolling back up. So the
    // amount to move to settle onto area 0 is always "back to the top".
    function seam(x) { return x.i === 0 ? -cur : x.off; }

    // Nearest seam to the header line.
    var near = seam(info[0]);
    for (var i = 1; i < info.length; i++) {
      if (Math.abs(seam(info[i])) < Math.abs(near)) near = seam(info[i]);
    }

    // 1. A seam is essentially aligned -> nothing to do.
    if (Math.abs(near) <= 8) return;

    // 2. A seam is close to aligned -> finish it precisely, but only in the
    //    direction the user was already moving (down snaps a seam that is
    //    still below the line; up snaps one just above it). This is what
    //    lands the deck full-canvas without yanking you back when you scroll
    //    on into the next area.
    if (Math.abs(near) <= SNAP_NEAR) {
      if ((down && near > 0) || (!down && near < 0)) {
        settling = true;
        go(sc, Math.round(cur + near));
        setTimeout(function () { settling = false; lastPos = pos(scroller()); }, 550);
      }
      return;
    }

    // 3. Bigger gap. If one area already fills the viewport you're inside it
    //    -- leave it (this is the tall Examples / chat content case).
    for (var k = 0; k < info.length; k++) if (info[k].frac >= FILL) return;

    // 4. Genuinely straddling two areas. Resolve toward the direction of
    //    travel only: down -> align the next area's top; up -> align the top
    //    of the area you're backing into (if it's within ~a screen).
    var target = null;
    info.forEach(function (x) {
      var o = seam(x);
      if (down) {
        if (o > 8 && o < vh && (target === null || o < target)) target = o;
      } else {
        if (o <= 8 && o > -(usable + 40) && (target === null || o > target)) target = o;
      }
    });
    if (target === null || Math.abs(target) <= 8) return;

    settling = true;
    go(sc, Math.round(cur + target));
    setTimeout(function () { settling = false; lastPos = pos(scroller()); }, 550);
  }

  function onScroll() {
    if (settling) return;
    var p = pos(scroller());
    if (lastPos !== null) {
      if (p > lastPos + 1) lastDir = 1;
      else if (p < lastPos - 1) lastDir = -1;
    }
    lastPos = p;
    clearTimeout(t);
    t = setTimeout(settle, 140);   // fire once the scroll has come to rest
  }

  // The scroll container can be re-created across Streamlit reruns; (re)bind
  // defensively, and also listen on window so document-level scrolling is
  // covered whichever element actually scrolls.
  function bind() {
    var sc = scroller();
    if (sc && !sc.__twBound) {
      sc.__twBound = true;
      sc.addEventListener("scroll", onScroll, { passive: true });
    }
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(settle, 200); });
  bind();
  setInterval(bind, 2000);
})();
</script>
"""


def render_scroll_settle() -> None:
    """Keep the page a single continuous scroll, but never let it come to
    rest straddling two of the three areas (app / presentation / examples).
    When the scroll stops mid-transition it resolves the seam ONLY in the
    direction the user was already scrolling -- down finishes the move into
    the next area, up backs out to the previous one. Once a seam has been
    scrolled past, that area is left alone, so scrolling through the tall
    Examples / chat content is never pulled back. Pure viewport behaviour --
    no backend, no state."""
    st.html(_SCROLL_SETTLE_JS, unsafe_allow_javascript=True)


def _count_slides(md: str) -> int:
    """How many slides presentation.md renders -- mirrors the deck parser
    (components/deck/index.html): split on a `---` / `***` line, drop chunks
    that are empty once HTML comments are stripped."""
    chunks = re.split(r"\n[ \t]*(?:-{3,}|\*{3,})[ \t]*\n", md)
    n = sum(1 for c in chunks if re.sub(r"<!--.*?-->", "", c, flags=re.S).strip())
    return max(n, 1)


# A fixed left-edge rail: [app] · [slide 1] … [slide N] · [examples]. The
# first and last stripes are longer (styles.css .edge) so app / examples are
# obvious. Clicking a stripe jumps straight there -- app / examples by
# scrolling this page, slides by calling the deck's window.__deckAPI. Built
# straight onto document.body so Streamlit's reruns never touch it; the
# %SLIDES% token is filled in by render_nav_rail().
_NAV_RAIL_JS = """
<script>
(function () {
  var N = %SLIDES%;                       // presentation slide count
  var HEADER = 80;                        // == deck HEADER_OFFSET
  if (window.__twRail && window.__twRailN === N) return;
  var old = document.getElementById("tw-navrail");
  if (old) old.remove();
  window.__twRail = true;
  window.__twRailN = N;

  var total = N + 2;                      // app + slides + examples
  var rail = document.createElement("nav");
  rail.id = "tw-navrail";
  rail.setAttribute("aria-label", "Page navigation");
  var dots = [];
  for (var i = 0; i < total; i++) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "tw-navrail-dot" + (i === 0 || i === total - 1 ? " edge" : "");
    b.dataset.g = String(i);
    b.setAttribute("aria-label",
      i === 0 ? "Go to app" : i === total - 1 ? "Go to examples" : "Go to slide " + i);
    b.addEventListener("click", function () { navTo(parseInt(this.dataset.g, 10)); });
    rail.appendChild(b);
    dots.push(b);
  }
  (document.body || document.documentElement).appendChild(rail);

  function q(s) { return document.querySelector(s); }

  // --- cold-load layout kick ---------------------------------------------
  // Streamlit bakes each custom-component iframe's *width* to whatever the
  // content column measures at the instant the component first renders, and
  // only re-sends it on an app rerun or a real window `resize`. On a cold
  // reload the deck / workflow iframes routinely mount before the layout has
  // settled (web font swap, custom CSS max-width + header padding applying a
  // tick late, Streamlit's own "running" chrome collapsing), so they latch a
  // too-narrow width and never widen -- the deck shows a blank strip on the
  // right, the workflow canvas frames its graph to a narrow box and parks it
  // top-left with dead space to the right and below. A synthetic `resize`
  // once the width actually changes makes Streamlit re-measure and re-push
  // the correct width to every component (and the deck re-runs its own
  // height calc, which already listens on `resize`). Bounded so it can't
  // feed back on itself. Content-only; no backend involvement.
  if (!window.__twLayoutKick) {
    window.__twLayoutKick = true;
    var kicks = 0, KICK_MAX = 24, kickDeadline = Date.now() + 12000;
    function widthNow() {
      var el = document.querySelector('[data-testid="stAppViewContainer"]')
            || document.querySelector('[data-testid="stMain"]')
            || document.documentElement;
      return el ? el.clientWidth : 0;
    }
    var lastW = widthNow();
    function kick(force) {
      if (kicks >= KICK_MAX || Date.now() > kickDeadline) return;
      var w = widthNow();
      if (!force && w === lastW) return;
      lastW = w;
      kicks++;
      try { window.dispatchEvent(new Event("resize")); } catch (e) {}
    }
    [0, 150, 400, 900, 1800, 3500, 6000].forEach(function (ms) {
      setTimeout(function () { kick(true); }, ms);
    });
    window.addEventListener("load", function () { kick(true); }, { once: true });
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(function () { kick(true); });
    }
    try {
      var kro = new ResizeObserver(function () { kick(false); });
      var kt = document.querySelector('[data-testid="stAppViewContainer"]')
            || document.documentElement;
      if (kt) kro.observe(kt);
      setTimeout(function () { try { kro.disconnect(); } catch (e) {} }, 12000);
    } catch (e) { /* no ResizeObserver -- the timed kicks cover it */ }
  }

  function scroller() {
    var c = [q('[data-testid="stAppViewContainer"]'), q('[data-testid="stMain"]'),
             document.scrollingElement, document.documentElement, document.body];
    for (var i = 0; i < c.length; i++) {
      if (c[i] && c[i].scrollHeight - c[i].clientHeight > 4) return c[i];
    }
    return document.scrollingElement || document.documentElement;
  }
  function isWin(el) {
    return el === document.scrollingElement || el === document.documentElement || el === document.body;
  }
  function toEl(el) {
    if (!el) return;
    var sc = scroller();
    var dy = el.getBoundingClientRect().top - HEADER;
    var cur = isWin(sc) ? (window.scrollY || window.pageYOffset || 0) : sc.scrollTop;
    if (isWin(sc)) window.scrollTo({ top: cur + dy, behavior: "smooth" });
    else sc.scrollTo({ top: cur + dy, behavior: "smooth" });
  }
  function deck() {
    try {
      var f = q(".st-key-tw_readme iframe");
      return (f && f.contentWindow && f.contentWindow.__deckAPI) ? f.contentWindow.__deckAPI : null;
    } catch (e) { return null; }
  }

  function navTo(g) {
    if (g <= 0) { toEl(q(".st-key-tw_section_chat")); return; }
    if (g >= N + 1) { toEl(q(".st-key-tw_section_examples")); return; }
    toEl(q(".st-key-tw_section_dashboard"));
    var d = deck();
    if (d) setTimeout(function () { d.goto(g - 1); }, 60);
  }

  function currentG() {
    var vh = window.innerHeight || document.documentElement.clientHeight;
    var ex = q(".st-key-tw_section_examples");
    if (ex && ex.getBoundingClientRect().top <= vh * 0.5) return N + 1;
    var dash = q(".st-key-tw_section_dashboard");
    if (dash) {
      var r = dash.getBoundingClientRect();
      if (r.top <= vh * 0.5 && r.bottom >= vh * 0.5) {
        var d = deck();
        return 1 + (d ? d.index() : 0);
      }
      if (r.top > vh * 0.5) return 0;
    }
    return 0;
  }
  function sync() {
    var g = currentG();
    for (var i = 0; i < dots.length; i++) dots[i].classList.toggle("on", i <= g);
  }
  window.__twRailSync = sync;

  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () { ticking = false; sync(); });
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  function bindSc() {
    var s = scroller();
    if (s && !s.__twRailBound) { s.__twRailBound = true; s.addEventListener("scroll", onScroll, { passive: true }); }
  }
  bindSc();
  setInterval(bindSc, 2000);
  setInterval(sync, 1000);   // also catches deck slide changes if the notify was missed

  // Arrow Up / Down drives the whole app -> deck -> examples flow while focus
  // is on the page (the deck runs the same handler for when focus is inside
  // its iframe). One key = one step, and the boundaries carry over: from the
  // search area ArrowDown snaps onto the first slide; from the last slide one
  // more ArrowDown continues to Examples (and the mirror going back up).
  window.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    var tag = (e.target && e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || (e.target && e.target.isContentEditable)) return;
    var down = e.key === "ArrowDown";
    var g = currentG();

    if (g < 1) {                       // app / search area
      if (down) { e.preventDefault(); navTo(1); }
      return;
    }
    if (g > N) {                       // Examples area
      if (!down) { e.preventDefault(); navTo(N); }
      return;
    }
    var d = deck();                    // inside the presentation
    if (!d) return;
    var tgt = d.index() + (down ? 1 : -1);
    if (tgt > d.count() - 1) { e.preventDefault(); toEl(q(".st-key-tw_section_examples")); return; }
    if (tgt < 0)             { e.preventDefault(); toEl(q(".st-key-tw_section_chat")); return; }
    e.preventDefault();
    d.goto(tgt);
  });

  sync();
})();
</script>
"""


def render_nav_rail(slide_count: int) -> None:
    """Left-edge page rail: app | each slide | examples. Content-only, built
    directly on document.body; no backend, no state."""
    st.html(_NAV_RAIL_JS.replace("%SLIDES%", str(int(slide_count))),
            unsafe_allow_javascript=True)


# --- PAGE FLOW -----------------------------------------------------------------
# One continuously-scrolling page: header, then the three areas -- Chat,
# Dashboard, Examples. Scrolling is continuous; a scroll-idle "settle"
# (render_scroll_settle, at the end) keeps it from parking between areas.
render_header()

with st.container(key="tw_section_chat"):
    if st.session_state.query:
        _render_workflow_result()
    else:
        # Landing view: eyebrow + rotating headline + the one big search bar,
        # vertically & horizontally centred (styled in styles.css).
        with st.container(key="tw_landing"):
            st.markdown(
                f"<h1 class='tw-hero-title'>{st.session_state.headline}</h1>",
                unsafe_allow_html=True,
            )
            render_search_bar("hero")

with st.container(key="tw_section_dashboard"):
    # The demo-day deck: presentation.md rendered as a one-slide-at-a-time,
    # scroll-snapped section (its own internal viewport -- see
    # components/deck/index.html). Edit the slides in presentation.md (next
    # to this file) -- Markdown, split by `---`; see the header comment in
    # that file. Push and Streamlit Cloud redeploys.
    _pres = Path(__file__).with_name("presentation.md")
    _md = _pres.read_text() if _pres.exists() else "# Dashboard\n\n_presentation.md not found._"
    with st.container(key="tw_readme"):
        if deck_view is not None:
            deck_view(markdown=_md, key="tw_deck", theme=st.session_state.theme)
        else:
            st.markdown(_md)  # fallback: deck component unavailable

with st.container(key="tw_section_examples"):
    render_examples_section()

render_scroll_settle()
render_nav_rail(_count_slides(_md))
