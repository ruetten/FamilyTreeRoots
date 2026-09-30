"""Renders animation frames into a self-contained interactive Plotly HTML page."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go

from .model import FamilyTree
from .timeline import Config, Frame

# Root first, then progressively cooler shades going back through the generations.
_PALETTE = [
    "#ffd166", "#ff9f6e", "#ff7a8a", "#e07be0", "#9b8cff",
    "#5fb8ff", "#49d9c4", "#7fe06a", "#c9d94c",
]
_GHOST = "#8a97a6"
_TRAIL = "#7fd7ff"
_FLASH = "#ffe9a8"

TRAIL_OLD, TRAIL_NEW, GHOSTS, FLASH, DOTS, ROOT = range(6)


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{max(0.0, min(alpha, 1.0)):.3f})"


def _color_for(depth: int) -> str:
    return _PALETTE[max(depth, 0) % len(_PALETTE)]


def _flatten(paths: list[tuple[list[float], list[float]]]) -> tuple[list, list]:
    lats: list[float | None] = []
    lons: list[float | None] = []
    for path_lats, path_lons in paths:
        lats.extend([*(round(v, 3) for v in path_lats), None])
        lons.extend([*(round(v, 3) for v in path_lons), None])
    return lats, lons


def _frame_traces(frame: Frame, config: Config) -> list[go.Scattergeo]:
    old_lats, old_lons = _flatten(frame.trails_old)
    new_lats, new_lons = _flatten(frame.trails_new)

    regular = [d for d in frame.dots if not d.is_root]
    root = [d for d in frame.dots if d.is_root]

    return [
        go.Scattergeo(
            lat=old_lats, lon=old_lons, mode="lines", hoverinfo="skip", showlegend=False,
            line=dict(width=1.2, color=_rgba(_TRAIL, 0.16)),
        ),
        go.Scattergeo(
            lat=new_lats, lon=new_lons, mode="lines", hoverinfo="skip", showlegend=False,
            line=dict(width=2.2, color=_rgba(_TRAIL, 0.45)),
        ),
        go.Scattergeo(
            lat=[p[0] for p in frame.ghosts], lon=[p[1] for p in frame.ghosts],
            mode="markers", hoverinfo="skip", showlegend=False,
            marker=dict(size=5, color=_rgba(_GHOST, config.ghost_opacity)),
        ),
        go.Scattergeo(
            lat=[f.lat for f in frame.flashes], lon=[f.lon for f in frame.flashes],
            mode="markers", hoverinfo="skip", showlegend=False,
            marker=dict(
                size=[round(f.size, 1) for f in frame.flashes],
                color=[_rgba(_FLASH, 0.0) for _ in frame.flashes],
                line=dict(
                    width=2,
                    color=[_rgba(_FLASH, f.alpha) for f in frame.flashes],
                ),
            ),
        ),
        go.Scattergeo(
            lat=[round(d.lat, 3) for d in regular], lon=[round(d.lon, 3) for d in regular],
            mode="markers", showlegend=False,
            text=[d.hover for d in regular], hoverinfo="text",
            marker=dict(
                size=13,
                color=[_rgba(_color_for(d.depth), d.alpha) for d in regular],
                line=dict(width=0),
            ),
        ),
        go.Scattergeo(
            lat=[round(d.lat, 3) for d in root], lon=[round(d.lon, 3) for d in root],
            mode="markers", showlegend=False,
            text=[d.hover for d in root], hoverinfo="text",
            marker=dict(
                size=24,
                color=[_rgba(_PALETTE[0], d.alpha) for d in root],
                line=dict(width=2, color=[_rgba("#ffffff", 0.85 * d.alpha) for d in root]),
            ),
        ),
    ]


def _legend_traces(tree: FamilyTree) -> list[go.Scattergeo]:
    max_depth = max(tree.ancestor_depths().values(), default=0)
    labels = {0: "me", 1: "parents", 2: "grandparents"}
    traces = []
    for depth in range(max_depth + 1):
        name = labels.get(depth) or f"{depth}\u00d7 back"
        traces.append(
            go.Scattergeo(
                lat=[None], lon=[None], mode="markers", name=name, hoverinfo="skip",
                marker=dict(size=10, color=_color_for(depth)),
            )
        )
    return traces


def _caption(text: str) -> dict:
    return dict(
        text=text, x=0.02, y=0.96, xref="paper", yref="paper",
        showarrow=False, align="left",
        font=dict(size=26, color="#e8edf2", family="Helvetica Neue, Arial, sans-serif"),
    )


def build_figure(tree: FamilyTree, frames: list[Frame], config: Config) -> go.Figure:
    if not frames:
        raise ValueError("no frames to render")

    fig = go.Figure(data=_frame_traces(frames[0], config) + _legend_traces(tree))

    fig.frames = [
        go.Frame(
            name=str(i),
            data=_frame_traces(frame, config),
            traces=[TRAIL_OLD, TRAIL_NEW, GHOSTS, FLASH, DOTS, ROOT],
            layout=go.Layout(annotations=[_caption(frame.caption)]),
        )
        for i, frame in enumerate(frames)
    ]

    # Label every step; plotly thins them to whatever fits the bar's width.
    steps = [
        dict(
            method="animate",
            label=frame.label,
            args=[[str(i)], dict(mode="immediate", frame=dict(duration=0, redraw=True),
                                 transition=dict(duration=0))],
        )
        for i, frame in enumerate(frames)
    ]

    play_args = [None, dict(
        mode="immediate",
        frame=dict(duration=config.frame_ms, redraw=True),
        transition=dict(duration=int(config.frame_ms * 0.6), easing="linear"),
        fromcurrent=True,
    )]
    pause_args = [[None], dict(mode="immediate", frame=dict(duration=0, redraw=False),
                               transition=dict(duration=0))]

    fig.update_layout(
        title=None,
        annotations=[_caption(frames[0].caption)],
        paper_bgcolor="#0b0e12",
        plot_bgcolor="#0b0e12",
        font=dict(color="#c7d0da"),
        margin=dict(l=0, r=0, t=0, b=76),
        legend=dict(
            orientation="h", x=0.33, y=0.995, xanchor="left", yanchor="top",
            bgcolor="rgba(0,0,0,0)", font=dict(size=11),
        ),
        geo=dict(
            scope="world",
            resolution=config.map.resolution,
            projection_type=config.map.projection,
            showland=True, landcolor=config.map.land_color,
            showocean=True, oceancolor=config.map.ocean_color,
            showcountries=True, countrycolor=config.map.country_color,
            showsubunits=config.map.show_states, subunitcolor=config.map.subunit_color,
            showlakes=config.map.show_lakes, lakecolor=config.map.ocean_color,
            showcoastlines=True, coastlinecolor=config.map.country_color,
            showframe=False,
            bgcolor="#0b0e12",
            lataxis=dict(range=list(config.map.lat_range)),
            lonaxis=dict(range=list(config.map.lon_range)),
        ),
        updatemenus=[dict(
            type="buttons", direction="left", showactive=False,
            x=0, y=0, xanchor="left", yanchor="top",
            bgcolor="#1b212a", bordercolor="#3a444f", font=dict(color="#e8edf2"),
            buttons=[
                dict(label="\u25b6  Play", method="animate", args=play_args),
                dict(label="\u2016  Pause", method="animate", args=pause_args),
            ],
        )],
        sliders=[dict(
            active=0, x=0.14, y=0, len=0.84, xanchor="left", yanchor="top",
            pad=dict(t=6, b=10),
            bgcolor="#1b212a", bordercolor="#3a444f", activebgcolor="#ffd166",
            currentvalue=dict(visible=False),
            tickcolor="#3a444f", font=dict(size=10),
            steps=steps,
        )],
    )
    return fig


def write_html(fig: go.Figure, config: Config) -> Path:
    path = Path(config.output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(
        path,
        include_plotlyjs=True if config.plotlyjs == "inline" else "cdn",
        full_html=True,
        auto_play=False,
        config=dict(displayModeBar=False, scrollZoom=True),
    )
    return path
