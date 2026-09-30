"""Core data structures for a family tree laid out in space and time."""

from __future__ import annotations

import datetime as _dt
import math
import re
from dataclasses import dataclass, field

_YEAR_RE = re.compile(r"^(\d{3,4})$")
_YM_RE = re.compile(r"^(\d{3,4})-(\d{1,2})$")
_YMD_RE = re.compile(r"^(\d{3,4})-(\d{1,2})-(\d{1,2})$")

_CUM_DAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


class DateParseError(ValueError):
    """Raised when a date value cannot be understood."""


def parse_date(value: object) -> float:
    """Normalize ``1842``, ``"1842-05"``, ``"1842-05-03"`` or a ``date`` to a fractional year."""
    if value is None:
        raise DateParseError("date is missing")
    if isinstance(value, _dt.datetime):
        value = value.date()
    if isinstance(value, _dt.date):
        return _to_fractional(value.year, value.month, value.day)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value

    text = str(value).strip()
    if m := _YMD_RE.match(text):
        return _to_fractional(int(m[1]), int(m[2]), int(m[3]))
    if m := _YM_RE.match(text):
        return _to_fractional(int(m[1]), int(m[2]), 1)
    if m := _YEAR_RE.match(text):
        return float(int(m[1]))
    raise DateParseError(f"unrecognized date {value!r} (use YYYY, YYYY-MM or YYYY-MM-DD)")


def _to_fractional(year: int, month: int, day: int) -> float:
    if not 1 <= month <= 12:
        raise DateParseError(f"month out of range in {year}-{month}-{day}")
    if not 1 <= day <= 31:
        raise DateParseError(f"day out of range in {year}-{month}-{day}")
    return year + (_CUM_DAYS[month - 1] + day - 1) / 365.0


def format_year(year: float | None) -> str:
    return "?" if year is None else str(int(math.floor(year)))


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    lat: float
    lon: float
    country: str = ""

    @property
    def label(self) -> str:
        return f"{self.name}, {self.country}" if self.country else self.name


@dataclass(frozen=True)
class Event:
    """A dated event at a place. Either field may be unknown."""

    year: float | None = None
    place_id: str | None = None


@dataclass(frozen=True)
class Move:
    year: float
    place_id: str


@dataclass
class Person:
    id: str
    name: str
    sex: str = ""
    birth: Event = field(default_factory=Event)
    death: Event = field(default_factory=Event)
    parents: tuple[str, ...] = ()
    residences: tuple[Move, ...] = ()
    notes: str = ""

    @property
    def birth_year(self) -> float | None:
        return self.birth.year

    @property
    def death_year(self) -> float | None:
        return self.death.year

    def is_alive(self, year: float) -> bool:
        if self.birth.year is None or year < self.birth.year:
            return False
        return self.death.year is None or year < self.death.year

    @property
    def lifespan_label(self) -> str:
        born = format_year(self.birth.year)
        died = format_year(self.death.year) if self.death.year is not None else ""
        return f"{born}\u2013{died}"


@dataclass
class FamilyTree:
    root_id: str
    people: dict[str, Person]
    places: dict[str, Place]

    def __post_init__(self) -> None:
        self._children: dict[str, list[str]] = {pid: [] for pid in self.people}
        for person in self.people.values():
            for parent_id in person.parents:
                if parent_id in self._children:
                    self._children[parent_id].append(person.id)

    @property
    def root(self) -> Person:
        return self.people[self.root_id]

    def children_of(self, person_id: str) -> list[Person]:
        return [self.people[c] for c in self._children.get(person_id, ())]

    def place(self, place_id: str | None) -> Place | None:
        return self.places.get(place_id) if place_id else None

    def ancestor_depths(self, person_id: str | None = None) -> dict[str, int]:
        """Map each direct ancestor of ``person_id`` to its generation distance (root itself = 0)."""
        start = person_id or self.root_id
        depths: dict[str, int] = {start: 0}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            for parent_id in self.people[current].parents:
                if parent_id not in self.people:
                    continue
                depth = depths[current] + 1
                if depth < depths.get(parent_id, 1 << 30):
                    depths[parent_id] = depth
                    frontier.append(parent_id)
        return depths

    def generation_depths(self) -> dict[str, int]:
        """Generation distance from the root for every person, ancestors first then everyone else."""
        depths = self.ancestor_depths()
        for person in self.people.values():
            if person.id in depths:
                continue
            # Non-ancestors (siblings, cousins) inherit depth from their nearest known parent.
            depths[person.id] = _derive_depth(person.id, self.people, depths, set())
        return depths

    def date_bounds(self) -> tuple[float, float]:
        years = [p.birth.year for p in self.people.values() if p.birth.year is not None]
        years += [p.death.year for p in self.people.values() if p.death.year is not None]
        years += [m.year for p in self.people.values() for m in p.residences]
        if not years:
            raise ValueError("family tree contains no dated events")
        return min(years), max(years)


def _derive_depth(
    person_id: str,
    people: dict[str, Person],
    depths: dict[str, int],
    seen: set[str],
) -> int:
    if person_id in depths:
        return depths[person_id]
    if person_id in seen:
        return 0
    seen.add(person_id)
    parent_depths = [
        _derive_depth(p, people, depths, seen) for p in people[person_id].parents if p in people
    ]
    depths[person_id] = min(parent_depths) - 1 if parent_depths else 0
    return depths[person_id]
