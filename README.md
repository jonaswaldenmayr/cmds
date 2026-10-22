```text
  ▄█████  ██▄   ▄██  █████▄   ▄█████
  ██░░░░░ ██▀█▄█▀██░ ██░░▀██  ██▄▄▄░░
  ██░     ██░ ▀░░██░ ██░ ▄██░  ▀▀▀██
  ▀█████  ██░    ██░ █████▀░░ █████▀░   command notebook
    ░░░░░  ░░     ░░  ░░░░░    ░░░░░
```


CMDS is a personal notebook of shell commands you use often.
It stores command *text* only and never executes anything.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
cd ~/Code/_tools/cmds
uv tool install .            # puts `cmds` on your PATH
uv tool install --reinstall . # after changing the code
```

The store lives at `~/.config/cmds/commands.yaml` by default and is created empty on first
run. To keep it under version control, point the tool at a file inside a repo:

```sh
cmds file ~/Code/_tools/cmds/commands.yaml   # saved in ~/.config/cmds/settings.yaml
cmds file                                    # show where the store is
```

Existing entries are carried over when the target does not exist yet. `CMDS_FILE=...`
overrides the saved location for a single run.

With the store inside a git repo, `cmds` can commit it for you after every `add` and `rm`:

```sh
cmds autocommit on     # one commit per change, e.g. "cmds add git: git stash list"
cmds autocommit push   # same, then git push (fails loudly when offline)
cmds autocommit off    # default
```

Only the store file is committed; other changes in the repo are left alone.

A tidy way to keep the tool public and the commands private is a second, private repo
cloned into `data/` inside this folder. `data/` is in `.gitignore`, so the tool repo never
sees it, while autocommit works inside the nested repo as usual:

```sh
gh repo create cmds-data --private
git clone git@github.com:<you>/cmds-data.git data
cmds file ~/Code/_tools/cmds/data/commands.yaml
cmds autocommit on
```

## Usage

```sh
cmds                         # every entry, grouped by tech
cmds all                     # same
cmds azure                   # azure plus all its subgroups (azure/pim, azure/keyvault, ...)
cmds azure/pim               # only that subgroup
cmds add                     # interactive: tech (tab-completes known ones), command, description
cmds add --tech git --command "git stash list" --desc "show stashes"
cmds search pim              # everything mentioning pim (tech, command or description)
cmds search secret set       # entries containing both words, in any field, any order
cmds search --tech kubectl log
cmds rm                      # numbered list, pick one, confirm
cmds edit                    # open the YAML file in $VISUAL / $EDITOR
cmds style goth              # switch the banner style (shadow | plain | goth)
cmds color orange            # switch the palette (blue | orange)
cmds --help
```

Groups print in the order azure, git, kubectl, kong, then anything else alphabetically.
Subgroups follow their parent with an indented header. Within a group the shortest
command comes first. Long commands wrap to the terminal width and are never truncated.
Search results are shown in the same view with the matched text highlighted.

## Banner and colours

Three banner styles: `shadow` (ANSI-art drop shadow, context text beside the logo), `plain`
(same letters without the shadow) and `goth` (chamfered pixel letters, context text in the
rule below). Two palettes: `blue` and `orange`. Both settings are saved in
`~/.config/cmds/settings.yaml` next to the data file.

```sh
cmds style           # show the current style and the available ones
cmds style plain     # switch: shadow | plain | goth
cmds color           # show the current palette
cmds color orange    # switch: blue | orange   (`cmds colour` works too)
```

The palettes live in the `THEMES` dictionary at the top of `cmds/view.py`.

## The data file

```yaml
# cmds notebook. One entry per list item; tech may be nested like azure/pim.
- tech: git
  command: git log --oneline --graph --decorate -20
  description: compact history graph
- tech: azure/pim
  command: az rest --method GET --url "..."
  description: list my eligible PIM roles
```

Edit it by hand whenever you like. `tech` and `command` are required, `description` is
optional. Entries keep their file order; `add` appends at the end and each entry is
serialised independently, so untouched entries do not change between saves and diffs stay
small. (If you hand-format an entry in a non-canonical way, the next `add` or `rm` will
normalise it.)

Keep secrets out of the file. Use placeholders such as `<token>` or `<key>`; `add` refuses
commands that look like they embed a literal password, token or key.

## Exit codes

| code | meaning |
|------|---------|
| 0 | success |
| 1 | user error: unknown tech, duplicate, no search results, bad input |
| 2 | the store file cannot be read or written |

## Development

```sh
uv sync                      # creates .venv with rich, pyyaml and pytest
uv run pytest
uv run cmds all              # run from the checkout without installing
```
