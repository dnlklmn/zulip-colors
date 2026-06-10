# zulip-colors

Source of truth for Zulip's redesigned color system. `tokens.json` holds the
tokens in [Tokens Studio](https://tokens.studio/) / W3C design-token format; the
scripts in `tools/` translate them into the concrete formats each consumer needs,
so a single token edit regenerates every downstream artifact.

## Token structure

- **`global`** — primitive ramps: `primary.50`–`primary.950`, `primary-dim.*`,
  `neutral.*`. Stored as hex.
- **`dark-app`, `dark-web`, `light-web`** — semantic roles (e.g.
  `background.default`, `link.hover`, `button.background`) whose `$value` is a
  `{dot.path}` reference resolved against `global` (or against another role in
  the same set, e.g. `fill.match-background → {background.default}`).
- `$themes` / `$metadata` — Tokens Studio bookkeeping.

## Generated outputs (`dist/`)

`python tools/build.py` writes, per semantic set:

- **`<set>.hex.json`** — flat `role → lowercase hex`.
- **`<set>.hsl.css`** — a custom-property block in stylelint-compliant
  `hsl(238deg 28% 21%)` (modern syntax, `deg`, minimal precision that
  round-trips exactly). Each var carries a `/* <set> <role> ← <ref> */` trace.
  Prefix and scope selector are configurable per set in `build.config.json`.

and one paired file:

- **`email.css`** — a light/dark hex table for every role, plus example rules
  (light defaults + a `@media (prefers-color-scheme: dark)` block with
  `!important`, literal hex — email clients support neither `hsl()` nor
  `var()`, and an inliner moves base rules inline so dark overrides need
  `!important`).

`dist/` is committed; CI fails if it is out of date.

## Scripts

| Command | Purpose |
| --- | --- |
| `python tools/validate.py` | Assert every value round-trips `hex → hsl(rounded) → rgb` to the exact source RGB. Fails the build otherwise. |
| `python tools/build.py` | Regenerate everything in `dist/`. |
| `python tools/check_drift.py /path/to/zulip` | Scan the consumer files in a `zulip/zulip` checkout and report any color that no longer matches a current token (with the nearest token as a hint). |

`build.config.json` controls output dir, per-set CSS prefix/selector, the
email light/dark pairing and example rules, and the `consumers` list the drift
checker scans (file, which sets count as “known”, an optional `include` line
filter to scope noisy files, and an `ignore` list for intentional non-token
colors).

## Keeping consumers in sync

The consumer files live in `zulip/zulip`:

- `templates/zerver/emails/email.css`
- `web/styles/portico/legacy_portico.css`

After changing tokens, run `check_drift.py` against a checkout to see exactly
which lines to regenerate, then paste the relevant `dist/` output.

## Automation

- **CI** — `.github/workflows/tokens.yml` runs `validate.py` + `build.py` on
  every change to the tokens, scripts, or `dist/`, and fails if `dist/` is stale.
- **Pre-commit hook** — install once with:

  ```bash
  git config core.hooksPath tools/git-hooks
  ```

  It validates and regenerates `dist/` on every commit that touches tokens,
  staging the refreshed output so a stale palette can’t be committed.

All scripts are pure Python standard library (`json`, `colorsys`); no
dependencies to install.
