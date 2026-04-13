# inkr-harness-tools

Utility CLIs for inkr harness workflows.

## Commands

`inkr-skill-sync` (alias: `inkr-skill-symlink`)

Symlink discovered skill directories from a source tree into `AGENT_ROOT/skills`.
Filter linked skills by regex with `-s, --skill <skills>` (default: `"*"` for all skills).

## Usage

```sh
uv run inkr-skill-sync .local .agents --recursive
```

```sh
uv run inkr-skill-sync .local .agents --recursive --skill '^openai-.*'
```

```sh
uvx --from git+https://github.com/existedinnettw/inkr-harness-tools.git inkr-skill-sync .local .agents --recursive
```

## Development

```sh
uv sync --dev
uv run pytest
uv run pre-commit run --all-files
```
