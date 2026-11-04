# Contributing

Thanks for helping make Noodle better. It is free software, licensed under the **GNU General Public License v3.0 or later** (see `LICENSE`). By contributing you agree that your contribution is licensed the same way.

## Good first contributions

- **A new integration.** Each one is a single module in `homepi/backend/homepi/plugins/`; the README section "Writing an integration" has a complete example.
- **Flow examples** for `homepi/backend/homepi/examples/flows/` (use placeholder device ids, English text and `enabled: false`).
- **Bug reports** with what you expected, what happened, and the log lines from the hub (System page, or `docker logs`).
- **Translations and wording** in the interface.

## Before you open a pull request

```bash
cd homepi/backend && pip install -r requirements-dev.txt && pytest
cd homepi/frontend && bun install && bun run check
```

- Add a test for what you change. Anything that migrates user data needs a test with the old shape and must be safe to run twice.
- Keep personal device ids, names, addresses and keys out of the code, examples and tests.
- New flows from files or an AI must keep starting switched off.
- `CLAUDE.md` describes how the code is organised, and `docs/AI.md` how flows are written.

## Being kind

Be respectful and assume good intent. Discussions are about the work, not the people.
