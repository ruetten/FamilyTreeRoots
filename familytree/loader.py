"""Read YAML sources into a :class:`FamilyTree` and report everything wrong at once."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .model import DateParseError, Event, FamilyTree, Move, Person, Place, parse_date


class FamilyDataError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} problem(s) in family data")


def load_yaml(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_places(path: str | Path) -> dict[str, Place]:
    raw = load_yaml(path) or {}
    places: dict[str, Place] = {}
    for place_id, data in raw.items():
        places[place_id] = Place(
            id=place_id,
            name=data.get("name", place_id),
            lat=float(data["lat"]),
            lon=float(data["lon"]),
            country=data.get("country", ""),
        )
    return places


def load_tree(family_path: str | Path, places_path: str | Path) -> FamilyTree:
    """Load and validate a tree, raising :class:`FamilyDataError` with every problem found."""
    places = load_places(places_path)
    raw = load_yaml(family_path) or {}
    errors: list[str] = []

    people: dict[str, Person] = {}
    for entry in raw.get("people", []):
        person, person_errors = _build_person(entry)
        errors.extend(person_errors)
        if person is None:
            continue
        if person.id in people:
            errors.append(f"duplicate person id {person.id!r}")
            continue
        people[person.id] = person

    root_id = raw.get("root")
    if not root_id:
        errors.append("top-level 'root' key is missing (it names the person everything converges into)")
    elif root_id not in people:
        errors.append(f"root {root_id!r} is not among the people")

    errors.extend(_validate_references(people, places))
    errors.extend(_validate_chronology(people))
    errors.extend(_validate_acyclic(people))

    if errors:
        raise FamilyDataError(errors)

    return FamilyTree(root_id=root_id, people=people, places=places)


def _build_person(entry: dict[str, Any]) -> tuple[Person | None, list[str]]:
    errors: list[str] = []
    person_id = entry.get("id")
    if not person_id:
        return None, [f"person entry without an 'id': {entry!r}"]

    def event(key: str) -> Event:
        data = entry.get(key) or {}
        if not isinstance(data, dict):
            errors.append(f"{person_id}: '{key}' must be a mapping with 'date' and 'place'")
            return Event()
        year = None
        if data.get("date") is not None:
            try:
                year = parse_date(data["date"])
            except DateParseError as exc:
                errors.append(f"{person_id}: {key} date - {exc}")
        return Event(year=year, place_id=data.get("place"))

    residences: list[Move] = []
    for move in entry.get("residences") or []:
        try:
            residences.append(Move(year=parse_date(move["from"]), place_id=move["place"]))
        except (DateParseError, KeyError, TypeError) as exc:
            errors.append(f"{person_id}: bad residence entry {move!r} - {exc}")
    residences.sort(key=lambda m: m.year)

    parents = tuple(entry.get("parents") or ())
    if len(parents) > 2:
        errors.append(f"{person_id}: has {len(parents)} parents, expected at most 2")

    person = Person(
        id=person_id,
        name=entry.get("name", person_id),
        sex=entry.get("sex", ""),
        birth=event("birth"),
        death=event("death"),
        parents=parents,
        residences=tuple(residences),
        notes=entry.get("notes", ""),
    )
    return person, errors


def _validate_references(people: dict[str, Person], places: dict[str, Place]) -> list[str]:
    errors: list[str] = []
    locatable_parents = {
        parent_id
        for person in people.values()
        if person.birth.place_id
        for parent_id in person.parents
    }
    for person in people.values():
        for label, place_id in _place_refs(person):
            if place_id and place_id not in places:
                errors.append(f"{person.id}: unknown place {place_id!r} in {label}")
        for parent_id in person.parents:
            if parent_id not in people:
                errors.append(f"{person.id}: unknown parent {parent_id!r}")
        if person.birth.year is None:
            errors.append(f"{person.id}: missing birth date")
        # An unknown birthplace is fine as long as we can place them somewhere on the map.
        if not any(place_id for _, place_id in _place_refs(person)) and person.id not in locatable_parents:
            errors.append(f"{person.id}: no known place at all, so they cannot be drawn")
    return errors


def _place_refs(person: Person):
    yield "birth", person.birth.place_id
    yield "death", person.death.place_id
    for move in person.residences:
        yield f"residence from {int(move.year)}", move.place_id


def _validate_chronology(people: dict[str, Person]) -> list[str]:
    errors: list[str] = []
    for person in people.values():
        birth, death = person.birth.year, person.death.year
        if birth is not None and death is not None and death < birth:
            errors.append(f"{person.id}: death {int(death)} precedes birth {int(birth)}")
        for move in person.residences:
            if birth is not None and move.year < birth:
                errors.append(f"{person.id}: moves in {int(move.year)}, before being born in {int(birth)}")
            if death is not None and move.year > death:
                errors.append(f"{person.id}: moves in {int(move.year)}, after dying in {int(death)}")
        for parent_id in person.parents:
            parent = people.get(parent_id)
            if parent is None or birth is None:
                continue
            if parent.birth.year is not None and parent.birth.year >= birth:
                errors.append(
                    f"{person.id}: parent {parent_id} born {int(parent.birth.year)}, "
                    f"not before child's birth {int(birth)}"
                )
            if parent.death.year is not None and parent.death.year < birth:
                errors.append(
                    f"{person.id}: parent {parent_id} died {int(parent.death.year)}, "
                    f"before child's birth {int(birth)}"
                )
    return errors


def _validate_acyclic(people: dict[str, Person]) -> list[str]:
    errors: list[str] = []
    WHITE, GREY, BLACK = 0, 1, 2
    color = dict.fromkeys(people, WHITE)

    def visit(person_id: str, path: list[str]) -> None:
        color[person_id] = GREY
        for parent_id in people[person_id].parents:
            if parent_id not in people:
                continue
            if color[parent_id] == GREY:
                cycle = path[path.index(parent_id):] if parent_id in path else [parent_id]
                errors.append("ancestry cycle: " + " -> ".join([*cycle, parent_id]))
            elif color[parent_id] == WHITE:
                visit(parent_id, [*path, parent_id])
        color[person_id] = BLACK

    for person_id in people:
        if color[person_id] == WHITE:
            visit(person_id, [person_id])
    return errors
