import re
from decimal import Decimal
from pydantic import ValidationError
from .errors import TutuError
from .models import Price, Seat, SiteState


def parse_price(text: str) -> dict | None:
    clean = re.sub(r"[\s\u2060]", "", text)
    match = re.search(r"(\d+(?:[.,]\d{1,2})?)(?:₽|руб)", clean, re.I)
    if not match:
        return None
    return Price(
        amount=float(match[1].replace(",", ".")),
        kind="from" if text.strip().lower().startswith("от") else "unknown",
        conditions=text if re.search(r"кошел|карт|скид|промо|СБП", text, re.I) else None,
    ).model_dump()


def position_from_label(label: str) -> str:
    for pattern, position in [("нижн", "lower"), ("верхн", "upper"), ("сидяч", "sitting")]:
        if re.search(pattern, label, re.I):
            return position
    return "unknown"


def explicit_availability(label: str) -> bool | None:
    if re.search("занят|недоступ|продан", label, re.I):
        return False
    if re.search("свобод|доступн", label, re.I):
        return True
    return None


def site_date(text: str | None, departure: str) -> str | None:
    match = re.search(r"(\d{1,2})\s+([а-я]+)", text or "", re.I)
    if not match:
        return None
    months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    month = next((i + 1 for i, name in enumerate(months) if match[2].startswith(name)), None)
    if month is None:
        return None
    year = int(departure[:4]) + (month < int(departure[5:7]))
    return f"{year}-{month:02d}-{int(match[1]):02d}"


def decode_state(data) -> SiteState:
    try:
        return SiteState.model_validate(data)
    except ValidationError as exc:
        raise TutuError("SITE_CHANGED", "Структура публичных данных страницы выбора мест изменилась.",
                        exc.errors(include_url=False, include_input=False)[:3]) from exc


def normalize_seats(dom: list[dict], state: SiteState, car_number: str) -> list[dict]:
    d = state.dictionaries
    car = next((c for c in d.cars.values() if c.number == car_number), None)
    if car is None:
        raise TutuError("SITE_CHANGED", "Вагон схемы отсутствует в данных страницы")
    result = []
    for item in dom:
        if item["state"] != "active":
            continue
        groups = [(key, d.seatsGroups[key]) for key in car.seatsGroups
                  if key in d.seatsGroups and any(s.number == item["number"] for s in d.seatsGroups[key].seats)]
        key, group = groups[0] if len(groups) == 1 else (None, None)
        detail = next((s for s in group.seats if s.number == item["number"]), None) if group else None
        amounts = set()
        for fare in d.fareApplications.values():
            passenger = d.passengers.get(fare.passengerHash)
            if (key and fare.seatGroupHash == key and passenger and passenger.type == 0
                    and fare.fareType == 0 and not fare.price.fareDiscounts
                    and fare.price.total.currencyCode == "RUB"):
                money = fare.price.total
                amounts.add(Decimal(money.amount) / (10 ** money.precision))
        price = Price(amount=float(next(iter(amounts))), kind="exact", conditions=(
            "Обычный взрослый тариф из price.total для группы этого места; без условной платёжной скидки. "
            "Итог подтвердится при оформлении."
        )) if len(amounts) == 1 else None
        result.append(Seat(
            number=item["number"], position={"bottom": "lower", "top": "upper", "sitting": "sitting"}.get(item["type"], "unknown"),
            compartment=str(detail.compartmentNumber) if detail and detail.compartmentNumber is not None else None,
            price=price, evidence=f"DOM data-ti-state=active; data-ti-type={item['type']}; купе из seatsGroups. Этаж и пол не интерпретированы.",
        ).model_dump())
    return result


def category(text: str) -> dict:
    def count(pattern):
        match = re.search(pattern, text)
        return int(match[1]) if match else None
    lower, upper, total = count(r"(\d+)\s*ниж"), count(r"(\d+)\s*верх"), count(r"(\d+)\s*мест")
    price = parse_price(text)
    if price:
        price.update(kind="from", conditions="Цена из выдачи; условия скидки и способ оплаты не установлены. Не цена каждого места.")
    return dict(type=text.split("\n")[0], lower=lower, upper=upper, price=price,
                available=0 if "Мест нет" in text else total if total is not None else
                (lower or 0) + (upper or 0) if lower is not None or upper is not None else None)
