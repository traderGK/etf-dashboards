# ops/

## refresh-terminal.yml.txt

A ready-to-use GitHub Actions workflow that rebuilds `/terminal` hourly on its own.

It is **not active**. The deploy token used from the workstation lacks the `workflow`
OAuth scope, so it cannot create files under `.github/workflows/`.

Until it is promoted, the terminal rebuild is driven from the tail of
`scripts/refresh_data.py`, which runs on the existing "Refresh ETF Signal Data"
workflow every 10 minutes and rebuilds only when the last build is >55 min old.

### To promote it (about 30 seconds, in the browser)

1. Open the repo on github.com → **Add file → Create new file**
2. Name it `.github/workflows/refresh-terminal.yml`
3. Paste the contents of `refresh-terminal.yml.txt`
4. Commit to `main`
5. Delete the `_rebuild_terminal()` block at the bottom of `scripts/refresh_data.py`

### Knobs (env vars, both paths)

| Variable                | Default | Meaning                                    |
|-------------------------|---------|--------------------------------------------|
| `TERMINAL_REBUILD`      | `1`     | Set to `0` to disable rebuilds entirely     |
| `TERMINAL_MAX_AGE_MIN`  | `55`    | Rebuild only if the last build is older     |

A rebuild that produces more than 3 failed modules aborts without writing, so a bad
data day can never overwrite a good terminal.
