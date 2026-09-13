"""Tests for CLI interface."""

from __future__ import annotations

from typer.testing import CliRunner
from cozmo.cli import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Cozmo AI Pipeline" in result.output


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Cozmo AI" in result.output
    assert "run" in result.output
    assert "benchmark" in result.output


def test_repeat_option_scores_several_pairs():
    from cozmo.cli import parse_repeat_pairs

    assert parse_repeat_pairs(["multiroom_home,multiroom_long", "bedroom_solo, multiroom_long"]) == [
        ["multiroom_home", "multiroom_long"],
        ["bedroom_solo", "multiroom_long"],
    ]


def test_repeat_option_rejects_a_value_that_is_not_a_pair():
    import pytest
    import typer

    from cozmo.cli import parse_repeat_pairs

    with pytest.raises(typer.BadParameter):
        parse_repeat_pairs(["multiroom_home"])

