dtek API server

This folder contains a FastAPI server that uses Playwright to query DTEK shutdowns and expose status via HTTP.

Files

- `dtek_api_server.py` — main server implementation (FastAPI app). Key endpoints:
  - GET /status?city=&street=&house=
  - GET /status/all
  - GET /health

Requirements

- Python 3.11+
- Playwright and a browser (chromium recommended)

Installation

From the repository root (macOS / zsh):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m playwright install chromium
```

Run server

Start with uvicorn:

```bash
uvicorn dtek_api_server.dtek_api_server:app --host 0.0.0.0 --port 8000
```

Or directly:

```bash
python -m dtek_api_server.dtek_api_server
```

Notes

- The server creates a Playwright browser at lifespan startup and closes it at shutdown. Expect a few seconds delay on cold start while the browser boots.
- If you run the server in an environment that blocks sandboxing, the code already sets `--no-sandbox` and disables automation detection flags.
- If you see issues locating the form on the DTEK website, the page structure may have changed — the CSS selectors are defined at the top of `dtek_api_server.py` (CITY_SEL, STREET_SEL, HOUSE_SEL). Update them if necessary.

