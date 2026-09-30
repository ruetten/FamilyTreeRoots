from pathlib import Path

import pytest

from familytree import dummy_data
from familytree.loader import FamilyDataError, load_tree
from familytree.model import parse_date

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    sample = dummy_data.write(tmp_path_factory.mktemp("sample") / "family.yaml")
    return load_tree(sample, DATA / "places.yaml")


def test_sample_tree_loads(tree):
    assert len(tree.people) == 15
    assert tree.root_id == "ego"
    assert tree.root.name == "Alva Severin"


def test_every_place_reference_resolves(tree):
    for person in tree.people.values():
        assert tree.place(person.birth.place_id) is not None


def test_ancestor_depths_span_eight_generations(tree):
    depths = tree.ancestor_depths()
    assert depths["ego"] == 0
    assert depths["erik_1972"] == 1
    assert depths["olof_1800"] == 7
    # The sample file is one unbroken line, so everyone is a direct ancestor.
    assert len(depths) == len(tree.people)


@pytest.mark.parametrize(
    "value,expected",
    [(1842, 1842.0), ("1842", 1842.0), ("1842-01-01", 1842.0)],
)
def test_parse_date_variants(value, expected):
    assert parse_date(value) == pytest.approx(expected)


def test_parse_date_midyear_is_fractional():
    assert 1842.4 < parse_date("1842-07-01") < 1842.6


def test_validation_reports_all_problems(tmp_path):
    (tmp_path / "places.yaml").write_text("home:\n  name: Home\n  lat: 0\n  lon: 0\n")
    (tmp_path / "family.yaml").write_text(
        "root: kid\n"
        "people:\n"
        "  - id: kid\n"
        "    name: Kid\n"
        "    birth: {date: 1900, place: nowhere}\n"
        "    death: {date: 1880, place: home}\n"
        "    parents: [ghost]\n"
    )
    with pytest.raises(FamilyDataError) as excinfo:
        load_tree(tmp_path / "family.yaml", tmp_path / "places.yaml")
    joined = " | ".join(excinfo.value.errors)
    assert "unknown place 'nowhere'" in joined
    assert "unknown parent 'ghost'" in joined
    assert "death 1880 precedes birth 1900" in joined


def test_validation_detects_ancestry_cycle(tmp_path):
    (tmp_path / "places.yaml").write_text("home:\n  name: Home\n  lat: 0\n  lon: 0\n")
    (tmp_path / "family.yaml").write_text(
        "root: a\n"
        "people:\n"
        "  - id: a\n"
        "    birth: {date: 1900, place: home}\n"
        "    parents: [b]\n"
        "  - id: b\n"
        "    birth: {date: 1870, place: home}\n"
        "    parents: [a]\n"
    )
    with pytest.raises(FamilyDataError) as excinfo:
        load_tree(tmp_path / "family.yaml", tmp_path / "places.yaml")
    assert any("cycle" in e for e in excinfo.value.errors)
