#!/usr/bin/env python3
"""
DTEK — electricity outage checker.

Run:
uv run src/dtek_check/dtek_api.py
uvicorn dtek_check.dtek_api:app --host 0.0.0.0async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:async def fetch_status(city: str, street: str, house: str) -> dict[str, Any]: --port 8000
"""

import asyncio
import re
from contextlib import asynccontextmanager
from typing import Any, Dict, AsyncGenerator

import uvicorn
from fastapi import FastAPI, HTTPException
from loguru import logger
from playwright.async_api import Browser, async_playwright

SITE       = "https://www.dtek-oem.com.ua/ua/shutdowns"
CITY_SEL   = ".discon-input-wrapper input#city"
STREET_SEL = ".discon-input-wrapper input#street"
HOUSE_SEL  = ".discon-input-wrapper input#house_num"

# Default city (English label)
DEFAULT_CITY = "м. Одеса"

SAVED_ADDRESSES: list[Any] = []

state: Dict[str, Any] = {}


POWER_OFF_UK = "відсутня електроенергія"
POWER_ON_UK_1 = "є електроенергія"
POWER_ON_UK_2 = "поточних відключень немає"
QUEUE_UK_RE = r"черга\s+([\d.]+)"
DETAILS_UK_RE = r"(причина\s*[:–]|час початку|час відновлення|орієнтовний час|аварійн|ремонтн|дата оновлення\s*–)"


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI)-> Generator[None, Any, None]:
    logger.info("🚀 Starting browser...")
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    state["browser"] = browser
    state["playwright"] = playwright
    logger.info("✅ Ready")
    yield
    await browser.close()
    await playwright.stop()
    logger.info("🛑 Browser stopped")


app = FastAPI(
    title="DTEK API",
    description="Check electricity outages",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Playwright helpers ────────────────────────────────────────────────────────
async def _close_popup(page) -> None:
    from playwright.async_api import TimeoutError as PWTimeout
    await asyncio.sleep(1.5)
    for sel in [
        "button.modal__close", "button.popup__close",
        "[class*='modal'] [class*='close']", "[class*='popup'] [class*='close']",
        "button:has-text('×')", "button:has-text('✕')", "[aria-label='Close']",
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=1_500, state="visible")
            await btn.click()
            await asyncio.sleep(0.8)
            return
        except PWTimeout:
            continue
    await page.keyboard.press("Escape")


async def _wait_enabled(page, css: str) -> bool:
    for _ in range(20):
        enabled = await page.evaluate(
            f"() => {{ const el = document.querySelector('{css}'); return el ? !el.disabled : false; }}"
        )
        if enabled:
            return True
        await asyncio.sleep(0.4)
    return False


async def _select(page, css: str, value: str) -> bool:
    if not await _wait_enabled(page, css):
        return False

    loc = page.locator(css).first
    await loc.scroll_into_view_if_needed()
    await loc.click(click_count=3)
    await page.keyboard.press("Backspace")
    await asyncio.sleep(0.1)

    for char in value:
        await page.keyboard.type(char, delay=60)
    await asyncio.sleep(2.5)

    item = await page.evaluate("""
        () => {
            for (const c of document.querySelectorAll('.autocomplete-items')) {
                if (window.getComputedStyle(c).display === 'none') continue;
                const child = c.firstElementChild;
                if (!child) continue;
                const r = child.getBoundingClientRect();
                if (r.width < 5 || r.height < 5) continue;
                return { text: child.textContent.trim(), x: r.left + r.width/2, y: r.top + r.height/2 };
            }
            return null;
        }
    """)

    if item:
        await page.mouse.move(item["x"], item["y"])
        await asyncio.sleep(0.1)
        await page.mouse.click(item["x"], item["y"])
        await asyncio.sleep(1.2)
        return True

    await page.keyboard.press("ArrowDown")
    await asyncio.sleep(0.3)
    await page.keyboard.press("Enter")
    await asyncio.sleep(0.8)
    return False


# ── Main logic ────────────────────────────────────────────────────────────
async def fetch_status(city: str, street: str, house: str) -> dict:
    browser: Browser = state["browser"]

    context = await browser.new_context(
        locale="uk-UA",
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page = await context.new_page()

    try:
        await page.goto(SITE, wait_until="domcontentloaded", timeout=60_000)
        await _close_popup(page)

        from playwright.async_api import TimeoutError as PWTimeout
        try:
            await page.locator(CITY_SEL).first.wait_for(timeout=15_000, state="visible")
        except PWTimeout:
            raise RuntimeError("Form not found on the page")

        await asyncio.sleep(0.5)
        await _select(page, CITY_SEL,   city)
        await _select(page, STREET_SEL, street)
        await _select(page, HOUSE_SEL,  house)
        await asyncio.sleep(2.0)

        body = await page.inner_text("body")
        body_lower = body.lower()

        # Status detection: prefer Ukrainian phrases (site is Ukrainian), but
        # accept English equivalents if present.
        if POWER_OFF_UK in body_lower or "power is off" in body_lower:
            status, message = "OFF", "Power is OFF"
        elif (
            POWER_ON_UK_1 in body_lower
            or POWER_ON_UK_2 in body_lower
            or "power is on" in body_lower
            or "no current shutdowns" in body_lower
        ):
            status, message = "ON", "Power is ON"
        else:
            status, message = "UNKNOWN", "Unable to determine status"

        # Queue (try Ukrainian then English)
        m = re.search(QUEUE_UK_RE, body, re.I) or re.search(r"queue\s+([\d.]+)", body, re.I)
        queue = m.group(1) if m else None

        # Details: look for lines that mention reasons, times, or update timestamps.
        details_re = re.compile(
            rf"({DETAILS_UK_RE}|reason\s*[:–]|start time|restoration time|estimated time|emergenc|repair|date updated\s*–)",
            re.I,
        )
        details = [line.strip() for line in body.splitlines() if line.strip() and details_re.search(line)][:6]

        dict_return = {"city":    city,
            "street":  street,
            "house":   house,
            "status":  status,
            "message": message,
            "queue":   queue,
            "details": details
                       }

        return dict_return

    finally:
        await context.close()


# ── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/status")
async def check_status(
    street: str,
    house: str,
    city: str = DEFAULT_CITY,
):
    """
    Check outage status for an address.

    - **city** *(optional)*: locality. Default: `м. Одеса`
    - **street** *(required)*: street name, e.g. `просп. Небесної Сотні`
    - **house** *(required)*: house number, e.g. `123`
    """
    logger.info(f"GET /status  {city}, {street}, {house}")
    try:
        return await fetch_status(city, street, house)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"ok": True, "browser_ready": "browser" in state}


# ── Run ────────────────────────────────────────────────────────────────────
def main():
    # Use the correct module path for the uvicorn entry-point declared in pyproject.toml
    uvicorn.run("dtek_api_server.dtek_api_server:app", host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

