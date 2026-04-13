"""Integration tests for skill symlink synchronization."""

from pathlib import Path

from inkr_harness_tools.skill_sync import parse_args, run


# Feature: Skill directory synchronization
# Rule: Matching skills are linked into AGENT_ROOT/skills.
def test_sync_links_matching_skill_in_recursive_mode(tmp_path: Path) -> None:
    # Scenario: recursive discovery links a matching skill directory
    source = tmp_path / "source"
    agent_root = tmp_path / "agent"
    skill_dir = source / "nested" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Demo\n", encoding="utf-8")

    # Given a source tree containing one recursive skill
    # When run() is invoked with recursive mode and matching regex
    args = parse_args(
        [
            str(source),
            str(agent_root),
            "--recursive",
            "--skill",
            "demo-.*",
        ]
    )
    exit_code = run(args)

    # Then the destination symlink exists and points to the source skill
    destination = agent_root / "skills" / "demo-skill"
    assert exit_code == 0
    assert destination.is_symlink()
    assert destination.resolve() == skill_dir.resolve()
