"""Command line entry point: ``python -m familytree.cli {generate,validate,render}``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import dummy_data
from .loader import FamilyDataError, load_tree

DEFAULT_FAMILY = "data/family.yaml"
DEFAULT_PLACES = "data/places.yaml"
DEFAULT_CONFIG = "config.yaml"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--family", default=DEFAULT_FAMILY)
    parser.add_argument("--places", default=DEFAULT_PLACES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="familytree", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="write the sample family tree to data/family.yaml")
    gen.add_argument("--family", default=DEFAULT_FAMILY)

    val = sub.add_parser("validate", help="check the YAML for dates, places and ancestry problems")
    _add_common(val)

    ren = sub.add_parser("render", help="build the interactive HTML map")
    _add_common(ren)
    ren.add_argument("--config", default=DEFAULT_CONFIG)
    ren.add_argument("--out", default=None, help="override the output path from config.yaml")

    args = parser.parse_args(argv)

    if args.command == "generate":
        path = dummy_data.write(args.family)
        print(f"wrote {len(dummy_data.PEOPLE)} people to {path}")
        return 0

    try:
        tree = load_tree(args.family, args.places)
    except FamilyDataError as exc:
        print(f"{len(exc.errors)} problem(s) found:", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"missing file: {exc.filename} (run `generate` first?)", file=sys.stderr)
        return 1

    if args.command == "validate":
        first, last = tree.date_bounds()
        print(f"0 errors - {len(tree.people)} people, {len(tree.places)} places, "
              f"{int(first)}-{int(last)}, root '{tree.root_id}'")
        return 0

    from .render import build_figure, write_html
    from .timeline import Config, build_frames

    config = Config.load(args.config)
    if args.out:
        config.output_path = args.out
    frames = build_frames(tree, config)
    path = write_html(build_figure(tree, frames, config), config)
    print(f"wrote {len(frames)} frames to {Path(path).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
