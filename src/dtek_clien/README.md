dtek client

A tiny client script that calls the API server's `/status` endpoint and prints a couple of log lines.

File

- `dtek_client.py` — simple script using `requests`.

Usage

By default the script sends requests to `http://127.0.0.1:8000/status` (see `SERVER_URL` inside the file).

Run directly:

```bash
python -m dtek_clien.dtek_client
```

Or call the `check_my_light` function from your own script:

```py
from dtek_clien.dtek_client import check_my_light
check_my_light('Odesa', 'Nebesnoi Sotni Ave', '79B')
```

Notes

- The client uses the standard `requests` package. Install with `pip install requests` or `pip install -e .` from the repo root.
- The client uses `loguru` for logging. If you prefer the standard library, replace `from loguru import logger` with `import logging` and adjust calls.
