"""Сверка обычных цен в рамках одной живой сессии. К оформлению не переходит."""
import asyncio
import json
import math
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .client import ROOT
from tutu_mcp.errors import checked_at
from tutu_mcp.parsers import decode_state, normalize_seats
from tutu_mcp.tutu import TutuAdapter, ti, READ_SEATS


async def main():
    adapter = TutuAdapter()
    departure = os.environ.get("LIVE_DATE") or (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(days=20)).date().isoformat()
    try:
        search = await adapter.search("Москва", "Санкт-Петербург", departure)
        train = next((t for t in search["trains"] if t["number"] == "022А"), None) or next(
            t for t in search["trains"] if any(c["type"] == "Купе" for c in t["categories"]))
        async with adapter.seats_page(train["result_id"]) as (page, result):
            cookie = page.locator(ti("agree-button"))
            if await cookie.count() and await cookie.first.is_visible():
                await cookie.first.click()
            card = page.locator(ti("car_card")).filter(has=page.locator(ti("car_type")).filter(has_text="Купе")).first
            number = (await card.locator(ti("car_number")).first.inner_text()).split()[0]
            await card.get_by_role("button", name="Выбрать", exact=True).click()
            expanded = page.locator(ti("car_card_expanded"))
            await expanded.locator(ti("full-scheme")).wait_for()
            dom = await expanded.locator("[data-ti-seat]").evaluate_all(READ_SEATS)
            state = decode_state(json.loads(await page.locator("#__NEXT_DATA__").inner_text())["props"]["pageProps"]["initialState"])
            seats = normalize_seats(dom, state, number)
            candidates = [s for s in seats if s["price"]][:3]
            assert len(candidates) == 3, "Недостаточно мест с однозначной обычной ценой для сверки"
            report = dict(checked_at=checked_at(), train=train["number"], departure_date=departure,
                          carriage_number=number, source_url=page.url, comparisons=[], available=len(seats),
                          sold_out=[s["number"] for s in dom if s["state"] == "sold_out"])
            for seat in candidates:
                element = expanded.locator(f'[data-ti-seat="{seat["number"]}"]')
                await element.click()
                await page.wait_for_function("""expected=>document.querySelector('[data-ti=next-step-sticky]')
                    ?.textContent?.replace(/[\s\u2060]/g,'').includes(String(expected))""", arg=math.ceil(seat["price"]["amount"]))
                summary = await page.locator(ti("next-step-sticky")).inner_text()
                report["comparisons"].append(dict(seat=seat, visible_summary=summary))
                await page.screenshot(path=str(ROOT / "artifacts" / f'python-ui-seat-{seat["number"]}.png'), timeout=15000)
                await element.click()
            (ROOT / "artifacts" / "python-ui-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        await adapter.browser.close()


if __name__ == "__main__":
    asyncio.run(main())
