"""Unit tests for top-level CLI entrypoint."""

from inkr_harness_tools import main


# Feature: Package CLI entrypoint behavior
# Rule: Running the entrypoint should print the package banner.
def test_main_prints_package_name(capsys) -> None:
    # Scenario: entrypoint prints a stable banner
    # Given the top-level entrypoint is imported
    # When main() is executed
    main()

    # Then the package banner is printed
    captured = capsys.readouterr()
    assert captured.out.strip() == "inkr-harness-tools"
