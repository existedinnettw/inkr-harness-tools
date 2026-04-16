"""Install a release asset from GitHub into a local bin directory."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

import httpx

DEFAULT_REPO = "existedinnettw/inkr-harness-tools"


def resolve_github_token() -> str | None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    gh_path = shutil.which("gh")
    if gh_path:
        try:
            result = subprocess.run(
                [gh_path, "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass

    try:
        result = subprocess.run(
            ["git", "config", "--get", "github.token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass

    netrc_path = Path.home() / "_netrc" if os.name == "nt" else Path.home() / ".netrc"
    if netrc_path.exists():
        try:
            content = netrc_path.read_text()
            in_github = False
            for line in content.splitlines():
                parts = line.split()
                if parts and parts[0] == "machine" and "github.com" in parts[-1]:
                    in_github = True
                elif in_github and parts and parts[0] == "password":
                    return parts[-1]
                elif in_github and parts and parts[0] in ("machine", "default"):
                    in_github = False
        except OSError:
            pass

    return None


def github_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "inkr-release-install",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def default_bin_dir(binary_name: str) -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Programs" / binary_name / "bin"
        return Path.home() / "AppData" / "Local" / "Programs" / binary_name / "bin"
    return Path.home() / ".local" / "bin"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install a GitHub release asset that matches your OS and architecture."
    )
    parser.add_argument(
        "--version",
        default="latest",
        help="Release tag to install (default: latest).",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help="GitHub repository in owner/name format.",
    )
    parser.add_argument(
        "--binary-name",
        default=None,
        help="Binary name and expected release asset prefix (defaults to repo name).",
    )
    parser.add_argument(
        "--bin-dir",
        default=None,
        help="Directory to install the binary into (default: platform-specific bin path).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected asset and destination without downloading.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="GitHub personal access token for authentication.",
    )
    return parser.parse_args(argv)


def detect_target() -> tuple[str, str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system.startswith("linux"):
        target_os = "linux"
        extension = ""
    elif system.startswith("darwin"):
        target_os = "macos"
        extension = ""
    elif system.startswith("windows"):
        target_os = "windows"
        extension = ".exe"
    else:
        raise RuntimeError(f"Unsupported operating system: {platform.system()}")

    if machine in {"x86_64", "amd64"}:
        arch = "x64"
    elif machine in {"aarch64", "arm64"}:
        arch = "arm64"
    else:
        raise RuntimeError(f"Unsupported architecture: {platform.machine()}")

    if target_os == "windows" and arch != "x64":
        raise RuntimeError(
            "No published Windows release asset for this architecture. Expected x64."
        )

    return target_os, arch, extension


def release_api_url(repo: str, version: str) -> str:
    if version == "latest":
        return f"https://api.github.com/repos/{repo}/releases/latest"
    encoded_tag = quote(version, safe="")
    return f"https://api.github.com/repos/{repo}/releases/tags/{encoded_tag}"


def download_release_metadata(repo: str, version: str, token: str | None) -> dict:
    url = release_api_url(repo, version)
    try:
        response = httpx.get(
            url,
            headers=github_headers(token),
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        hint = ""
        if exc.response.status_code == 404:
            if token:
                hint = (
                    " Verify the repository/tag exists and that your token can access it."
                )
            else:
                hint = (
                    " If this release exists in a private repo, set GH_TOKEN "
                    "(or GITHUB_TOKEN) or pass --token and retry."
                )
        raise RuntimeError(
            "Failed to fetch release metadata "
            f"({exc.response.status_code}): {exc.response.text}{hint}"
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to fetch release metadata: {exc}") from exc


def expected_asset_name(
    binary_name: str, tag: str, target_os: str, arch: str, extension: str
) -> str:
    return f"{binary_name}-{tag}-{target_os}-{arch}{extension}"


def infer_binary_name(repo: str) -> str:
    repo_name = repo.rsplit("/", maxsplit=1)[-1].strip()
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    if not repo_name:
        raise RuntimeError(
            f"Could not infer binary name from repo {repo!r}. Pass --binary-name explicitly."
        )
    return repo_name


def select_asset(metadata: dict, asset_name: str) -> dict:
    for asset in metadata.get("assets", []):
        if asset.get("name") == asset_name:
            return asset
    available = ", ".join(
        asset.get("name", "<unknown>") for asset in metadata.get("assets", [])
    )
    raise RuntimeError(
        f"Could not find release asset {asset_name!r}. Available assets: {available}"
    )


def download_asset(asset: dict, destination: Path, token: str | None) -> None:
    download_url = asset.get("browser_download_url")
    if not download_url:
        raise RuntimeError("Release asset is missing browser_download_url.")

    try:
        with httpx.stream(
            "GET",
            download_url,
            headers=github_headers(token),
            timeout=60.0,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                for chunk in response.iter_bytes(chunk_size=1024 * 64):
                    output.write(chunk)
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Failed to download asset ({exc.response.status_code}): {exc.response.text}"
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to download asset: {exc}") from exc


def install_binary(download_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(download_path), str(destination_path))
    if os.name != "nt":
        mode = destination_path.stat().st_mode
        destination_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def warn_if_not_on_path(bin_dir: Path, binary_name: str) -> None:
    path_env = os.environ.get("PATH", "")
    path_entries = [Path(entry).resolve() for entry in path_env.split(os.pathsep) if entry]
    if bin_dir.resolve() not in path_entries:
        print(
            f"Warning: {bin_dir} is not in PATH. Add it to run {binary_name} directly.",
            file=sys.stderr,
        )


def run(args: argparse.Namespace) -> int:
    token = args.token or resolve_github_token()
    target_os, arch, extension = detect_target()
    metadata = download_release_metadata(args.repo, args.version, token)
    binary_name = args.binary_name or infer_binary_name(args.repo)
    tag = metadata.get("tag_name")
    if not tag:
        raise RuntimeError("Release metadata is missing tag_name.")

    asset_name = expected_asset_name(binary_name, tag, target_os, arch, extension)
    asset = select_asset(metadata, asset_name)

    bin_dir = (
        Path(args.bin_dir).expanduser()
        if args.bin_dir
        else default_bin_dir(binary_name).expanduser()
    )
    binary_filename = binary_name + extension
    destination_path = bin_dir / binary_filename

    if args.dry_run:
        print(f"repo: {args.repo}")
        print(f"tag: {tag}")
        print(f"asset: {asset_name}")
        print(f"install_to: {destination_path}")
        return 0

    temp_prefix = re.sub(r"[^A-Za-z0-9_-]", "-", binary_name)
    with tempfile.TemporaryDirectory(prefix=f"{temp_prefix}-install-") as temp_dir:
        temp_path = Path(temp_dir) / binary_filename
        download_asset(asset, temp_path, token)
        install_binary(temp_path, destination_path)

    print(f"Installed {binary_name} {tag} to {destination_path}")
    warn_if_not_on_path(bin_dir, binary_name)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
