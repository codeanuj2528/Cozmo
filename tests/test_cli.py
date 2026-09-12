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
