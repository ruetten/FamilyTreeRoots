"""Builds the sample family tree shipped for testing and writes it to ``data/family.yaml``.

A single unbroken line of descent, 1800 to 2000: Dalarna -> Stockholm -> Bergen -> Hamburg
-> Paris -> Chicago -> Minneapolis. Each generation is one couple who merge into one child.
Replace this file's output with your own research.
"""

from __future__ import annotations

from pathlib import Path

Move = tuple[str, str]  # (year-ish date, place id)


def _p(
    pid: str,
    name: str,
    sex: str,
    birth: str,
    birth_place: str,
    death: str | None = None,
    death_place: str | None = None,
    parents: tuple[str, ...] = (),
    residences: tuple[Move, ...] = (),
    notes: str = "",
) -> dict:
    return {
        "id": pid,
        "name": name,
        "sex": sex,
        "birth": (birth, birth_place),
        "death": (death, death_place),
        "parents": parents,
        "residences": residences,
        "notes": notes,
    }


ROOT = "ego"

PEOPLE: list[dict] = [
    # --- generation 1: Dalarna, Sweden -------------------------------------
    _p("olof_1800", "Olof Andersson", "M", "1800-03-14", "dalarna",
       "1871-09-02", "dalarna"),
    _p("kerstin_1803", "Kerstin Larsdotter", "F", "1803-07-21", "dalarna",
       "1868-11-19", "dalarna"),

    # --- generation 2: the move to the capital ------------------------------
    _p("anders_1830", "Anders Olofsson", "M", "1830-05-08", "dalarna",
       "1899-02-27", "stockholm", parents=("olof_1800", "kerstin_1803"),
       residences=(("1855-04-01", "stockholm"),)),
    _p("brita_1833", "Brita Jonsdotter", "F", "1833-10-02", "uppsala",
       "1905-06-14", "stockholm",
       residences=(("1854-09-12", "stockholm"),)),

    # --- generation 3: across to Norway -------------------------------------
    _p("sven_1858", "Sven Andersson", "M", "1858-01-19", "stockholm",
       "1930-12-05", "bergen", parents=("anders_1830", "brita_1833"),
       residences=(("1882-05-20", "gothenburg"), ("1883-08-03", "bergen"))),
    _p("marit_1861", "Marit Sørensen", "F", "1861-04-27", "trondheim",
       "1934-03-22", "bergen",
       residences=(("1880-06-15", "bergen"),)),

    # --- generation 4: shipyard work in Germany -----------------------------
    _p("olav_1886", "Olav Svensson", "M", "1886-09-11", "bergen",
       "1957-07-08", "hamburg", parents=("sven_1858", "marit_1861"),
       residences=(("1911-03-06", "hamburg"),)),
    _p("greta_1889", "Greta Vogel", "F", "1889-11-30", "berlin",
       "1962-01-17", "hamburg",
       residences=(("1910-05-22", "hamburg"),)),

    # --- generation 5: out of Europe in 1939 --------------------------------
    _p("heinrich_1915", "Heinrich Svensson", "M", "1915-06-23", "hamburg",
       "1994-05-11", "chicago", parents=("olav_1886", "greta_1889"),
       residences=(
           ("1936-09-04", "strasbourg"),
           ("1937-04-18", "paris"),
           ("1939-07-02", "le_havre"),
           ("1939-08-26", "new_york"),
           ("1940-02-10", "chicago"),
       ),
       notes="Left Le Havre weeks before the war closed the Atlantic."),
    _p("cecile_1918", "Cécile Laurent", "F", "1918-02-14", "lyon",
       "1999-10-03", "chicago",
       residences=(
           ("1936-10-11", "paris"),
           ("1939-07-02", "le_havre"),
           ("1939-08-26", "new_york"),
           ("1940-02-10", "chicago"),
       )),

    # --- generation 6: the American midwest ---------------------------------
    _p("henry_1944", "Henry Severin", "M", "1944-08-05", "chicago",
       "2018-04-19", "minneapolis", parents=("heinrich_1915", "cecile_1918"),
       residences=(("1970-06-01", "minneapolis"),)),
    _p("jeanne_1947", "Jeanne Rousseau", "F", "1947-03-30", "chicago",
       residences=(("1970-06-01", "minneapolis"),)),

    # --- generation 7: parents ----------------------------------------------
    _p("erik_1972", "Erik Severin", "M", "1972-02-20", "minneapolis",
       parents=("henry_1944", "jeanne_1947")),
    _p("marie_1975", "Marie Hoffmann", "F", "1975-09-03", "minneapolis"),

    # --- generation 8: me -----------------------------------------------------
    _p("ego", "Alva Severin", "F", "2000-04-12", "minneapolis",
       parents=("erik_1972", "marie_1975"),
       notes="That's me."),
]

_HEADER = """\
# Sample family tree. Regenerate with: python -m familytree.cli generate
#
# Schema
#   root: <id>                        the person the finale converges into
#   people:
#     - id: unique_key
#       name: Display Name
#       sex: M | F | ''
#       birth:  {date: YYYY[-MM[-DD]], place: <id from places.yaml>}
#       death:  {date: ..., place: ...}   omit entirely if still living
#       parents: [id, id]                 0, 1 or 2 entries
#       residences:                       optional; where they were between events
#         - {from: YYYY[-MM[-DD]], place: <id>}
#
# Locations you do not record are inferred: a person is assumed to have been
# present at each of their children's births.
"""


def build_yaml() -> str:
    lines = [_HEADER, f"root: {ROOT}", "", "people:"]
    for person in PEOPLE:
        lines.append(f"  - id: {person['id']}")
        lines.append(f"    name: {_scalar(person['name'])}")
        if person["sex"]:
            lines.append(f"    sex: {person['sex']}")
        birth_date, birth_place = person["birth"]
        lines.append(f"    birth: {{date: {birth_date}, place: {birth_place}}}")
        death_date, death_place = person["death"]
        if death_date:
            lines.append(f"    death: {{date: {death_date}, place: {death_place}}}")
        if person["parents"]:
            lines.append(f"    parents: [{', '.join(person['parents'])}]")
        if person["residences"]:
            lines.append("    residences:")
            for when, where in person["residences"]:
                lines.append(f"      - {{from: {when}, place: {where}}}")
        if person["notes"]:
            lines.append(f"    notes: {_scalar(person['notes'])}")
        lines.append("")
    return "\n".join(lines)


def _scalar(text: str) -> str:
    return f'"{text}"' if any(c in text for c in ":#\"'{}[]") else text


def write(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_yaml(), encoding="utf-8")
    return path
