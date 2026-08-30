"""Local mock of the RAG backend so the Streamlit UI can be developed offline.

Not used in production. Standard library only -- no extra dependency.

Run:
    make mock                 # ~2s delay
    make mock_slow            # 20s delay, to exercise the "thinking" cue
    MOCK_DELAY=0 make mock    # instant, for fast UI iteration

Point the frontend's sidebar "RAG API URL" at http://localhost:8000
(that is already the default).

If a file `mock_response.json` sits next to this script it is returned
verbatim for POST /query -- drop a real captured backend response there to
preview real content. Otherwise the built-in CANNED payload below is used;
it deliberately includes one fully-populated tool and one sparse tool so the
`—` fallbacks in app.py get exercised.
"""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DELAY = int(os.environ.get("MOCK_DELAY", "2"))
PORT = int(os.environ.get("MOCK_PORT", "8000"))
RESPONSE_FILE = Path(__file__).with_name("mock_response.json")

HEALTH = {"status": "ok", "collection": "mock", "document_count": 0}

CANNED = {
    "query": "mock",
    "answer": (
        "**Mock answer.** For a hydraulic-press digital twin aimed at predictive "
        "maintenance you would combine a physics-based press model with a "
        "data-driven degradation model, fed by pressure, stroke and temperature "
        "telemetry. The two tools below are illustrative catalogue hits.\n\n"
        "This text comes from mock_api.py, not the real RAG backend."
    ),
    "sources": [
        {
            "source_file": "catalogue/press_models.jsonl",
            "page": 12,
            "session_date": "2025-12-01",
            "excerpt": "Reduced-order model of a 400t hydraulic press ...",
        }
    ],
    "tools": [
        {
            "name": "PressTwin RO",
            "rationale": (
                "Reduced-order structural model of hydraulic presses; pairs well "
                "with a degradation estimator for predictive maintenance."
            ),
            "development_status": "actively maintained",
            "access_type": "commercial",
            "fidelity_tier": "reduced-order",
            "spatial_scale": "~1 mm – ~3 m",
            "temporal_scale": "~1 ms – ~1 h",
            "validation_level": "validated against rig data",
            "pricing": {
                "estimate_low": 400.0,
                "estimate_high": 900.0,
                "currency": "USD",
                "unit": "per seat/month",
                "notes": "Model estimate -- catalogue has no pricing field.",
                "estimated": True,
            },
            "known_fail_modes": [
                "Extrapolates poorly outside the calibrated load range",
                "Assumes rigid tooling",
            ],
            "inputs": ["Ram force", "Stroke position", "Oil temperature"],
            "outputs": ["Frame stress field", "Fatigue index"],
            "standards": ["FMI 2.0", "ISO 10303"],
            "docs_url": "https://example.com/presstwin",
            "alternatives": ["OpenPress", "FEMPress"],
        },
        {
            "name": "BareTool (sparse record)",
            "rationale": "Sparse catalogue entry -- used to check the UI null fallbacks.",
            "development_status": None,
            "access_type": None,
            "fidelity_tier": None,
            "spatial_scale": None,
            "temporal_scale": None,
            "validation_level": None,
            "pricing": {
                "estimate_low": 0.0,
                "estimate_high": 0.0,
                "currency": "USD",
                "unit": "per seat/month",
                "notes": "Unknown -- model estimate.",
                "estimated": True,
            },
            "known_fail_modes": [],
            "inputs": [],
            "outputs": [],
            "standards": [],
            "docs_url": None,
            "alternatives": [],
        },
    ],
    "pipeline_diagram": (
        "graph LR\n"
        "  T[Telemetry] --> P[PressTwin RO]\n"
        "  P --> D[Degradation model]\n"
        "  D --> A[Maintenance alert]"
    ),
    "architecture_diagram": (
        "graph TD\n"
        "  Sensors --> Ingest\n"
        "  Ingest --> Twin[Digital Twin]\n"
        "  Twin --> Dashboard"
    ),
}


def _payload() -> bytes:
    if RESPONSE_FILE.exists():
        return RESPONSE_FILE.read_bytes()
    return json.dumps(CANNED).encode()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._send(200, json.dumps(HEALTH).encode())
        else:
            self._send(404, b'{"detail":"not found"}')

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        if self.path.rstrip("/") == "/query":
            try:
                sent = json.loads(raw or b"{}").get("query", "")
            except json.JSONDecodeError:
                sent = "<unparseable>"
            print(f"POST /query  delay={DELAY}s  query={sent!r}", flush=True)
            time.sleep(DELAY)
            src = "mock_response.json" if RESPONSE_FILE.exists() else "canned"
            print(f"  -> 200 ({src})", flush=True)
            self._send(200, _payload())
        else:
            self._send(404, b'{"detail":"not found"}')

    def log_message(self, *args):  # silence default per-request noise
        pass


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"mock RAG API listening on :{PORT}  (MOCK_DELAY={DELAY}s)", flush=True)
    print("point the Streamlit sidebar 'RAG API URL' at http://localhost:%d" % PORT, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping", flush=True)
        server.shutdown()


if __name__ == "__main__":
    main()
