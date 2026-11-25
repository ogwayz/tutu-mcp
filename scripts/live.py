import asyncio
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .client import ROOT, connect, call
from tutu_mcp.errors import checked_at


async def main():
    departure = os.environ.get("LIVE_DATE") or (datetime.now(ZoneInfo("Europe/Moscow")) + timedelta(days=20)).date().isoformat()
    report = dict(implementation="Python", started_at=checked_at(), checks=[])
    path = ROOT / "artifacts" / "python-live.json"
    path.parent.mkdir(exist_ok=True)
    def save():
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    try:
        async with connect() as client:
            report["tools"] = [t.name for t in (await client.list_tools()).tools]
            report["protocol"] = client.protocol_version
            for destination in ["Санкт-Петербург", "Казань"]:
                args = dict(origin="Москва", destination=destination, departure_date=departure)
                print("Searching", args, flush=True)
                result = await call(client, "search_trains", args)
                report["checks"].append(dict(tool="search_trains", args=args, **result)); save()
                assert not result["isError"], result
                trains = result["data"]["trains"]
                train = next((t for t in trains if t["number"] == "022А"), None) or next(
                    (t for t in trains if any(c["type"] == "Купе" for c in t["categories"])), trains[0])
                print("Found", len(trains), "chosen", train["number"], flush=True)
                args = dict(result_id=train["result_id"])
                cars = await call(client, "get_train_seats", args)
                report["checks"].append(dict(tool="get_train_seats", args=args, **cars)); save()
                assert not cars["isError"], cars
                car = next((c for c in cars["data"]["carriages"] if c["type"] == "Купе"), cars["data"]["carriages"][0])
                args = dict(result_id=train["result_id"], carriage_number=car["carriage_number"])
                seats = await call(client, "get_carriage_seats", args)
                report["checks"].append(dict(tool="get_carriage_seats", args=args, **seats)); save()
                assert not seats["isError"], seats
                carriage = seats["data"]["carriage"]
                assert carriage["available"] == len(carriage["seats"])
                matches = [s for s in carriage["seats"] if s["position"] == "lower" and s["price"] and s["price"]["amount"] <= 6000]
                report["checks"].append(dict(scenario="нижнее до 6000 рублей", matches=matches))
                print("Cars", len(cars["data"]["carriages"]), "seats", carriage["available"], "lower <=6000", len(matches), flush=True)
            invalid = await call(client, "search_trains", dict(origin="Москва", destination="Казань", departure_date="2020-01-01"))
            report["checks"].append(dict(scenario="прошедшая дата", **invalid))
            assert invalid["isError"] and invalid["data"]["error"]["code"] == "PAST_DATE"
            report["success"] = True
    finally:
        report["finished_at"] = checked_at()
        save()


if __name__ == "__main__":
    asyncio.run(main())
