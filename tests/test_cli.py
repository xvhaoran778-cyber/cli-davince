import json

from click.testing import CliRunner

from cli_anything.resolve.cli import Context, cli

from .fakes import fake_client


def test_status_json_output():
    client, resolve = fake_client()
    resolve.manager.CreateProject("Demo")
    result = CliRunner().invoke(cli, ["--json", "status"], obj=Context(True, client))
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["project"] == "Demo"


def test_delete_requires_confirmation():
    client, resolve = fake_client()
    project = resolve.manager.CreateProject("Demo")
    project.GetMediaPool().CreateEmptyTimeline("Main")
    result = CliRunner().invoke(cli, ["timeline", "delete", "Main"], obj=Context(False, client))
    assert result.exit_code != 0
    assert isinstance(result.exception, Exception)
