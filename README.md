# Family Roots

An animated map of a family line. Each person is a dot that moves across the world as they
migrate, trailing a comet tail behind it. When a child is born, both parents' dots converge
onto the exact birthplace, a ring pulses, and the new generation emerges from the same point —
generation after generation, until you appear at the end.

Output is one self-contained interactive HTML file with play/pause and a scrub bar.
Only two dependencies: `plotly` and `PyYAML`.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```sh
.venv/bin/python -m familytree.cli generate   # write the sample tree to data/family.yaml
.venv/bin/python -m familytree.cli validate   # check dates, places and ancestry
.venv/bin/python -m familytree.cli render     # build out/family_map.html
```

Then open `out/family_map.html` in a browser.

> `generate` overwrites `data/family.yaml`. Once you start entering your own family, stop
> running it (or pass `--family` to write the sample somewhere else).

## Entering your own family

Two files drive everything.

**`data/places.yaml`** — every location, keyed by an id you choose:

```yaml
stockholm:
  name: Stockholm
  country: Sweden
  lat: 59.3293
  lon: 18.0686
```

**`data/family.yaml`** — the people:

```yaml
root: ego          # the person the whole line leads to

people:
  - id: sven_1858              # unique key, referenced by `parents`
    name: Sven Andersson
    sex: M
    birth: {date: 1858-01-19, place: stockholm}
    death: {date: 1930-12-05, place: bergen}    # omit entirely if still living
    parents: [anders_1830, brita_1833]          # 0, 1 or 2 ids
    residences:                                 # optional, where they were in between
      - {from: 1882-05-20, place: gothenburg}
      - {from: 1883-08-03, place: bergen}
    notes: Anything you like.
```

Dates accept `1858`, `1858-01` or `1858-01-19`. Anything coarser than a full date is treated
as the start of that year or month.

You only need to record moves you actually know about. A person is automatically assumed to
have been present at each of their children's births, so their path fills itself in. Positions
are held between known points and eased from one to the next.

Run `validate` after editing. It reports every problem at once — unknown place or parent ids,
a death before a birth, a parent who died before their child was born, ancestry loops.

## Tuning the animation

Everything visual lives in `config.yaml`:

| Key | What it does |
| --- | --- |
| `start_year` / `end_year` | Clip the timeline. `null` uses the data's own range. |
| `years_per_frame` | Smaller is smoother; also more frames and a bigger file. |
| `frame_ms` | Playback speed. |
| `move_tween_years` | How long a migration takes to draw across the map. |
| `transit_years` | Moves recorded closer together than this are treated as stopovers on one journey and animate as a single crossing. |
| `merge_years` | How long a birth pulls the parents together, and how long the handed-off generation takes to dim. |
| `merged_alpha` | How faint a generation becomes once the next one exists. |
| `trail_years`, `trail_samples` | Length and smoothness of the comet tail. |
| `flash_years` | Duration of the expanding ring at each birth. |
| `show_dead_ghosts`, `ghost_opacity` | The faint permanent marks left where people died. |
| `map.lat_range`, `map.lon_range` | The window. Widen it if your family reaches further. |
| `output.plotlyjs` | `inline` embeds plotly.js (~7 MB, works offline); `cdn` makes a small file that needs internet. |

## Layout

```
familytree/
  model.py       Person, Place, FamilyTree, date parsing
  loader.py      YAML -> model, with full validation
  timeline.py    position tracks, merge behaviour, frame building
  render.py      Plotly figure, frames, slider
  dummy_data.py  the sample tree
  cli.py         generate / validate / render
```

## Tests

```sh
.venv/bin/python -m pytest -q
```
