import pytest

from cmds.cli import main
from cmds.store import Entry, load, save
from cmds.view import grouped, matches_tech


def add(*args):
    return main(["add", *args])


def test_first_run_creates_empty_store(empty_store, capsys):
    assert main(["all"]) == 0
    assert empty_store.exists()
    assert load(empty_store) == []
    assert "nothing stored yet" in capsys.readouterr().out


def test_all_groups_in_pinned_order(store, capsys):
    assert main(["all"]) == 0
    out = capsys.readouterr().out
    assert out.index("── azure") < out.index("── git") < out.index("── kubectl")


def test_add_persists_entry(store):
    assert add("--tech", "kong", "--command", "deck gateway dump", "--desc", "export config") == 0
    assert Entry("kong", "deck gateway dump", "export config") in load(store)


def test_add_refuses_exact_duplicate_within_tech(store, capsys):
    add("--tech", "git", "--command", "git stash list")
    before = store.read_text()
    with pytest.raises(SystemExit) as exc:
        add("--tech", "git", "--command", "git stash list")
    assert exc.value.code == 1
    assert "already exists" in capsys.readouterr().err
    assert store.read_text() == before
    # The same command under another tech is fine.
    assert add("--tech", "git/stash", "--command", "git stash list") == 0


def test_add_refuses_secret_looking_commands(store):
    with pytest.raises(SystemExit) as exc:
        add("--tech", "kong", "--command", "curl -H token=abcdef123456 http://x")
    assert exc.value.code == 1
    assert add("--tech", "kong", "--command", "curl -H token=<token> http://x") == 0


def test_untouched_entries_are_not_rewritten(store):
    add("--tech", "git", "--command", "git fetch --prune")
    before = store.read_text()
    add("--tech", "git", "--command", "git gc")
    assert store.read_text().startswith(before)


def test_grouping_and_sort_order():
    entries = [
        Entry("zsh", "bindkey -L"),
        Entry("azure/pim", "az rest --method GET --url <long-url>"),
        Entry("azure/pim", "az login"),
        Entry("kong", "deck ping"),
        Entry("azure/keyvault", "az keyvault secret list --vault-name <v>"),
        Entry("git", "git log --oneline"),
        Entry("git", "git st"),
        Entry("azure", "az account list"),
        Entry("azure", "az account show --query name -o tsv"),
        Entry("kubectl", "kubectl get pods"),
        Entry("ansible", "ansible-playbook site.yml"),
    ]
    groups = grouped(entries)
    assert [tech for tech, _ in groups] == [
        "azure", "azure/keyvault", "azure/pim", "git", "kubectl", "kong", "ansible", "zsh",
    ]
    by_tech = dict(groups)
    assert [e.command for e in by_tech["azure"]] == ["az account list", "az account show --query name -o tsv"]
    assert [e.command for e in by_tech["azure/pim"]] == ["az login", "az rest --method GET --url <long-url>"]
    assert [e.command for e in by_tech["git"]] == ["git st", "git log --oneline"]


def test_subgroup_without_parent_entries_still_gets_top_header(store, capsys):
    save(store, [Entry("azure/pim", "az login"), Entry("git", "git st")])
    main(["all"])
    lines = [line.rstrip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    start = next(i for i, line in enumerate(lines) if line.startswith("── azure "))
    assert lines[start + 1] == "   › azure/pim"
    assert lines[start + 2].startswith("     az login")
    assert lines[lines.index("── git " + "─" * 113) + 1].startswith("     git st")  # same column as subgroup commands


def test_tech_filter_includes_subgroups():
    assert matches_tech("azure/pim", "azure")
    assert matches_tech("azure", "azure")
    assert not matches_tech("azure/pim", "azure/keyvault")
    assert not matches_tech("azureml", "azure")


def test_show_tech_and_unknown_tech(store, capsys):
    assert main(["azure"]) == 0
    out = capsys.readouterr().out
    assert "azure/pim" in out and "git log" not in out
    assert main(["azure/pim"]) == 0
    out = capsys.readouterr().out
    assert "roleEligibilitySchedules" in "".join(out.split()) and "az account show" not in out
    with pytest.raises(SystemExit) as exc:
        main(["nope"])
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "unknown tech" in err and "azure/pim" in err


def test_long_commands_wrap_but_are_never_truncated(store, capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "60")
    command = "az rest --method GET --url https://graph.microsoft.com/v1.0/roleManagement/directory/roleEligibilitySchedules"
    save(store, [Entry("azure/pim", command)])
    main(["azure/pim"])
    out = capsys.readouterr().out
    assert "…" not in out
    assert command.replace(" ", "") in "".join(out.split())
    assert all(len(line) <= 60 for line in out.splitlines())


def test_search_all_words_any_field_any_order(store, capsys):
    add("--tech", "azure/keyvault", "--command", "az keyvault secret set --vault-name <v> --name <k> --value <val>",
        "--desc", "store a secret")
    assert main(["search", "SET", "keyvault"]) == 0
    out = capsys.readouterr().out
    assert "az keyvault secret set" in out and "roleEligibilitySchedules" not in out
    # One word from the description, one from the tech.
    assert main(["search", "store", "azure"]) == 0
    assert "az keyvault secret set" in capsys.readouterr().out


def test_search_scope_and_no_results(store, capsys):
    assert main(["search", "--tech", "kubectl", "log"]) == 0
    out = capsys.readouterr().out
    assert "kubectl logs" in out and "git log" not in out
    with pytest.raises(SystemExit) as exc:
        main(["search", "pim", "kubectl"])
    assert exc.value.code == 1
    assert "no matching" in capsys.readouterr().err


def test_search_highlights_matches(store, monkeypatch):
    from rich.console import Console
    from cmds.store import load as load_entries
    from cmds.view import render
    console = Console(width=100, force_terminal=True, color_system="standard", file=open(store.parent / "o", "w"))
    render(load_entries(store), console, highlight=["pim"])
    console.file.close()
    out = (store.parent / "o").read_text()
    assert "\x1b[" in out and "PIM" in out


def test_rm_deletes_chosen_entry(store, monkeypatch, capsys):
    answers = iter(["1", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert main(["rm"]) == 0
    remaining = load(store)
    assert len(remaining) == 5
    assert "az account show --query name -o tsv" not in [e.command for e in remaining]


def test_broken_store_exits_2(store, capsys):
    store.write_text("- just a string\n")
    assert main(["all"]) == 2
    assert "needs 'tech' and 'command'" in capsys.readouterr().err


def test_banner_styles(store, capsys):
    main(["all"])
    out = capsys.readouterr().out
    assert any("█" in line and "command notebook · 6 entries" in line for line in out.splitlines())  # beside
    assert "░" in out and "────" in out
    assert main(["style", "goth"]) == 0
    assert "style: goth" in (store.parent / "settings.yaml").read_text()
    main(["all"])
    assert "── command notebook · 6 entries ──" in capsys.readouterr().out
    assert main(["style", "plain"]) == 0
    main(["all"])
    assert "░" not in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        main(["style", "nope"])
    assert exc.value.code == 1


def test_color_setting(store, capsys):
    from cmds.view import THEMES, theme
    assert theme() is THEMES["blue"]
    assert main(["color", "orange"]) == 0
    assert "colour: orange" in capsys.readouterr().out
    assert theme() is THEMES["orange"]
    assert main(["style", "goth"]) == 0  # both settings live in the same file
    text = (store.parent / "settings.yaml").read_text()
    assert "color: orange" in text and "style: goth" in text
    assert main(["colour"]) == 0
    assert "colour: orange" in capsys.readouterr().out
