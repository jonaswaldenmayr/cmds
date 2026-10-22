"""Command-line entry point for cmds."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .store import Entry, StoreError, load, load_settings, save, save_setting, store_path
from .view import STYLES, THEMES, grouped, known_techs, matches_tech, plural, render

EXAMPLES = """\
examples:
  cmds                          same as `cmds all`
  cmds azure                    azure and all its subgroups (azure/pim, ...)
  cmds azure/pim                only the azure/pim subgroup
  cmds add                      interactive add
  cmds add --tech git --command "git stash list" --desc "show stashes"
  cmds search pim               everything mentioning pim
  cmds search secret set        entries containing both words (any field)
  cmds search --tech kubectl log
  cmds rm                       pick an entry by number and delete it
  cmds edit                     open the YAML file in $EDITOR
  cmds style goth               switch the banner (shadow | plain | goth); no arg shows it
  cmds color orange             switch the palette (blue | orange); no arg shows it
  cmds file ~/dotfiles/cmds.yaml keep the store elsewhere, e.g. in a git repo; no arg shows it
  cmds autocommit on            commit the store after add/rm (off | on | push)

store: ~/.config/cmds/commands.yaml unless changed with `cmds file` or $CMDS_FILE
Commands are never executed. Store placeholders like <key>, never real secrets.
exit codes: 0 ok, 1 user error / no match, 2 store file problem
"""
AUTOCOMMIT = {"off": "do nothing", "on": "git commit the store", "push": "commit and push"}
SECRET_RE = re.compile(r"(?i)(password|passwd|secret|token|api[-_]?key)\s*[=:]\s*(?!<)\S{6,}")


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse exits 2 by default; 1 is a user error here
        self.print_usage(sys.stderr)
        fail(message)


def fail(message: str) -> None:
    print(f"cmds: {message}", file=sys.stderr)
    raise SystemExit(1)


def build_parser() -> Parser:
    parser = Parser(prog="cmds", description="A notebook of shell commands you use often but cannot remember.",
                    epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", metavar="command")
    sub.add_parser("all", help="list every entry grouped by tech")
    show = sub.add_parser("show", help="list one tech (shortcut: `cmds <tech>`)")
    show.add_argument("tech")
    add = sub.add_parser("add", help="add an entry (interactive unless flags are given)")
    add.add_argument("--tech", help="e.g. git or azure/pim")
    add.add_argument("--command", help="the exact command text")
    add.add_argument("--desc", help="optional description")
    search = sub.add_parser("search", help="find entries matching all words in any field")
    search.add_argument("words", nargs="+", metavar="word")
    search.add_argument("--tech", help="limit the search to one tech")
    sub.add_parser("rm", help="delete an entry (interactive)")
    sub.add_parser("edit", help="open the YAML file in $EDITOR")
    style = sub.add_parser("style", help="show or switch the banner style")
    style.add_argument("name", nargs="?", choices=list(STYLES), metavar="name")
    color = sub.add_parser("color", aliases=["colour"], help="show or switch the colour palette")
    color.add_argument("name", nargs="?", choices=list(THEMES), metavar="name")
    file = sub.add_parser("file", help="show or change where the YAML store lives")
    file.add_argument("path", nargs="?")
    auto = sub.add_parser("autocommit", help="git-commit the store after add/rm: off, on, or push")
    auto.add_argument("mode", nargs="?", choices=list(AUTOCOMMIT), metavar="mode")
    return parser


def ask(label: str, required: bool = True) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value or not required:
            return value


def ask_tech(entries: list[Entry]) -> str:
    known = known_techs(entries)
    print("known: " + ", ".join(known) + "  (tab completes; new names are fine)")
    try:
        import readline

        readline.set_completer(lambda text, i: [t for t in known if t.startswith(text)][i])
        readline.parse_and_bind("tab: complete")
    except ImportError:
        pass
    return ask("tech").strip("/")


def cmd_all(args: argparse.Namespace, console: Console) -> int:
    render(load(store_path()), console)
    return 0


def cmd_show(args: argparse.Namespace, console: Console) -> int:
    entries = load(store_path())
    wanted = args.tech.strip("/")
    hits = [e for e in entries if matches_tech(e.tech, wanted)]
    if not hits:
        fail(f"unknown tech '{wanted}'. Known: {', '.join(known_techs(entries))}")
    render(hits, console, subtitle=f"{wanted} · {plural(len(hits), 'entry', 'entries')}")
    return 0


def cmd_search(args: argparse.Namespace, console: Console) -> int:
    entries = load(store_path())
    if args.tech:
        entries = [e for e in entries if matches_tech(e.tech, args.tech.strip("/"))]
    words = [w.lower() for w in args.words]
    hits = [e for e in entries if all(w in f"{e.tech}\n{e.command}\n{e.description}".lower() for w in words)]
    if not hits:
        fail("no matching commands")
    scope = f" in {args.tech}" if args.tech else ""
    render(hits, console, highlight=args.words, subtitle=f"search {' '.join(args.words)!r}{scope} · {plural(len(hits), 'hit', 'hits')}")
    return 0


def autocommit(path: Path, message: str) -> None:
    """Commit (and maybe push) just the store file, if the user turned that on."""
    mode = load_settings().get("autocommit", "off")
    if mode not in ("on", "push"):
        return

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(path.parent), *args], capture_output=True, text=True)

    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        print(f"cmds: autocommit is {mode} but {path.parent} is not a git repository", file=sys.stderr)
        return
    git("add", "--", str(path))
    result = git("commit", "-q", "-m", message[:72], "--", str(path))
    if result.returncode == 0 and mode == "push":
        result = git("push", "-q")
    if result.returncode != 0:
        print(f"cmds: git failed: {result.stderr.strip() or result.stdout.strip()}", file=sys.stderr)


def cmd_add(args: argparse.Namespace, console: Console) -> int:
    path = store_path()
    entries = load(path)
    prompted = args.tech is None or args.command is None
    tech = (args.tech or ask_tech(entries)).strip().strip("/")
    command = (args.command or ask("command")).strip()
    if not tech or not command:
        fail("tech and command must not be empty")
    description = args.desc if args.desc is not None else (ask("description (optional)", required=False) if prompted else "")
    if any(e.tech == tech and e.command == command for e in entries):
        fail(f"'{command}' already exists under {tech}")
    if SECRET_RE.search(command):
        fail("that command looks like it contains a secret value; use a placeholder like <token> instead")
    entries.append(Entry(tech, command, description.strip()))
    save(path, entries)
    console.print(Text(f"added to {tech}: {command}"))
    autocommit(path, f"cmds add {tech}: {command}")
    return 0


def cmd_rm(args: argparse.Namespace, console: Console) -> int:
    path = store_path()
    entries = load(path)
    if not entries:
        fail("nothing stored yet")
    ordered = [e for _, group in grouped(entries) for e in group]
    table = Table(box=None, show_header=False, padding=(0, 2, 0, 0), pad_edge=False)
    table.add_column(justify="right", style="bold")
    table.add_column(style="cyan")
    table.add_column(style="green", overflow="fold")
    for number, entry in enumerate(ordered, 1):
        table.add_row(str(number), Text(entry.tech), Text(entry.command))
    console.print(table)
    choice = ask("delete #")
    if not choice.isdigit() or not 1 <= int(choice) <= len(ordered):
        fail(f"pick a number between 1 and {len(ordered)}")
    victim = ordered[int(choice) - 1]
    if ask(f"delete '{victim.command}'? [y/N]", required=False).lower() != "y":
        print("not deleted")
        return 0
    save(path, [e for e in entries if e is not victim])
    print("deleted")
    autocommit(path, f"cmds rm {victim.tech}: {victim.command}")
    return 0


def cmd_edit(args: argparse.Namespace, console: Console) -> int:
    path: Path = store_path()
    load(path)  # creates the file on first run
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    return subprocess.call([*shlex.split(editor), str(path)])


def _setting(console: Console, key: str, options: dict, label: str, name: str | None) -> int:
    if name:
        save_setting(key, name)
    current = load_settings().get(key)
    current = current if current in options else next(iter(options))
    console.print(Text(f"{label}: {current}   (available: {', '.join(options)})"))
    return 0


def cmd_style(args: argparse.Namespace, console: Console) -> int:
    return _setting(console, "style", STYLES, "banner style", args.name)


def cmd_color(args: argparse.Namespace, console: Console) -> int:
    return _setting(console, "color", THEMES, "colour", args.name)


def cmd_autocommit(args: argparse.Namespace, console: Console) -> int:
    return _setting(console, "autocommit", AUTOCOMMIT, "autocommit", args.mode)


def cmd_file(args: argparse.Namespace, console: Console) -> int:
    if args.path:
        new = Path(args.path).expanduser().resolve()
        if not new.exists():
            save(new, load(store_path()))  # carry the current entries over
        save_setting("file", str(new))
    print(f"store: {store_path()}")  # plain print: never wrapped, usable in scripts
    return 0


COMMANDS = {"file": cmd_file, "autocommit": cmd_autocommit, "all": cmd_all, "style": cmd_style, "color": cmd_color, "colour": cmd_color, "show": cmd_show, "search": cmd_search, "add": cmd_add, "rm": cmd_rm, "edit": cmd_edit}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["all"]
    elif argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv = ["show", *argv]  # `cmds <tech>` shortcut
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.cmd](args, Console())
    except StoreError as exc:
        print(f"cmds: {exc}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
