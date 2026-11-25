"""Предметные MCP-инструменты. stdout используется исключительно протоколом."""
import asyncio
import json
import logging
import signal
from typing import Annotated, Awaitable, Callable
import anyio
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from .errors import TutuError, checked_at
from .tutu import TutuAdapter

adapter = TutuAdapter()
server = MCPServer(
    "tutu-trains", version="0.2.0", instructions=(
        "Поиск только прямых поездов Туту. При пожелании нижней полки получите вагоны, затем get_carriage_seats. "
        "Не оформляйте заказ. Результаты действуют 15 минут в рамках этого процесса."
    ), log_level="WARNING",
)
annotations = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=False, open_world_hint=True)
Station = Annotated[str, Field(min_length=1, max_length=150, pattern=r"\S")]
ResultId = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")]
CarNumber = Annotated[str, Field(pattern=r"^\d{1,3}$")]


async def invoke(fn: Callable[[], Awaitable[dict]]) -> CallToolResult:
    try:
        result = await fn()
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
                              structured_content=result)
    except Exception as exc:
        if isinstance(exc, TutuError):
            error = exc
        else:
            code = "TIMEOUT" if isinstance(exc, (PlaywrightTimeoutError, TimeoutError)) else (
                "SITE_UNAVAILABLE" if any(x in str(exc) for x in ["net::", "ENOTFOUND", "ECONN"]) else "SITE_CHANGED")
            error = TutuError(code, str(exc))
        logging.warning("[tutu] %s: %s", error.code, error)
        result = dict(error=dict(code=error.code, message=str(error), details=error.details), checked_at=checked_at())
        return CallToolResult(is_error=True, content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))])


@server.tool(annotations=annotations, structured_output=False)
async def search_trains(origin: Station, destination: Station, departure_date: str) -> CallToolResult:
    """Найти прямые поезда на живом Туту. result_id действует 15 минут; полнота выдачи не гарантируется."""
    return await invoke(lambda: adapter.search(origin.strip(), destination.strip(), departure_date))


@server.tool(annotations=annotations, structured_output=False)
async def get_train_seats(result_id: ResultId) -> CallToolResult:
    """Получить перечень вагонов поезда. Для конкретных мест и полок вызовите get_carriage_seats."""
    return await invoke(lambda: adapter.seats(result_id))


@server.tool(annotations=annotations, structured_output=False)
async def get_carriage_seats(result_id: ResultId, carriage_number: CarNumber) -> CallToolResult:
    """Раскрыть вагон и прочитать активные свободные места, полки, купе и обычные взрослые цены."""
    return await invoke(lambda: adapter.carriage(result_id, carriage_number))


async def run():
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        await server.run_stdio_async()
    finally:
        with anyio.CancelScope(shield=True):
            await adapter.browser.close()
        loop.remove_signal_handler(signal.SIGTERM)


def main():
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(run())
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
