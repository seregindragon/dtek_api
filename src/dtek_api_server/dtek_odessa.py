#!/usr/bin/env python3
"""
DTEK Odesa electric networks — outage checker for three addresses.

Run:
  uv run src/dtek_api_server/dtek_odessa.py           # normal mode
  uv run src/dtek_api_server/dtek_odessa.py --debug   # with detailed logs and screenshots
"""

import argparse
import asyncio
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

# ── Arguments ────────────────────────────────────────────────────────────────
parser: argparse.ArgumentParser = argparse.ArgumentParser(description="DTEK Odesa — outage checker")
_ = parser.add_argument(
    "--debug", action="store_true",
    help="Detailed logs + screenshots"
)

args = parser.parse_args()

DEBUG: bool = args.debug

# ── Logging ─────────────────────────────────────────────────────────────────
logger.remove()
_ = logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="DEBUG" if DEBUG else "INFO",
)

# ── Constants ────────────────────────────────────────────────────────────────
SITE = "https://www.dtek-oem.com.ua/ua/shutdowns"

ADDRESSES: list[dict[str, str]] = [
    #{"city": "м. Одеса", "street": "просп. небесної сотні", "house": "79Б"}#,
    {"city": "м. Одеса", "street": "вул. Палія семена",     "house": "93"}#,
    #{"city": "м. Одеса", "street": "вул. Кримська",         "house": "64"},
]

CITY_SEL   = ".discon-input-wrapper input#city"
STREET_SEL = ".discon-input-wrapper input#street"
HOUSE_SEL  = ".discon-input-wrapper input#house_num"

SCREENSHOTS = Path("debug_screenshots")
_shot_counter = 0


async def screenshot(page, name: str) -> None:
    if not DEBUG:
        return
    global _shot_counter
    _shot_counter += 1
    SCREENSHOTS.mkdir(exist_ok=True)
    path = SCREENSHOTS / f"{_shot_counter:02d}_{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    logger.debug(f"  📸 {path.name}")


def ensure_playwright() -> None:
    _ = subprocess.run(
        ["playwright", "install", "chromium", "--with-deps"],
        capture_output=True, text=True,
    )


def banner(i: int, addr: dict[str, str]) -> None:
    logger.info("━" * 58)
    logger.info(f"#{i}  {addr['street']}, {addr['house']}  ({addr['city']})")
    logger.info("━" * 58)


async def close_popup(page):
    from playwright.async_api import TimeoutError as PWTimeout
    await asyncio.sleep(2)
    for sel in [
        "button.modal__close", "button.popup__close",
        "[class*='modal'] [class*='close']", "[class*='popup'] [class*='close']",
        "button:has-text('×')", "button:has-text('✕')",
        "[aria-label='Close']", ".modal button", ".popup button",
    ]:
        try:
            btn = await page.wait_for_selector(sel, timeout=2_000, state="visible")
            await btn.click()
            logger.info("Popup closed ✓")
            await asyncio.sleep(1.5)
            return
        except PWTimeout:
            continue
    await page.keyboard.press("Escape")
    await asyncio.sleep(1)


async def click_first_autocomplete_item(page) -> str | None:
    """Click the first visible .autocomplete-items entry using the mouse."""
    item = await page.evaluate("""
        () => {
            const containers = document.querySelectorAll('.autocomplete-items');
            for (const container of containers) {
                const st = window.getComputedStyle(container);
                if (st.display === 'none' || st.visibility === 'hidden') continue;
                const child = container.firstElementChild;
                if (!child) continue;
                const rect = child.getBoundingClientRect();
                if (rect.width < 5 || rect.height < 5) continue;
                return {
                    text: child.textContent.trim(),
                    x: rect.left + rect.width / 2,
                    y: rect.top + rect.height / 2,
                };
            }
            // Fallback
            for (const el of document.querySelectorAll('.autocomplete')) {
                const st = window.getComputedStyle(el);
                if (st.display === 'none') continue;
                for (const child of el.children) {
                    if (window.getComputedStyle(child).display === 'none') continue;
                    const rect = child.getBoundingClientRect();
                    if (rect.width < 10 || rect.height < 10 || rect.top < 50) continue;
                    const text = child.textContent.trim();
                    if (!text || text.length < 2) continue;
                    return { text, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
                }
            }
            return null;
        }
    """)

    if item:
        logger.debug(f"  ✅ Item: '{item['text'][:60]}' @ ({item['x']:.0f},{item['y']:.0f})")
        await page.mouse.move(item["x"], item["y"])
        await asyncio.sleep(0.1)
        await page.mouse.click(item["x"], item["y"])
        return item["text"]
    return None


async def autocomplete_select(page, css: str, value: str, label: str, addr_idx: int) -> bool:
    # Wait until the field becomes enabled
    for attempt in range(20):
        is_enabled = await page.evaluate(f"""
            () => {{ const el = document.querySelector('{css}'); return el ? !el.disabled : false; }}
        """)
        if is_enabled:
            break
        logger.debug(f"  ⏳ Waiting for enabled: {label} ({attempt+1}/20)…")
        await asyncio.sleep(0.5)
    else:
        logger.warning(f"  ⚠️  {label} remains disabled!")
        return False

    loc = page.locator(css).first
    await loc.scroll_into_view_if_needed()
    await asyncio.sleep(0.3)

    await loc.click(click_count=3)
    await page.keyboard.press("Backspace")
    await asyncio.sleep(0.2)

    for char in value:
        await page.keyboard.type(char, delay=80)

    logger.debug(f"  ⌨️  Typed '{value}'")
    await asyncio.sleep(2.5)

    await screenshot(page, f"addr{addr_idx}_{label}_typed")

    clicked = await click_first_autocomplete_item(page)
    if clicked:
        logger.info(f"  ✔  {label}: {clicked[:70]}")
        await asyncio.sleep(1.5)
        await screenshot(page, f"addr{addr_idx}_{label}_selected")
        return True

    logger.warning(f"  ↩  '{label}': fallback ArrowDown+Enter")
    await page.keyboard.press("ArrowDown")
    await asyncio.sleep(0.4)
    await page.keyboard.press("Enter")
    await asyncio.sleep(1.0)
    return False


async def extract_result(page) -> dict[str, str | list[str]]:
    result: dict[str, str | list[str]] = {}
    body = await page.inner_text("body")

    m = re.search(r"Черга\s+([\d.]+)", body, re.I)
    if m:
        result["queue"] = f"Queue {m.group(1)}"

    kw = re.compile(
        (
            r"(відсутня електроенерг|є електроенерг|аварійн|стабіліз|ремонтн"
            r"|причина\s*[:–]|час початку|час відновлення|орієнтовний час"
            r"|дата оновлення\s*–|не зафіксовано|не передбачен"
            r"|відключення за вашою|поточних відключень немає)"
        ),
        re.I,
    )
    lines = [line.strip() for line in body.splitlines() if line.strip() and kw.search(line)]
    if lines:
        result["lines"] = lines[:15]

    return result


async def check_address(context, addr: dict[str, str], idx: int) -> None:
    from playwright.async_api import TimeoutError as PWTimeout

    page = await context.new_page()
    try:
        logger.debug("Loading page…")
        await page.goto(SITE, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(2)

        await screenshot(page, f"addr{idx}_loaded")
        await close_popup(page)
        await screenshot(page, f"addr{idx}_popup_closed")

        try:
            await page.locator(CITY_SEL).first.wait_for(timeout=15_000, state="visible")
        except PWTimeout:
            logger.error("Form not found")
            await screenshot(page, f"addr{idx}_ERROR_no_form")
            return

        await asyncio.sleep(0.8)


        on_req  = None
        if DEBUG:
            async def on_req(req):
                if "dtek-oem" in req.url and req.resource_type in ("xhr", "fetch"):
                    logger.debug(f"  🌐 {req.method} {req.url}")
            page.on("request", on_req)

        _ = await autocomplete_select(page, CITY_SEL,   addr["city"],   "City",   idx)
        await asyncio.sleep(1)
        _ = await autocomplete_select(page, STREET_SEL, addr["street"], "Street",  idx)
        await asyncio.sleep(1)
        _ = await autocomplete_select(page, HOUSE_SEL,  addr["house"],  "House", idx)
        await asyncio.sleep(2)

        if DEBUG and on_req is not None:
            page.remove_listener("request", on_req)

        await screenshot(page, f"addr{idx}_result")

        result = await extract_result(page)
        logger.info("─" * 40)
        if "queue" in result:
            logger.success(f"🔢  {result['queue']}")
        if "lines" in result:
            for line in result["lines"]:
                logger.info(f"📋  {line}")
        if not result:
            logger.warning("⚠️  No data received")

    except Exception as e:
        await screenshot(page, f"addr{idx}_EXCEPTION")
        logger.exception(f"Error: {e}")
    finally:
        await page.close()


async def async_main():
    """Async main logic for DTEK Odesa CLI."""
    from playwright.async_api import async_playwright

    logger.info("🔌  DTEK Odesa power networks — outage status")
    logger.info(f"🕐  {datetime.now().strftime('%d.%m.%Y  %H:%M:%S')}")
    if DEBUG:
        logger.debug("🐛  Debug mode enabled")
        logger.debug(f"📁  Screenshots: {SCREENSHOTS.resolve()}")

    ensure_playwright()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not DEBUG,  # in debug mode — show the browser
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            locale="uk-UA",
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        for i, addr in enumerate(ADDRESSES, 1):
            banner(i, addr)
            await check_address(context, addr, i)

        await browser.close()

    logger.success("✅  Check complete")


def main():
    """Entry point for the dtek-cli command (synchronous wrapper)."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
