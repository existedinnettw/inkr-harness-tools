"""Unit tests for release installer behavior."""

from __future__ import annotations

import httpx
import pytest

from inkr_harness_tools.release_install import download_release_metadata, parse_args, run


def _raise_404(*_args, **_kwargs) -> None:
    request = httpx.Request("GET", "https://api.github.com/repos/o/r/releases/latest")
    response = httpx.Response(404, request=request, text='{"message":"Not Found"}')
    raise httpx.HTTPStatusError("Not Found", request=request, response=response)


def test_404_hint_without_token_mentions_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", _raise_404)

    with pytest.raises(RuntimeError) as exc_info:
        download_release_metadata("owner/repo", "latest", token=None)

    message = str(exc_info.value)
    assert "GH_TOKEN" in message
    assert "--token" in message


def test_404_hint_with_token_mentions_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", _raise_404)

    with pytest.raises(RuntimeError) as exc_info:
        download_release_metadata("owner/repo", "latest", token="token")

    message = str(exc_info.value)
    assert "repository/tag exists" in message
    assert "GH_TOKEN" not in message


def test_run_infers_binary_name_from_repo_in_dry_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "inkr_harness_tools.release_install.detect_target",
        lambda: ("windows", "x64", ".exe"),
    )
    monkeypatch.setattr(
        "inkr_harness_tools.release_install.download_release_metadata",
        lambda *_args, **_kwargs: {
            "tag_name": "v1.0.0-alpha.5",
            "assets": [
                {"name": "code_work_spawner-v1.0.0-alpha.5-windows-x64.exe"},
            ],
        },
    )

    args = parse_args(
        [
            "--repo",
            "existedinnettw/code_work_spawner",
            "--version",
            "v1.0.0-alpha.5",
            "--dry-run",
        ]
    )
    assert run(args) == 0
    output = capsys.readouterr().out
    assert "asset: code_work_spawner-v1.0.0-alpha.5-windows-x64.exe" in output
