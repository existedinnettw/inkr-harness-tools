# inkr-harness-tools

Utility CLIs for inkr harness workflows.

## Commands

`inkr-skill-sync` (alias: `inkr-skill-symlink`)

Symlink discovered skill directories from a source tree into `AGENT_ROOT/skills`.

## Usage

```sh
uv run inkr-skill-sync .local .agents --recursive
```

```sh
uvx --from git+https://github.com/existedinnettw/inkr-harness-tools.git inkr-skill-sync .local .agents --recursive
```
