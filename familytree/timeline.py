"""Turns a :class:`FamilyTree` into an ordered list of animation frames."""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .model import FamilyTree, Person

LatLon = tuple[float, float]
Path2D = tuple[list[float], list[float]]

# Plotly bends each line segment along a great circle, so long ones bulge. Keeping every
# segment short makes the bulge invisible and the path read as straight.
_MAX_SEGMENT_DEGREES = 1.5


@dataclass
class MapStyle:
    projection: str = "natural earth"
    lat_range: tuple[float, float] = (38.0, 70.0)
    lon_range: tuple[float, float] = (-98.0, 26.0)
    land_color: str = "#2b3138"
    ocean_color: str = "#11151a"
    country_color: str = "#4a535e"
    show_states: bool = True
    subunit_color: str = "#3b444e"
    show_lakes: bool = True
    resolution: int = 50


@dataclass
class Config:
    start_year: float | None = None
    end_year: float | None = None
    years_per_frame: float = 0.5
    frame_ms: int = 70
    move_tween_years: float = 3.0
    transit_years: float = 1.5
    merge_years: float = 3.0
    merged_alpha: float = 0.3
    trail_years: float = 7.0
    trail_samples: int = 16
    flash_years: float = 4.0
    birth_fade_years: float = 1.5
    death_fade_years: float = 2.0
    show_dead_ghosts: bool = True
    ghost_opacity: float = 0.25
    map: MapStyle = field(default_factory=MapStyle)
    output_path: str = "out/family_map.html"
    plotlyjs: str = "inline"
    title: str = "Family Roots"

    @classmethod
    def load(cls, path: str | Path) -> Config:
        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        map_raw = raw.get("map") or {}
        out_raw = raw.get("output") or {}
        defaults = cls()

        def value(key: str, cast):
            return cast(raw[key]) if raw.get(key) is not None else getattr(defaults, key)

        return cls(
            start_year=raw.get("start_year"),
            end_year=raw.get("end_year"),
            years_per_frame=value("years_per_frame", float),
            frame_ms=value("frame_ms", int),
            move_tween_years=value("move_tween_years", float),
            transit_years=value("transit_years", float),
            merge_years=value("merge_years", float),
            merged_alpha=value("merged_alpha", float),
            trail_years=value("trail_years", float),
            trail_samples=value("trail_samples", int),
            flash_years=value("flash_years", float),
            birth_fade_years=value("birth_fade_years", float),
            death_fade_years=value("death_fade_years", float),
            show_dead_ghosts=value("show_dead_ghosts", bool),
            ghost_opacity=value("ghost_opacity", float),
            map=MapStyle(
                projection=map_raw.get("projection", defaults.map.projection),
                lat_range=tuple(map_raw.get("lat_range", defaults.map.lat_range)),
                lon_range=tuple(map_raw.get("lon_range", defaults.map.lon_range)),
                land_color=map_raw.get("land_color", defaults.map.land_color),
                ocean_color=map_raw.get("ocean_color", defaults.map.ocean_color),
                country_color=map_raw.get("country_color", defaults.map.country_color),
                show_states=map_raw.get("show_states", defaults.map.show_states),
                subunit_color=map_raw.get("subunit_color", defaults.map.subunit_color),
                show_lakes=map_raw.get("show_lakes", defaults.map.show_lakes),
                resolution=int(map_raw.get("resolution", defaults.map.resolution)),
            ),
            output_path=out_raw.get("path", defaults.output_path),
            plotlyjs=out_raw.get("plotlyjs", defaults.plotlyjs),
            title=out_raw.get("title", defaults.title),
        )


@dataclass
class Dot:
    person_id: str
    label: str
    hover: str
    lat: float
    lon: float
    alpha: float
    depth: int
    is_root: bool = False


@dataclass
class Flash:
    """The expanding ring marking the moment two dots merge into a newborn."""

    lat: float
    lon: float
    size: float
    alpha: float


@dataclass
class Frame:
    label: str
    caption: str
    dots: list[Dot] = field(default_factory=list)
    ghosts: list[LatLon] = field(default_factory=list)
    trails_new: list[Path2D] = field(default_factory=list)
    trails_old: list[Path2D] = field(default_factory=list)
    flashes: list[Flash] = field(default_factory=list)


def _ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _jitter(person_id: str, spread: float = 0.9) -> LatLon:
    """Stable per-person nudge so a couple at one place stays two visible dots."""
    seed = zlib.crc32(person_id.encode())
    angle = (seed % 997) / 997 * 2 * math.pi
    radius = spread * (0.5 + 0.5 * ((seed >> 10) % 101) / 100)
    return radius * math.sin(angle) * 0.6, radius * math.cos(angle)


@dataclass
class _Leg:
    """One continuous journey, possibly via several stopovers, arriving on its recorded date."""

    depart: float
    arrive: float
    points: list[LatLon]
    cumulative: list[float]


class PositionTrack:
    """Where one person is at any moment, as a set of dated waypoints."""

    def __init__(self, waypoints: list[tuple[float, LatLon]], tween_years: float, transit_years: float):
        self.waypoints = waypoints
        self.legs = _build_legs(waypoints, max(tween_years, 0.0), max(transit_years, 0.0))

    @property
    def first_year(self) -> float:
        return self.waypoints[0][0]

    @property
    def final(self) -> LatLon:
        return self.waypoints[-1][1]

    def at(self, year: float) -> LatLon:
        if not self.legs:
            return self.waypoints[0][1]
        if year <= self.legs[0].depart:
            return self.legs[0].points[0]
        for leg in self.legs:
            if year >= leg.arrive:
                continue
            if year <= leg.depart:
                return leg.points[0]
            return _along(leg, _ease((year - leg.depart) / (leg.arrive - leg.depart)))
        return self.legs[-1].points[-1]


def _build_legs(waypoints: list[tuple[float, LatLon]], tween: float, transit: float) -> list[_Leg]:
    legs: list[_Leg] = []
    start = 0
    while start < len(waypoints) - 1:
        # Waypoints only a short hop apart are stopovers on one journey, not separate moves.
        end = start + 1
        while end < len(waypoints) - 1 and waypoints[end + 1][0] - waypoints[end][0] < transit:
            end += 1

        arrive = waypoints[end][0]
        travel = min(tween, 0.8 * (arrive - waypoints[start][0])) if tween > 0 else 0.0
        points = [pos for _, pos in waypoints[start:end + 1]]
        legs.append(_Leg(arrive - travel, arrive, points, _cumulative(points)))
        start = end
    return legs


def _cumulative(points: list[LatLon]) -> list[float]:
    """Normalized distance along the polyline, so long hops get proportionally more time."""
    totals = [0.0]
    for a, b in zip(points, points[1:]):
        totals.append(totals[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    span = totals[-1] or 1.0
    return [t / span for t in totals]


def _along(leg: _Leg, fraction: float) -> LatLon:
    for i in range(len(leg.cumulative) - 1):
        lo, hi = leg.cumulative[i], leg.cumulative[i + 1]
        if fraction > hi:
            continue
        t = (fraction - lo) / (hi - lo) if hi > lo else 0.0
        (lat0, lon0), (lat1, lon1) = leg.points[i], leg.points[i + 1]
        return lat0 + (lat1 - lat0) * t, lon0 + (lon1 - lon0) * t
    return leg.points[-1]


def build_position_track(
    person: Person,
    tree: FamilyTree,
    tween_years: float,
    transit_years: float = 1.5,
) -> PositionTrack | None:
    """Waypoints from birth, every child's birthplace, recorded moves, and death."""
    raw: list[tuple[float, LatLon, int]] = []
    off_lat, off_lon = _jitter(person.id)

    def add(year: float | None, place_id: str | None, priority: int) -> None:
        place = tree.place(place_id)
        if year is None or place is None:
            return
        raw.append((year, (place.lat + off_lat, place.lon + off_lon), priority))

    add(person.birth.year, person.birth.place_id, 0)
    for child in tree.children_of(person.id):
        # A parent is assumed to have been present wherever their child was born.
        add(child.birth.year, child.birth.place_id, 2)
    for move in person.residences:
        add(move.year, move.place_id, 1)
    add(person.death.year, person.death.place_id, 0)

    if not raw:
        return None

    # Explicit records win over inferred ones when they collide on the same date.
    raw.sort(key=lambda item: (item[0], item[2]))
    waypoints: list[tuple[float, LatLon]] = []
    for year, pos, _ in raw:
        if waypoints and abs(waypoints[-1][0] - year) < 1e-9:
            continue
        if waypoints and waypoints[-1][1] == pos:
            continue
        waypoints.append((year, pos))
    if not waypoints:
        waypoints = [(raw[0][0], raw[0][1])]
    return PositionTrack(waypoints, tween_years, transit_years)


class Lineage:
    """Position, visibility and merge behaviour for everyone in the tree."""

    def __init__(self, tree: FamilyTree, config: Config):
        self.tree = tree
        self.config = config
        self.tracks: dict[str, PositionTrack] = {}
        self.merge_points: dict[str, list[tuple[float, LatLon]]] = {}
        self.handover: dict[str, float] = {}

        for person in tree.people.values():
            track = build_position_track(
                person, tree, config.move_tween_years, config.transit_years
            )
            if track is None:
                continue
            self.tracks[person.id] = track
            self.merge_points[person.id] = self._merge_points(person)
            births = [c.birth.year for c in tree.children_of(person.id) if c.birth.year is not None]
            if births:
                self.handover[person.id] = max(births)

    def _merge_points(self, person: Person) -> list[tuple[float, LatLon]]:
        """Exact, un-jittered places a dot gets pulled onto: its own birth and each child's."""
        points = []
        for subject in (person, *self.tree.children_of(person.id)):
            place = self.tree.place(subject.birth.place_id)
            if place is not None and subject.birth.year is not None:
                points.append((subject.birth.year, (place.lat, place.lon)))
        return points

    def position(self, person_id: str, year: float) -> LatLon:
        lat, lon = self.tracks[person_id].at(year)
        span = self.config.merge_years
        if span <= 0:
            return lat, lon
        for event_year, (target_lat, target_lon) in self.merge_points[person_id]:
            pull = _ease(1.0 - abs(year - event_year) / span)
            if pull <= 0:
                continue
            lat += (target_lat - lat) * pull
            lon += (target_lon - lon) * pull
        return lat, lon

    def trail(self, person_id: str, year: float) -> Path2D:
        start = max(year - self.config.trail_years, self.tracks[person_id].first_year)
        steps = max(self.config.trail_samples, 2)
        lats, lons = [], []
        for i in range(steps + 1):
            lat, lon = self.position(person_id, start + (year - start) * i / steps)
            lats.append(lat)
            lons.append(lon)
        return _densify(lats, lons)

    def alpha(self, person: Person, year: float) -> float:
        config = self.config
        birth = person.birth.year
        if birth is None or year < birth:
            return 0.0
        alpha = (
            min(1.0, (year - birth) / config.birth_fade_years)
            if config.birth_fade_years > 0
            else 1.0
        )

        # Once the next generation exists, a dot steps into the background instead of vanishing.
        handover = self.handover.get(person.id)
        if handover is not None and config.merge_years > 0:
            stepped_back = _ease((year - handover - config.merge_years) / config.merge_years)
            alpha *= 1.0 - (1.0 - config.merged_alpha) * stepped_back

        death = person.death.year
        if death is not None and year >= death:
            if config.death_fade_years <= 0:
                return 0.0
            alpha *= max(0.0, 1.0 - (year - death) / config.death_fade_years)
        return max(alpha, 0.0)

    def flashes(self, year: float) -> list[Flash]:
        span = self.config.flash_years
        if span <= 0:
            return []
        out = []
        for person in self.tree.people.values():
            birth = person.birth.year
            place = self.tree.place(person.birth.place_id)
            if birth is None or place is None or not 0 <= year - birth < span:
                continue
            t = (year - birth) / span
            out.append(Flash(place.lat, place.lon, 20 + 72 * t, 0.55 * (1 - t) ** 2))
        return out


def build_tracks(tree: FamilyTree, config: Config) -> dict[str, PositionTrack]:
    return Lineage(tree, config).tracks


def _hover(person: Person, tree: FamilyTree, year: float) -> str:
    place = tree.place(person.birth.place_id)
    born = f"b. {int(person.birth.year)}" if person.birth.year is not None else "b. ?"
    if place:
        born += f" in {place.label}"
    lines = [f"<b>{person.name}</b>", born]
    if person.death.year is not None:
        death_place = tree.place(person.death.place_id)
        died = f"d. {int(person.death.year)}"
        if death_place:
            died += f" in {death_place.label}"
        lines.append(died)
        if person.birth.year is not None:
            lines.append(f"age {int(person.death.year - person.birth.year)}")
    elif person.birth.year is not None:
        lines.append(f"age {int(year - person.birth.year)}")
    return "<br>".join(lines)


def build_frames(tree: FamilyTree, config: Config) -> list[Frame]:
    lineage = Lineage(tree, config)
    depths = tree.generation_depths()
    data_start, data_end = tree.date_bounds()
    start = config.start_year if config.start_year is not None else math.floor(data_start)
    end = config.end_year if config.end_year is not None else math.ceil(data_end)
    step = max(config.years_per_frame, 0.05)

    frames: list[Frame] = []
    year = float(start)
    while year <= end + 1e-9:
        frames.append(_build_frame(lineage, depths, year))
        year += step
    return frames


def _build_frame(lineage: Lineage, depths: dict[str, int], year: float) -> Frame:
    tree, config = lineage.tree, lineage.config
    dots: list[Dot] = []
    ghosts: list[LatLon] = []
    trails_new: list[Path2D] = []
    trails_old: list[Path2D] = []
    living = 0

    for person in tree.people.values():
        if person.id not in lineage.tracks:
            continue
        alpha = lineage.alpha(person, year)
        if alpha <= 0.005:
            if config.show_dead_ghosts and person.death.year is not None and year >= person.death.year:
                ghosts.append(lineage.tracks[person.id].final)
            continue

        lat, lon = lineage.position(person.id, year)
        dots.append(
            Dot(
                person_id=person.id,
                label=person.name,
                hover=_hover(person, tree, year),
                lat=lat,
                lon=lon,
                alpha=alpha,
                depth=depths.get(person.id, 0),
                is_root=person.id == tree.root_id,
            )
        )
        if person.is_alive(year):
            living += 1

        lats, lons = lineage.trail(person.id, year)
        if _path_length(lats, lons) > 0.05:
            half = len(lats) // 2
            trails_old.append((lats[: half + 1], lons[: half + 1]))
            trails_new.append((lats[half:], lons[half:]))

    return Frame(
        label=str(int(year)),
        caption=f"{int(year)}  ·  {living} living",
        dots=dots,
        ghosts=ghosts,
        trails_new=trails_new,
        trails_old=trails_old,
        flashes=lineage.flashes(year),
    )


def _path_length(lats: list[float], lons: list[float]) -> float:
    return sum(math.hypot(lats[i + 1] - lats[i], lons[i + 1] - lons[i]) for i in range(len(lats) - 1))


def _densify(lats: list[float], lons: list[float]) -> Path2D:
    out_lats, out_lons = [lats[0]], [lons[0]]
    for i in range(len(lats) - 1):
        dlat, dlon = lats[i + 1] - lats[i], lons[i + 1] - lons[i]
        cuts = max(1, math.ceil(math.hypot(dlat, dlon) / _MAX_SEGMENT_DEGREES))
        for step in range(1, cuts + 1):
            out_lats.append(lats[i] + dlat * step / cuts)
            out_lons.append(lons[i] + dlon * step / cuts)
    return out_lats, out_lons
