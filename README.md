# Hermes Agent

[Nous Research Hermes Agent](https://hermes-agent.nousresearch.com) — self-improving AI agent with persistent memory, skills, and multi-platform messaging.

This environment has Hermes **installed and ready**. Install lives under `~/.hermes/` (managed by the official installer), not in this git tree.

## Status

| Item | Location / command |
| --- | --- |
| Version | Hermes Agent v0.21.3 |
| Launcher | `~/.local/bin/hermes` |
| Config | `~/.hermes/config.yaml` |
| API keys | `~/.hermes/.env` |
| Source checkout | `~/.hermes/hermes-agent` |

## Start chatting

```bash
source ~/.bashrc   # ensure ~/.local/bin is on PATH
hermes             # classic CLI
# or
hermes --tui       # modern TUI
```

## First-time provider setup (required)

No LLM API keys are configured yet. Pick one path:

```bash
# Fastest: Nous Portal (OAuth, 300+ models + Tool Gateway)
hermes setup --portal

# Or interactive provider/model picker
hermes model

# Or full wizard
hermes setup
```

Then start a session with `hermes`.

## Useful commands

```bash
hermes doctor          # diagnose install / config
hermes status          # overview of env, keys, gateway
hermes gateway setup   # Telegram / Discord / Slack / etc.
hermes skills browse   # Skills Hub
hermes update          # pull latest
```

## Reinstall (this machine)

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Docs: [Quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart) · [Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation)
