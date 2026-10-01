import math
from pathlib import Path

import pytest

from familytree import dummy_data
from familytree.loader import load_tree
from familytree.timeline import Config, Lineage, _hover, build_frames, build_position_track

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    sample = dummy_data.write(tmp_path_factory.mktemp("sample") / "family.yaml")
    return load_tree(sample, DATA / "places.yaml")


@pytest.fixture(scope="module")
def config():
    config = Config.load(ROOT / "config.yaml")
    config.start_year, config.end_year = 1800, 2006
    return config


@pytest.fixture(scope="module")
def lineage(tree, config):
    return Lineage(tree, config)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _near(tree, pos, place_id, tol=1.5):
    place = tree.places[place_id]
    return _dist(pos, (place.lat, place.lon)) < tol


def test_tree_is_a_single_line(tree):
    depths = tree.ancestor_depths()
    assert len(tree.people) == 15
    assert depths["ego"] == 0
    assert depths["olof_1800"] == 7
    # Every recorded person is a direct ancestor of the root.
    assert set(depths) == set(tree.people)


def test_emigrant_crosses_the_atlantic(tree, lineage):
    assert _near(tree, lineage.position("heinrich_1915", 1930), "hamburg")
    assert _near(tree, lineage.position("heinrich_1915", 1938), "paris")
    assert _near(tree, lineage.position("heinrich_1915", 1945), "chicago")
    assert lineage.position("heinrich_1915", 1939.7)[1] < -20  # mid-Atlantic


def test_parent_location_inferred_from_child_birth(tree, config):
    """marie_1975 records no moves, but her daughter was born in Minneapolis."""
    track = build_position_track(tree.people["marie_1975"], tree, config.move_tween_years)
    assert _near(tree, track.at(2001), "minneapolis")


def test_parents_converge_onto_the_birthplace(tree, lineage):
    birth = tree.people["heinrich_1915"].birth.year
    apart_before = _dist(
        lineage.position("olav_1886", birth - 6), lineage.position("greta_1889", birth - 6)
    )
    at_birth = _dist(
        lineage.position("olav_1886", birth), lineage.position("greta_1889", birth)
    )
    assert at_birth < 0.02
    assert apart_before > 0.3


def test_newborn_starts_exactly_where_its_parents_met(tree, lineage):
    birth = tree.people["heinrich_1915"].birth.year
    assert _dist(lineage.position("heinrich_1915", birth), lineage.position("olav_1886", birth)) < 0.02
    # ...then springs out to its own spot.
    assert _dist(
        lineage.position("heinrich_1915", birth), lineage.position("heinrich_1915", birth + 4)
    ) > 0.2


def test_handed_off_generation_dims_but_stays_visible(tree, lineage, config):
    olav = tree.people["olav_1886"]
    birth = tree.people["heinrich_1915"].birth.year
    assert lineage.alpha(olav, birth - 5) > 0.9
    dimmed = lineage.alpha(olav, birth + 2 * config.merge_years + 1)
    assert 0 < dimmed <= config.merged_alpha + 1e-6


def test_dot_is_gone_after_death_fade(tree, lineage, config):
    olav = tree.people["olav_1886"]
    assert lineage.alpha(olav, olav.death.year + config.death_fade_years + 0.1) == 0.0


def test_trail_follows_a_moving_dot(lineage):
    lats, lons = lineage.trail("heinrich_1915", 1940.5)
    assert lons[0] > -20 and lons[-1] < -70  # tail still in Europe, head in Chicago
    # No segment long enough for plotly's great-circle bend to show as a scallop.
    longest = max(
        math.hypot(lats[i + 1] - lats[i], lons[i + 1] - lons[i]) for i in range(len(lats) - 1)
    )
    assert longest <= 1.5 + 1e-9


def test_birth_flash_fires_only_around_a_birth(tree, lineage):
    birth = tree.people["ego"].birth.year
    assert any(f.alpha > 0 for f in lineage.flashes(birth + 0.2))
    assert lineage.flashes(birth - 1) == []


def test_frame_count_matches_the_span(tree, config):
    frames = build_frames(tree, config)
    data_first, data_last = tree.date_bounds()
    first = config.start_year if config.start_year is not None else math.floor(data_first)
    last = config.end_year if config.end_year is not None else math.ceil(data_last)
    assert len(frames) == int((last - first) / config.years_per_frame) + 1


def test_root_appears_in_2000(tree, config):
    frames = {f.label: f for f in build_frames(tree, config)}
    assert not any(d.is_root for d in frames["1999"].dots)
    assert any(d.is_root for d in frames["2001"].dots)


def test_living_counts_are_plausible(tree, config):
    frames = {f.label: f for f in build_frames(tree, config)}
    for year in ("1850", "1900", "1950", "2001"):
        expected = sum(1 for p in tree.people.values() if p.is_alive(float(year)))
        assert int(frames[year].caption.split("·")[1].split()[0]) == expected


def test_hover_age_tracks_the_slider_year(tree):
    olav = tree.people["olav_1886"]  # born 1886-09-11, died 1957
    assert "age 13" in _hover(olav, tree, 1900.0)
    assert "age 14" in _hover(olav, tree, 1900.8)
    assert "age 50" in _hover(olav, tree, 1937.0)


def test_hover_after_death_shows_age_at_death(tree):
    olav = tree.people["olav_1886"]
    text = _hover(olav, tree, olav.death.year + 0.5)
    assert "died aged 70" in text
    assert "<br>age " not in text
