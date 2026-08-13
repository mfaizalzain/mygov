# Malaysia at a Glance — agent rules

Rules for any AI agent (Claude, Codex, Hermes) working in this repo. Keep CI
green and the deploy flow predictable. This file is auto-loaded by both Claude
Code and OpenAI Codex, so a rule added here binds every agent session.

## Service worker versioning (CI-enforced)

- `public/sw.js` precaches `/app.js` and `/styles.css` cache-first, keyed on
  the hand-written `VERSION` constant. Returning visitors keep running the old
  shell until the cache name changes.
- **Whenever you modify `public/app.js` or `public/styles.css`, you MUST bump
  `VERSION` in `public/sw.js` (e.g. `mygov-v24` → `mygov-v25`) and add a one-
  line changelog entry to the comment block above it.**
- CI (`.github/workflows/ci.yml`) fails the build otherwise. Do not wait for
  the failure email — bump in the same commit as the shell change.

## Repo discipline

- Run `git status` before any commit. Multiple agents may be editing this repo
  in parallel; commit only your own files, never `git add -A`.
- Branch flow: feature work lands on `dev` first (deploys to
  mygov-staging / mygov.faizalmzain.com), then merge `dev` → `main` when
  prod-ready (malaysia-at-a-glance.com). Ask before committing or pushing
  unless explicitly told to proceed.
- Never hand-transcribe binary/base64 content; write exact bytes via script.

## Data hygiene

- Only use data sources that are free and open, government first.
- Live/current data beats forecasts. A 7-day weather forecast chart was
  removed on purpose — do not re-add it.
- data.gov.my paths need a trailing slash (301 otherwise).
- The data-catalogue API allows 4 requests/minute per family; spread calls and
  back off on failure (the collectors use 4 attempts with growing delays).
