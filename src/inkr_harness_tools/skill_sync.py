"""Sync private skills into an agent root via directory symlinks."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


SKILL_FILE_NAME = "SKILL.md"


@dataclass(frozen=True)
class SyncConfig:
    source_root: Path
    agent_root: Path
    destination_root: Path
    recursive: bool
    remove_stale: bool
    dry_run: bool


@dataclass(frozen=True)
class SkillLink:
    name: str
    source_dir: Path
    skill_file: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover skill directories under SOURCE and link them into AGENT_ROOT/skills. "
            "This exposes local-only private skills to agent CLIs without copying contents."
        )
    )
    parser.add_argument("source", type=Path, help="Source directory containing skills or nested skill folders.")
    parser.add_argument("agent_root", type=Path, help="Agent root directory, for example .agents.")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Find SKILL.md files recursively under SOURCE instead of only direct child directories.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without changing files.")
    parser.add_argument(
        "--no-remove-stale",
        action="store_true",
        help="Do not remove stale destination symlinks that point inside SOURCE.",
    )
    return parser.parse_args(argv)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def resolve_existing_dir(path: Path, label: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except FileNotFoundError:
        fail(f"{label} does not exist: {path}")
    if not resolved.is_dir():
        fail(f"{label} is not a directory: {resolved}")
    return resolved


def resolve_agent_root(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.exists():
        if not expanded.is_dir():
            fail(f"agent root exists but is not a directory: {expanded}")
        return expanded.resolve(strict=True)
    return expanded.resolve(strict=False)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def resolve_link_target(path: Path) -> Path | None:
    if not path.is_symlink():
        return None
    target = path.readlink()
    if not target.is_absolute():
        target = path.parent / target
    return target.resolve(strict=False)


def points_inside_source(path: Path, source_root: Path) -> bool:
    target = resolve_link_target(path)
    return target is not None and is_relative_to(target, source_root)


def same_link_target(path: Path, target: Path) -> bool:
    current_target = resolve_link_target(path)
    return current_target is not None and current_target == target.resolve(strict=False)


def discover_direct_skills(source_root: Path) -> list[SkillLink]:
    skills: list[SkillLink] = []
    for child in sorted(source_root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        skill_file = child / SKILL_FILE_NAME
        if not skill_file.is_file():
            warn(f"skip non-skill directory: {child}")
            continue
        skills.append(SkillLink(name=child.name, source_dir=child.resolve(strict=True), skill_file=skill_file))
    return skills


def discover_recursive_skills(source_root: Path) -> list[SkillLink]:
    skills: list[SkillLink] = []
    seen_dirs: set[Path] = set()
    for skill_file in sorted(source_root.rglob(SKILL_FILE_NAME), key=lambda item: str(item).lower()):
        if not skill_file.is_file():
            continue
        source_dir = skill_file.parent.resolve(strict=True)
        if source_dir in seen_dirs:
            continue
        seen_dirs.add(source_dir)
        skills.append(SkillLink(name=source_dir.name, source_dir=source_dir, skill_file=skill_file))
    return skills


def validate_unique_names(skills: list[SkillLink]) -> None:
    by_name: dict[str, list[SkillLink]] = {}
    for skill in skills:
        by_name.setdefault(skill.name, []).append(skill)

    duplicates = {name: matches for name, matches in by_name.items() if len(matches) > 1}
    if not duplicates:
        return

    lines = ["duplicate skill directory names would collide in the destination:"]
    for name, matches in sorted(duplicates.items()):
        lines.append(f"  {name}:")
        for match in matches:
            lines.append(f"    - {match.skill_file}")
    fail("\n".join(lines))


def remove_link(path: Path, *, dry_run: bool) -> None:
    if dry_run:
        print(f"would remove stale link {path}")
        return
    path.unlink()
    print(f"removed stale link: {path}")


def create_link(source: Path, destination: Path, *, dry_run: bool) -> None:
    if dry_run:
        print(f"would link {destination} -> {source}")
        return
    destination.symlink_to(source, target_is_directory=True)
    print(f"linked skill: {destination} -> {source}")


def sync_links(config: SyncConfig, skills: list[SkillLink]) -> None:
    if not config.destination_root.exists():
        if config.dry_run:
            print(f"would create destination directory {config.destination_root}")
        else:
            config.destination_root.mkdir(parents=True, exist_ok=True)
            print(f"created destination directory: {config.destination_root}")

    source_names = {skill.name for skill in skills}
    for skill in skills:
        destination = config.destination_root / skill.name

        if destination.exists() or destination.is_symlink():
            if same_link_target(destination, skill.source_dir):
                continue
            if destination.is_symlink() and points_inside_source(destination, config.source_root):
                remove_link(destination, dry_run=config.dry_run)
            else:
                warn(f"skip existing non-owned destination: {destination}")
                continue

        create_link(skill.source_dir, destination, dry_run=config.dry_run)

    if not config.remove_stale or not config.destination_root.exists():
        return

    for destination in sorted(config.destination_root.iterdir(), key=lambda item: item.name.lower()):
        if destination.name in source_names:
            continue
        if destination.is_symlink() and points_inside_source(destination, config.source_root):
            remove_link(destination, dry_run=config.dry_run)


def build_config(args: argparse.Namespace) -> SyncConfig:
    source_root = resolve_existing_dir(args.source, "source")
    agent_root = resolve_agent_root(args.agent_root)
    destination_root = agent_root / "skills"

    if is_relative_to(destination_root.resolve(strict=False), source_root):
        fail("agent root must not place its skills directory inside source")

    return SyncConfig(
        source_root=source_root,
        agent_root=agent_root,
        destination_root=destination_root,
        recursive=args.recursive,
        remove_stale=not args.no_remove_stale,
        dry_run=args.dry_run,
    )


def run(args: argparse.Namespace) -> int:
    config = build_config(args)
    skills = discover_recursive_skills(config.source_root) if config.recursive else discover_direct_skills(config.source_root)
    validate_unique_names(skills)

    if not skills:
        warn(f"no {SKILL_FILE_NAME} files found under {config.source_root}")
        return 0

    print(f"source: {config.source_root}")
    print(f"agent root: {config.agent_root}")
    print(f"destination: {config.destination_root}")
    print(f"skills: {len(skills)}")
    sync_links(config, skills)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
