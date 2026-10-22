import pytest

from cmds.store import Entry, save

SAMPLE = [
    Entry("git", "git log --oneline --graph --decorate -20", "compact history graph"),
    Entry("git", "git branch --sort=-committerdate | head", "recently touched branches"),
    Entry("azure", "az account show --query name -o tsv", "current subscription"),
    Entry(
        "azure/pim",
        "az rest --method GET --url \"https://graph.microsoft.com/v1.0/roleManagement/directory/"
        "roleEligibilitySchedules?\\$filter=principalId eq '<object-id>'\"",
        "list my eligible PIM roles",
    ),
    Entry("kubectl", "kubectl logs -f deploy/<name> --since=10m", "tail logs of a deployment"),
    Entry("kubectl", "kubectl get pods -A --field-selector=status.phase!=Running", "pods that are not running"),
]


@pytest.fixture
def empty_store(tmp_path, monkeypatch):
    """Point cmds at a throwaway, not yet existing store file and a fixed terminal width."""
    path = tmp_path / "commands.yaml"
    monkeypatch.setenv("CMDS_FILE", str(path))
    monkeypatch.setenv("COLUMNS", "120")
    monkeypatch.setenv("TERM", "dumb")
    return path


@pytest.fixture
def store(empty_store):
    """The same store, pre-filled with six sample entries."""
    save(empty_store, SAMPLE)
    return empty_store
