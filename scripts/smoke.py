import asyncio
from .client import connect, call


async def main():
    async with connect() as client:
        tools = await client.list_tools()
        assert sorted(t.name for t in tools.tools) == ["get_carriage_seats", "get_train_seats", "search_trains"]
        print("stdio listTools: OK; protocol", client.protocol_version)
        for date, code in [("2026-02-30", "INVALID_DATE"), ("2020-01-01", "PAST_DATE")]:
            result = await call(client, "search_trains", dict(origin="Москва", destination="Казань", departure_date=date))
            assert result["isError"] and result["data"]["error"]["code"] == code, result
            print(code, "OK")
        result = await call(client, "get_train_seats", dict(result_id="00000000-0000-4000-8000-000000000000"))
        assert result["isError"] and result["data"]["error"]["code"] == "STALE_RESULT", result
        print("STALE_RESULT: OK")
        result = await call(client, "get_carriage_seats", dict(result_id="bad", carriage_number="2"))
        assert result["isError"], result
        print("Input validation: OK")


if __name__ == "__main__":
    asyncio.run(main())
