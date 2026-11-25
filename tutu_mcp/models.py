"""Контракты публичных данных страницы. Неизвестные поля сайта игнорируются."""
from typing import Any, Literal
from pydantic import BaseModel, Field


class Price(BaseModel):
    amount: float
    currency: Literal["RUB"] = "RUB"
    kind: Literal["from", "exact", "unknown"] = "unknown"
    conditions: str | None = None


class Seat(BaseModel):
    number: str
    position: Literal["lower", "upper", "sitting", "unknown"]
    floor: int | None = None
    compartment: str | None = None
    gender: str | None = None
    price: Price | None = None
    evidence: str


class Money(BaseModel):
    currencyCode: str
    amount: int = Field(ge=0)
    precision: int = Field(ge=0, le=4)


class Car(BaseModel):
    hash: str
    number: str
    seatsGroups: list[str]


class SiteSeat(BaseModel):
    number: str
    compartmentNumber: int | None = None
    deck: int | None = None
    genderType: int | None = None


class SeatGroup(BaseModel):
    carHash: str
    serviceClassHash: str
    seats: list[SiteSeat]


class ServiceClass(BaseModel):
    name: str
    description: str | None = None
    petRules: str | None = None
    services: list[int] = Field(default_factory=list)


class Service(BaseModel):
    label: str


class FarePrice(BaseModel):
    total: Money
    fareDiscounts: list[Any]


class Fare(BaseModel):
    seatGroupHash: str
    passengerHash: str
    fareType: int
    price: FarePrice


class Passenger(BaseModel):
    type: int


class Segment(BaseModel):
    departureId: int
    arrivalId: int
    departureDateTime: str
    arrivalDateTime: str


class Point(BaseModel):
    tzName: str | None = None


class Dictionaries(BaseModel):
    cars: dict[str, Car]
    seatsGroups: dict[str, SeatGroup]
    serviceClasses: dict[str, ServiceClass]
    services: dict[str, Service]
    fareApplications: dict[str, Fare]
    passengers: dict[str, Passenger]
    segments: dict[str, Segment]
    points: dict[str, Point]


class SiteState(BaseModel):
    dictionaries: Dictionaries
