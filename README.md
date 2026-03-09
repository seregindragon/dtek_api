# dtek — DTEK Odesa — outage checker

This repository provides a small project that scrapes DTEK (dtek-oem) shutdown information and exposes it via a FastAPI server. A tiny client script calls that server for a single saved address example.

Overview

- Server: a FastAPI app using Playwright to query https://www.dtek-oem.com.ua/ua/shutdowns and extract outage information.
  - Source: `src/dtek_api_server/dtek_api_server.py`
  - Endpoints: `/status`, `/health`.
- Client: a tiny helper script that queries the server.
  - Source: `src/dtek_clien/dtek_client.py`

Requirements

- Python 3.11+
- The project dependencies are declared in `pyproject.toml`.
- Playwright (browsers) must be installed separately (see below).

Quick setup

1. Create and activate a virtual environment (macOS / zsh):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install the package (editable) and dependencies:

```bash
pip install -e .
```

3. Install Playwright browsers (required by the server):

```bash
python -m playwright install
```

If you only need a specific browser (chromium):

```bash
python -m playwright install chromium
```

Running the server

There are several ways to start the API server.

Recommended (direct uvicorn):

```bash
uvicorn dtek_api_server.dtek_api_server:app --host 0.0.0.0 --port 8000
```

Or run the module directly (this uses the `if __name__ == "__main__"` block in the file):

```bash
python -m dtek_api_server.dtek_api_server
```


API examples

- Check a specific address (URL-encode parameters):

```bash
curl "http://127.0.0.1:8000/status?city=Odesa&street=Nebesnoi+Sotni+Ave&house=79B"
```

- Health:

```bash
curl http://127.0.0.1:8000/health
```

Client

The repository contains a tiny client script which requests the `/status` endpoint. See `src/dtek_clien/dtek_client.py`.

Run it directly:

```bash
python -m dtek_clien.dtek_client
```

or using the provided (installed) entrypoint `dtek-client` if you installed the package in your environment.

Troubleshooting

- If the server logs indicate Playwright cannot find browser binaries, run `python -m playwright install`.
- Make sure the Python environment uses Python 3.11+.
- The server opens a headless browser; on CI or restricted environments you might need to supply extra launch args (e.g. `--no-sandbox`).

License

This repository contains example code; add a license file if you plan to redistribute.
