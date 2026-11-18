# waybar-opencode — OpenCode Go usage widget for Waybar

One bar pill showing the percent of your OpenCode Go **5-hour window** still
remaining, refreshed every 60s or on click. Hovering shows a tooltip with
usage bars for the 5h / weekly / monthly windows, reset countdowns, and the
Zen prepaid balance.

API modeled on the OpenCode Go support added in
[omacash PR #1](https://github.com/baranskyi/omacash/pull/1) (`baranskyi/omacash`):

- `GET {base}/zen/go/v1/usage` — Go quota. `usage.{rolling,weekly,monthly}.percent`
  is the **used** share (0–100); `status` is `ok` or `rate-limited`; `resetsAt`
  is an ISO-8601 timestamp.
- `GET {base}/console/api/billing/status` — Zen prepaid balance in
  `balanceMicroCents` (1 USD = 100,000,000).

Go is the headline when both are available; Zen dollars appear in the tooltip.

## Screenshot (tooltip)

```
OpenCode Go — quota used
5h    ██████░░░░░░░░░░░░░░    28% · resets in 2h 5m
Week  ████████░░░░░░░░░░░░    40% · resets in 4d 3h
Month ████████████░░░░░░░░    61% · resets in 12d 1h
Zen prepaid balance: $12.34
Updated 14:05:22
```

Collapsed states, chosen by the worst window:

| Text        | Meaning                            | Class   |
|-------------|------------------------------------|---------|
| `OC 5h 72%` | 72% of the 5h window remaining     | `ok`    |
| `OC 5h 12%` | under 30% remaining                | `warn`  |
| `OC 5h 0%`  | under 10% remaining / rate-limited | `crit`  |
| `OC $12.34` | Zen-only account, prepaid balance  | `ok`    |
| `~OC 5h 72%`| stale cache after a fetch failure  | `stale` |
| `OC ✗`      | fetch failed, no usable cache      | `error` |
| `OC ⚠`      | no API key configured              | `nokey` |

## Install

1. Copy (or clone) this directory to
   `~/.config/waybar/waybar_opencode/`.

2. Provide the key — either:

   - `$OPENCODE_API_KEY` in Waybar's environment (e.g. via Hyprland
     `env = OPENCODE_API_KEY=…`), or
   - a key file: `~/.config/waybar/waybar_opencode/key` containing the key,
     `chmod 600`. Get one at <https://opencode.ai/console>.

3. Add `module.jsonc`'s block to your waybar config and restart Waybar:

   ```bash
   killall waybar && waybar &
   ```

4. Optional: merge `style.css.example` into your `style.css` so the pill
   turns yellow/red as the quota drains.

## Module options

- `signal: 10` — click sends `SIGRTMIN+10` to Waybar, which re-runs the
  script immediately. Change it if 10 is taken (`8` and `12` are used by
  the pipewire and codexbar modules in this config).
- `interval: 60` — one refresh per minute.
- `OPENCODE_ICON` env var — change the collapsed prefix (default `OC`).
- `OPENCODE_BASE_URL` env var — override the API base (default
  `https://opencode.ai`; https enforced except for loopback, for tests).

## Behavior

- On a failed fetch the script shows the last good data with a `~` prefix
  and a stale note in the tooltip; the cache lives in
  `~/.cache/waybar-opencode/usage.json` (mode 600) and is trusted for 7 days.
- Click (left) forces a refresh; click (right) opens the OpenCode console.
- Stdlib only, no pip packages.

## Test

```bash
python3 tests/mock_server.py go &   # fixture mock from the PR data
OPENCODE_BASE_URL=http://127.0.0.1:8931 OPENCODE_API_KEY=test \
  ./opencode_usage.py
```

`go` = Go subscription, `rl` = rate-limited, `zen` = Zen-only, `none` = 401.
