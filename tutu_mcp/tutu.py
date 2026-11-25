"""Адаптер публичного интерфейса Туту. Все локаторы сайта изолированы здесь."""
import asyncio
import json
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from .browser import BrowserManager
from .errors import TutuError, checked_at, validate_date
from .parsers import category, decode_state, normalize_seats, site_date

TTL_SECONDS = 15 * 60


def ti(name: str) -> str:
    return f'[data-ti="{name}"]'


# Это небольшие DOM-выражения, выполняемые внутри браузера, не Node.js-сервер.
READ_TRAINS = """es => es.filter(e => !e.querySelector('[data-ti=route-1]')).map(e => {
 const text = name => e.querySelector(`[data-ti="${name}"]`)?.textContent?.trim() || null;
 const point = name => {const n=e.querySelector(`[data-ti="${name}"]`);return {
 date:n?.querySelector('[data-ti=date]')?.textContent?.trim()||null,
 station:n?.querySelector('[data-ti=place]')?.textContent?.trim()||null}};
 return {badge:text('train-name-badge'),departure:point('departure'),arrival:point('arrival'),
 departureTime:text('departure-time'),arrivalTime:text('arrival-time'),duration:text('duration-time'),
 categories:Array.from(e.querySelectorAll('[data-ti=offer-tariffs-table] [data-ti=offer-tariff]')).map(n=>n.innerText),raw:e.innerText};
})"""
READ_CARS = """es=>es.map(e=>{const txt=name=>e.querySelector(`[data-ti="${name}"]`)?.textContent?.trim()||null;
 return {number:txt('car_number'),type:txt('car_type'),availability:txt('seats_count'),
 services:Array.from(e.querySelectorAll('[data-ti^="service-badge-"]')).map(e=>e.textContent?.trim()).filter(Boolean)};})"""
READ_SEATS = """es=>es.map(e=>({number:e.getAttribute('data-ti-seat'),
 state:e.getAttribute('data-ti-state'),type:e.getAttribute('data-ti-type')}))"""


@dataclass
class Stored:
    train: dict
    url: str
    origin: str
    destination: str
    date: str
    expires: float


class TutuAdapter:
    def __init__(self):
        self.browser = BrowserManager()
        self.results: dict[str, Stored] = {}

    async def check(self, page: Page) -> str:
        body = await page.locator("body").inner_text()
        if re.search(r"подтвердите,? что вы|не робот|captcha|доступ ограничен|доступ заблокирован", body, re.I):
            raise TutuError("BLOCKED", "Туту показал проверку или ограничение доступа. Автоматизация остановлена.")
        return body

    async def station(self, page: Page, index: int, value: str) -> str:
        await page.locator(f"{ti('train-search-form')} input").nth(index).fill(value)
        options = page.locator(ti("dropdown-item"))
        try:
            await page.wait_for_function("""value=>Array.from(document.querySelectorAll('[data-ti=dropdown-item]'))
                .some(e=>e.textContent?.toLocaleLowerCase('ru').includes(value.toLocaleLowerCase('ru')))""",
                                         arg=value, timeout=15000)
        except PlaywrightTimeoutError:
            body = await self.check(page)
            if re.search("ничего не найдено|не нашли|не найден", body, re.I):
                raise TutuError("STATION_NOT_FOUND", f"Туту не нашёл станцию «{value}»") from None
            raise TutuError("TIMEOUT", f"Подсказки для «{value}» не загрузились; причина не установлена.") from None
        names = await options.all_text_contents()
        normalize = lambda s: s.strip().lower().replace("ё", "е")
        exact = [(i, name) for i, name in enumerate(names) if normalize(name) == normalize(value)]
        if len(exact) != 1:
            raise TutuError("AMBIGUOUS_STATION" if names else "STATION_NOT_FOUND",
                            f"Уточните город или станцию «{value}»", {"suggestions": names})
        index, name = exact[0]
        await options.nth(index).click()
        return name

    async def select_date(self, page: Page, departure: str):
        await page.locator(ti("trip-dates")).first.click()
        for _ in range(24):
            cells = page.locator(f"{ti('calendar-day-cell')}[data-date]")
            await cells.first.wait_for()
            dates = await cells.evaluate_all("""es=>es.map(e=>({stamp:e.getAttribute('data-date'),
                date:new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Moscow',year:'numeric',month:'2-digit',day:'2-digit'})
                .format(new Date(Number(e.getAttribute('data-date'))))}))""")
            match = next((item for item in dates if item["date"] == departure), None)
            if match:
                cell = page.locator(f'{ti("calendar-day-cell")}[data-date="{match["stamp"]}"]')
                if await cell.get_attribute("data-disabled") == "true":
                    raise TutuError("INVALID_DATE", "Дата недоступна в календаре Туту; причина не установлена.")
                await cell.click()
                await page.locator(ti("calendar-popper-footer-select-button")).click()
                return
            if dates[-1]["date"] > departure:
                raise TutuError("INVALID_DATE", "Дата отсутствует в календаре")
            await page.locator(ti("calendar-month-header-next-button")).click()
            await page.wait_for_function("""before=>document.querySelector('[data-ti=calendar-day-cell][data-date]')
                ?.getAttribute('data-date')!==before""", arg=dates[0]["stamp"])
        raise TutuError("INVALID_DATE", "Дата вне поддерживаемого диапазона календаря (24 месяца).")

    async def load_listing(self, page: Page) -> bool | None:
        for _ in range(20):
            count = await page.locator(ti("offer-card")).count()
            await page.evaluate("""()=>{const es=document.querySelectorAll('[data-ti=offer-card]');
                es[es.length-1]?.scrollIntoView({block:'center'});} """)
            try:
                await page.wait_for_function("n=>document.querySelectorAll('[data-ti=offer-card]').length>n",
                                             arg=count, timeout=4000)
            except PlaywrightTimeoutError:
                await self.check(page)
                return None  # Прекращение роста не доказывает полноту выдачи.
        return False

    async def empty_state(self, page: Page):
        body = await self.check(page)
        rules = [
            (r"продажа.*(?:не открыта|откроется)|продажи.*начнутся", "SALES_NOT_OPEN", "Продажа ещё не открыта"),
            (r"прямых поездов нет|нет прямых поездов|поезда не найдены|не нашли поезд", "NO_DIRECT_TRAINS", "Туту сообщил, что прямых поездов нет"),
            (r"все билеты.*(?:проданы|раскуплены)|места распроданы", "SOLD_OUT", "Туту сообщил, что места распроданы"),
        ]
        for pattern, code, message in rules:
            if re.search(pattern, body, re.I):
                raise TutuError(code, message)
        raise TutuError("TIMEOUT", "Туту не загрузил данные за 45 секунд; причина не установлена.",
                        {"url": page.url, "page_text": body[:2000]})

    async def search(self, origin: str, destination: str, departure: str) -> dict:
        validate_date(departure)
        async with self.browser.lock, self.browser.page() as page:
            self.results = {key: value for key, value in self.results.items() if value.expires > time.monotonic()}
            await page.goto("https://www.tutu.ru/poezda/", wait_until="networkidle", timeout=45000)
            await self.check(page)
            origin = await self.station(page, 0, origin)
            destination = await self.station(page, 1, destination)
            await self.select_date(page, departure)
            await page.locator(ti("submit-button")).first.click()
            await page.wait_for_url(re.compile(r"[?&]date="))
            try:
                await page.locator(ti("offer-card")).first.wait_for(timeout=45000)
            except PlaywrightTimeoutError:
                await self.empty_state(page)
            listing = await self.load_listing(page)
            raw = await page.locator(f'{ti("offer-card")}[data-ti-product="train"]').evaluate_all(READ_TRAINS)
            if not raw:
                raise TutuError("SITE_CHANGED", "На странице не найдены распознаваемые карточки прямых поездов")
            checked = checked_at()
            trains = []
            for item in raw:
                badge = re.match(r"^(\S+)\s*(.*)$", item["badge"] or "")
                if not badge:
                    raise TutuError("SITE_CHANGED", "Не найден номер поезда")
                result_id = str(uuid4())
                warnings = ["Часовые пояса не установлены; время приведено как на сайте.",
                            "Цена и наличие могут измениться до оформления."]
                if re.search("двухэтаж", item["raw"], re.I):
                    warnings.insert(0, "Поезд двухэтажный; этаж места требует отдельного подтверждения.")
                train = dict(result_id=result_id, number=badge[1], name=badge[2] or None,
                             departure=dict(date=departure, time=item["departureTime"], timezone=None,
                                            station=item["departure"]["station"]),
                             arrival=dict(date=site_date(item["arrival"]["date"], departure), time=item["arrivalTime"],
                                          timezone=None, station=item["arrival"]["station"]),
                             duration=item["duration"], categories=[category(text) for text in item["categories"]],
                             source_url=page.url, checked_at=checked, warnings=warnings)
                self.results[result_id] = Stored(train, page.url, origin, destination, departure, time.monotonic() + TTL_SECONDS)
                trains.append(train)
            return dict(origin=origin, destination=destination, departure_date=departure, trains=trains,
                        checked_at=checked, expires_at=datetime.fromtimestamp(time.time() + TTL_SECONDS, timezone.utc).isoformat(),
                        listing_complete=listing, warnings=[
                            "Достигнут лимит догрузки: выдача неполная." if listing is False else
                            "Список догружен до прекращения роста; сайт не сообщает явный признак полноты выдачи.",
                            "Прямые поезда, включая проходящие. Пересадки не подбираются."])

    def stored(self, result_id: str) -> Stored:
        result = self.results.get(result_id)
        if result is None or result.expires < time.monotonic():
            raise TutuError("STALE_RESULT", "Результат устарел или сервер перезапущен. Повторите search_trains.")
        return result

    @asynccontextmanager
    async def seats_page(self, result_id: str):
        async with self.browser.lock, self.browser.page() as page:
            result = self.stored(result_id)
            await page.goto(result.url, wait_until="domcontentloaded")
            await page.locator(ti("offer-card")).first.wait_for(timeout=45000)
            await self.check(page)
            card = page.locator(ti("offer-card")).filter(has=page.locator(ti("train-name-badge")).filter(
                has_text=re.compile(r"^" + re.escape(result.train["number"]) + r"(?:\s|$)")))
            if await card.count() == 0:
                await self.load_listing(page)
            if await card.count() != 1:
                raise TutuError("STALE_RESULT", "Поезд больше не найден в выдаче. Повторите поиск.")
            # Кнопка может открыть новую вкладку либо выполнить переход в текущей.
            popup_task = asyncio.create_task(page.wait_for_event("popup", timeout=10000))
            try:
                await card.get_by_role("button", name="Выбрать места", exact=True).click()
                try:
                    seat_page = await popup_task
                except PlaywrightTimeoutError:
                    seat_page = page
            finally:
                if not popup_task.done():
                    popup_task.cancel()
                await asyncio.gather(popup_task, return_exceptions=True)
            await seat_page.wait_for_load_state("domcontentloaded")
            try:
                await seat_page.locator(ti("car_card")).first.wait_for(timeout=45000)
            except PlaywrightTimeoutError:
                await self.empty_state(seat_page)
            await self.check(seat_page)
            yield seat_page, result

    async def seats(self, result_id: str) -> dict:
        self.stored(result_id)  # Устаревший UUID не должен даже запускать браузер.
        async with self.seats_page(result_id) as (page, result):
            raw = await page.locator(ti("car_card")).evaluate_all(READ_CARS)
            cars = []
            for item in raw:
                number = re.search(r"\d+", item["number"] or "")
                count = re.search(r"\d+", item["availability"] or "")
                cars.append(dict(carriage_number=number[0] if number else None, type=item["type"],
                                 available=int(count[0]) if count else None,
                                 availability_text=item["availability"], services=item["services"]))
            return dict(result_id=result_id, train=result.train,
                        route=dict(origin=result.origin, destination=result.destination, departure_date=result.date),
                        carriages=cars, source_url=page.url, checked_at=checked_at(), warnings=[
                            "Для номеров мест и полок вызовите get_carriage_seats.", "Наличие может измениться до оформления."])

    async def carriage(self, result_id: str, number: str) -> dict:
        self.stored(result_id)
        async with self.seats_page(result_id) as (page, result):
            chosen = None
            for card in await page.locator(ti("car_card")).all():
                match = re.search(r"\d+", await card.locator(ti("car_number")).first.inner_text())
                if match and match[0] == number:
                    chosen = card
                    break
            if chosen is None:
                raise TutuError("STALE_RESULT", "Вагон не найден; обновите get_train_seats.")
            await chosen.get_by_role("button", name="Выбрать", exact=True).click()
            expanded = page.locator(ti("car_card_expanded"))
            await expanded.locator(ti("full-scheme")).wait_for()
            dom = await expanded.locator("[data-ti-seat]").evaluate_all(READ_SEATS)
            if not dom:
                raise TutuError("SITE_CHANGED", "Не удалось прочитать номера мест раскрытой схемы")
            data = json.loads(await page.locator("#__NEXT_DATA__").inner_text())
            state = decode_state(data.get("props", {}).get("pageProps", {}).get("initialState"))
            seats = normalize_seats(dom, state, number)
            count = re.search(r"\d+", await expanded.locator(ti("seats_count")).first.inner_text())
            if count and int(count[0]) != len(seats):
                raise TutuError("SITE_CHANGED", "Число активных мест схемы не совпало с количеством в карточке.",
                                {"card": int(count[0]), "scheme": len(seats)})
            d = state.dictionaries
            car = next(c for c in d.cars.values() if c.number == number)
            hashes = dict.fromkeys(d.seatsGroups[key].serviceClassHash for key in car.seatsGroups if key in d.seatsGroups)
            classes = [d.serviceClasses[key] for key in hashes if key in d.serviceClasses]
            if len(d.segments) != 1:
                raise TutuError("SITE_CHANGED", "Страница не подтверждает единственный прямой участок")
            segment = next(iter(d.segments.values()))
            services = []
            for cls in classes:
                services.extend([cls.description, cls.petRules])
                services.extend(d.services[key].label for key in map(str, cls.services) if key in d.services)
            return dict(result_id=result_id, train=result.train["number"],
                        route=dict(origin=result.origin, destination=result.destination, departure_date=result.date,
                                   departure_utc=segment.departureDateTime, arrival_utc=segment.arrivalDateTime,
                                   departure_timezone=d.points[str(segment.departureId)].tzName,
                                   arrival_timezone=d.points[str(segment.arrivalId)].tzName),
                        carriage=dict(number=number, type=await expanded.locator(ti("car_type")).first.inner_text(),
                                      service_class=", ".join(cls.name for cls in classes), available=len(seats), seats=seats,
                                      services=list(dict.fromkeys(s for s in services if s))),
                        source_url=page.url, checked_at=checked_at(), warnings=[
                            "Этаж и пол купе возвращаются null: коды не проверены для всех схем.",
                            "Цена обычного взрослого тарифа может отличаться от рекламной цены со скидкой.",
                            "Места могут измениться до оформления."])
