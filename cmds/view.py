"""Grouping, ordering, filtering and rendering of entries."""

from __future__ import annotations

from collections.abc import Iterable

from rich.console import Console
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from .store import Entry, load_settings

PINNED = ["azure", "git", "kubectl", "kong"]
INDENT = 5  # commands sit two columns in from the group names, whether in a subgroup or not

# Colours live here only. Pick a palette with `cmds color`.
THEMES = {
    "blue": {
        "banner": ["#a6d0ff", "#7aa2f7", "#4f7bd9", "#2f4f9e"],  # one shade per banner row
        "shadow": "#8a8f98",
        "rule": "#273b6b",
        "subtitle": "#4f7bd9",
        "group": "bold #a6d0ff",
        "subgroup": "bold #7aa2f7",
        "command": "#c8d3f5",
        "description": "italic #5f7bb8",
        "highlight": "bold #0b1021 on #a6d0ff",
    },
    "orange": {
        "banner": ["#ffe2b8", "#ffc46b", "#ff9d2e", "#f27a0c"],
        "shadow": "#8a8f98",
        "rule": "#6b4515",
        "subtitle": "#ffa23d",
        "group": "bold #ffd58f",
        "subgroup": "bold #ffb24a",
        "command": "#fff3e3",
        "description": "italic #e0953f",
        "highlight": "bold #1a1208 on #ffc46b",
    },
}


def theme() -> dict:
    return THEMES.get(load_settings().get("color", ""), THEMES["blue"])
# "CMDS" as 8-row pixel fonts; row pairs become half-blocks. Switch with `cmds style`.
SANS = [
    ".#####..##.....##..#####.....#####",
    "######..###...###..######...######",
    "##......####.####..##..###..##....",
    "##......##.###.##..##...##..#####.",
    "##......##..#..##..##...##...#####",
    "##......##.....##..##..###......##",
    "######..##.....##..######...######",
    ".#####..##.....##..#####....#####.",
]
GOTH = [
    ".#####...#.....#...#####...#####.",
    "######..###...###.######..######.",
    "##....#.####.####.##..###.##....#",
    "##......##.###.##.##...##.####...",
    "##......##..#..##.##...##....####",
    "##....#.##..#..##.##..###.#....##",
    "######..##.....##.######...######",
    ".#####..##.....##..#####...#####.",
]
# name -> (pixels, drop-shadow offset or None, where the subtitle goes: "beside" the logo or in the "rule")
STYLES = {"shadow": (SANS, (1, 2), "beside"), "plain": (SANS, None, "beside"), "goth": (GOTH, None, "rule")}


def _cells(pixels: list[str], shadow: tuple[int, int] | None) -> list[list[tuple[str, bool]]]:
    """Lines of (character, is_shadow) cells."""
    dx, dy = shadow or (0, 0)
    height = len(pixels) + dy
    grid = [[" "] * (len(pixels[0]) + dx) for _ in range(height + height % 2)]
    for mark, ox, oy in (("s", dx, dy), ("#", 0, 0)):
        for y, row in enumerate(pixels):
            for x, px in enumerate(row):
                if px == "#":
                    grid[y + oy][x + ox] = mark

    def cell(t: str, b: str) -> tuple[str, bool]:
        if "#" in (t, b):
            return " ▀▄█"[(t == "#") + 2 * (b == "#")], False
        return "░" if b == "s" else " ", True  # only the lower half casts, keeps chamfers from leaking

    return [[cell(t, b) for t, b in zip(top, bottom)] for top, bottom in zip(grid[::2], grid[1::2])]


def _rule(width: int, t: dict, title: Text | None = None, tail: str = "") -> Text:
    """── title ───────── tail  (title and tail optional)."""
    rule = Text(style=t["rule"])
    if title:
        rule.append("── ")
        rule.append_text(title)
        rule.append(" ")
    rule.append("─" * max(0, width - len(rule) - len(tail)))
    rule.append(tail, style=t["subtitle"])
    return rule


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def banner(console: Console, subtitle: str, t: dict) -> None:
    pixels, shadow, placement = STYLES.get(load_settings().get("style", ""), STYLES["shadow"])
    lines, shades = _cells(pixels, shadow), t["banner"]
    beside = placement == "beside" and len(lines[0]) + 5 + len(subtitle) <= console.width
    console.print()
    for i, cells in enumerate(lines):
        line = Text("  ")
        for char, is_shadow in cells:
            line.append(char, style=t["shadow"] if is_shadow else shades[min(i, len(shades) - 1)])
        if beside and i == len(pixels) // 2 - 1:  # baseline row of the letters
            line.append("   " + subtitle, style=t["subtitle"])
        console.print(line)
    console.print(_rule(console.width, t, None if beside else Text(subtitle, style=t["subtitle"])))
    console.print()


def _tech_key(tech: str) -> tuple:
    top, _, sub = tech.partition("/")
    rank = PINNED.index(top) if top in PINNED else len(PINNED)
    return (rank, top, sub)  # sub == "" puts the parent group before its subgroups


def grouped(entries: Iterable[Entry]) -> list[tuple[str, list[Entry]]]:
    """(tech, entries) pairs: pinned tops first, then alphabetical; subgroups after
    their parent alphabetically; shortest command first inside each group."""
    by_tech: dict[str, list[Entry]] = {}
    for entry in entries:
        by_tech.setdefault(entry.tech, []).append(entry)
    return [
        (tech, sorted(by_tech[tech], key=lambda e: (len(e.command), e.command)))
        for tech in sorted(by_tech, key=_tech_key)
    ]


def matches_tech(entry_tech: str, wanted: str) -> bool:
    """`azure` matches azure and azure/*; `azure/pim` matches only azure/pim."""
    return entry_tech == wanted or entry_tech.startswith(wanted + "/")


def known_techs(entries: Iterable[Entry]) -> list[str]:
    techs = {e.tech for e in entries} | {e.top for e in entries}
    return sorted(techs, key=_tech_key)


def render(entries: list[Entry], console: Console, highlight: Iterable[str] = (), subtitle: str = "") -> None:
    words, t = list(highlight), theme()

    def text(value: str, style: str = "") -> Text:
        result = Text(value, style=style)
        result.highlight_words(words, t["highlight"], case_sensitive=False)
        return result

    banner(console, subtitle or f"command notebook · {plural(len(entries), 'entry', 'entries')}", t)
    if not entries:
        console.print(Text("     nothing stored yet. Add one with: cmds add", style=t["description"]))
        console.print()
        return
    # One shared command column and indent, so commands and descriptions line up across every group.
    cmd_width = min(max(len(e.command) for e in entries), max(40, int(console.width * 0.65)))
    last_top = None
    for tech, group in grouped(entries):
        top, _, sub = tech.partition("/")
        if top != last_top:
            if last_top is not None:
                console.print()
            console.print(_rule(console.width, t, text(top, t["group"])))
            last_top = top
        if sub:
            console.print()
            console.print(Padding(text("› " + tech, t["subgroup"]), (0, 0, 0, INDENT - 2), expand=False))
        table = Table(box=None, show_header=False, padding=(0, 3, 0, 0), pad_edge=False)
        table.add_column(style=t["command"], overflow="fold", width=cmd_width)
        table.add_column(style=t["description"], overflow="fold")
        for entry in group:
            table.add_row(text(entry.command), text(entry.description))
        console.print(Padding(table, (0, 0, 0, INDENT)))
    console.print()
