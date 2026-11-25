import asyncio
import os
import anyio
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright
from .errors import TutuError


class BrowserManager:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.playwright = None
        self.browser = None

    @asynccontextmanager
    async def page(self):
        context = None
        try:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
            if self.browser is None:
                self.browser = await self.playwright.chromium.launch(
                    channel=os.environ.get("BROWSER_CHANNEL", "chrome"),
                    headless=os.environ.get("HEADED") != "1",
                )
            context = await self.browser.new_context(
                locale="ru-RU", timezone_id=os.environ.get("USER_TIMEZONE", "Europe/Moscow")
            )
            page = await context.new_page()
            page.set_default_timeout(15000)
            page.set_default_navigation_timeout(45000)
        except Exception as exc:
            if context:
                await context.close()
            raise TutuError("SITE_UNAVAILABLE", f"Не удалось запустить браузер: {exc}") from exc
        try:
            yield page
        finally:
            with anyio.CancelScope(shield=True):
                await context.close()

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
        finally:
            self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
