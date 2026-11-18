#!/usr/bin/env python3
"""Waybar widget: OpenCode Go usage quota, with Zen balance in the tooltip.

Collapsed:  "5h 72%"  (percent of the 5-hour window still remaining)
Hover:      pango tooltip with usage bars for the 5h / weekly / monthly
            windows, reset countdowns, and the Zen prepaid balance.
Click:      waybar re-runs this script via SIGRTMIN+N (wire it in the module
            config; see README).

Usage API modeled on the omacash PR baranskyi/omacash#1:
  GET {base}/zen/go/v1/usage            -> {"usage": {"rolling": {...}, ...}}
  GET {base}/console/api/billing/status -> {"balanceMicroCents": "..."}

Stdlib only. Key comes from $OPENCODE_API_KEY or ~/.config/waybar/waybar_opencode/key.
"""

import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ICON = os.environ.get("OPENCODE_ICON", "OC")
BASE = os.environ.get("OPENCODE_BASE_URL", "https://opencode.ai").rstrip("/")
KEY_FILE = Path("~/.config/waybar/waybar_opencode/key").expanduser()
CACHE_DIR = Path("~/.cache/waybar-opencode").expanduser()
CACHE_FILE = CACHE_DIR / "usage.json"
CACHE_MAX_AGE = 7 * 24 * 3600  # seconds; older cache is ignored
MICROCENTS_PER_USD = 100_000_000
WINDOW_LABELS = (("rolling", "5h"), ("weekly", "Week"), ("monthly", "Month"))
BAR_WIDTH = 20

GREEN, YELLOW, ORANGE, RED, DIM, FAINT = (
    "#69ff94", "#ffffa5", "#ff9977", "#dd532e", "#c8c8c8", "#7d7d7d")


def resolve_key():
    key = os.environ.get("OPENCODE_API_KEY", "").strip()
    if key:
        return key
    try:
        return KEY_FILE.read_text().strip()
    except OSError:
        return ""


def check_base(base):
    parts = urllib.parse.urlsplit(base)
    ok = parts.scheme == "https" or (
        parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost", "::1"))
    if not ok:
        raise RuntimeError(f"OPENCODE_BASE_URL must use https: {base}")


def fetch(url, key, timeout=10):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "waybar-opencode/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"network: {e.reason}") from e


def parse_go_usage(body):
    """Validate /zen/go/v1/usage; return {name: {used, status, resetsAt}}."""
    windows = {}
    usage = json.loads(body.decode("utf-8", "replace")).get("usage")
    if not isinstance(usage, dict):
        raise ValueError("usage object missing")
    for name in ("rolling", "weekly", "monthly"):
        win = usage.get(name)
        if win is None and name != "rolling":
            continue
        if not isinstance(win, dict):
            raise ValueError(f"{name} is not an object")
        used = float(win["percent"])
        if not math.isfinite(used) or not 0 <= used <= 100:
            raise ValueError(f"{name}.percent out of range")
        status = win.get("status") or "ok"
        resets_at = win.get("resetsAt")
        if resets_at is not None and not isinstance(resets_at, str):
            raise ValueError(f"{name}.resetsAt must be a string")
        windows[name] = {"used": used, "status": status, "resetsAt": resets_at}
    return windows


def parse_zen_balance(body):
    micro = json.loads(body.decode("utf-8", "replace"))["balanceMicroCents"]
    usd = float(micro) / MICROCENTS_PER_USD
    return max(0.0, usd)


def fmt_pct(x):
    q = round(x * 10) / 10
    return f"{q:g}"


def fmt_usd(x):
    return f"{x:,.2f}"


def countdown(iso):
    """'in 2h 5m' for an ISO-8601 timestamp, '' if absent/in the past/unparseable."""
    if not iso:
        return ""
    try:
        target = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        secs = (target - datetime.now(timezone.utc)).total_seconds()
    except (ValueError, TypeError, OSError):
        return ""
    if secs <= 0:
        return "now"
    days, rem = int(secs // 86400), int(secs % 86400)
    hours, mins = rem // 3600, (rem % 3600) // 60
    if days:
        return f"in {days}d {hours}h"
    if hours:
        return f"in {hours}h {mins}m"
    return f"in {mins}m"


def severity(max_used):
    if max_used >= 90:
        return "crit"
    if max_used >= 70:
        return "warn"
    return "ok"


def bar(used, color):
    filled = round(used / 100 * BAR_WIDTH)
    fill = "█" * filled
    empty = "░" * (BAR_WIDTH - filled)
    return (f"<span color='{color}'>{fill}</span>"
            f"<span color='{FAINT}'>{empty}</span>")


def window_color(used):
    if used >= 90:
        return RED
    if used >= 70:
        return ORANGE
    return GREEN


def cache_write(data):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data))
        CACHE_FILE.chmod(0o600)
    except OSError:
        pass


def cache_read():
    try:
        data = json.loads(CACHE_FILE.read_text())
        if time.time() - data.get("ts", 0) > CACHE_MAX_AGE:
            return None
        return data
    except (OSError, ValueError):
        return None


def emit(text, tooltip, state):
    print(json.dumps({"text": text, "tooltip": tooltip,
                      "class": ["opencode", state]}))


def tooltip_html(windows, zen, note):
    title = "<b>OpenCode Go</b> — quota used" if windows \
        else "<b>OpenCode Zen</b> — prepaid balance"
    lines = [title, "<tt>"]
    for name, label in WINDOW_LABELS:
        win = windows.get(name)
        if win is None:
            continue
        used = 100.0 if win["status"] == "rate-limited" else win["used"]
        color = window_color(used)
        reset = countdown(win["resetsAt"])
        tag = " · rate limited" if win["status"] == "rate-limited" else ""
        pad = " " * (5 - len(label))
        lines.append(f"{label}{pad}{bar(used, color)} {fmt_pct(used):>5}%{tag}"
                     + (f" · resets {reset}" if reset else ""))
    lines.append("</tt>")
    if zen is not None:
        lines.append(f"Zen prepaid balance: <b>${fmt_usd(zen)}</b>")
    if note:
        lines.append(f"<span color='{DIM}'>{note}</span>")
    return "\n".join(lines)


def live(key):
    """Fetch both endpoints; returns (windows|None, zen|None, note)."""
    check_base(BASE)
    go = zen = None
    go_status = zen_status = None
    note = ""
    try:
        go_status, body = fetch(BASE + "/zen/go/v1/usage", key)
        if go_status == 200:
            go = parse_go_usage(body)
    except RuntimeError as e:
        note = str(e)
    except (ValueError, KeyError, TypeError) as e:
        note = f"unexpected Go usage response: {e}"
    try:
        zen_status, body = fetch(BASE + "/console/api/billing/status", key)
        if zen_status == 200:
            zen = parse_zen_balance(body)
    except RuntimeError as e:
        note = note or str(e)
    except (ValueError, KeyError, TypeError) as e:
        note = note or f"unexpected Zen billing response: {e}"

    if go is not None or zen is not None:
        return go, zen, note

    # Nothing usable: explain why.
    if note:
        raise RuntimeError(note)
    if go_status in (401, 403) and zen_status in (401, 403):
        if go_status == 401 or zen_status == 401:
            raise RuntimeError("OpenCode rejected the API key (401)")
        raise RuntimeError("Key has no Go subscription and cannot read Zen "
                           "billing (403) — use a Go key, or a personal key "
                           "with Billing: Read")
    raise RuntimeError(f"OpenCode did not answer with data "
                       f"(go={go_status}, zen={zen_status})")


def main():
    key = resolve_key()
    if not key:
        emit(f"{ICON} ⚠",
             "No OpenCode API key.\n\n"
             "Set $OPENCODE_API_KEY, or write the key to\n"
             "~/.config/waybar/waybar_opencode/key (chmod 600).\n\n"
             "Go key from https://opencode.ai/console", "nokey")
        return

    try:
        go, zen, note = live(key)
        windows = go or {}
        max_used = max((w["used"] for w in windows.values()), default=0.0)
        if go:
            rolling = 100.0 if windows["rolling"]["status"] == "rate-limited" \
                else windows["rolling"]["used"]
            text = f"{ICON} 5h {fmt_pct(100 - rolling)}%"
        else:
            text = f"{ICON} ${fmt_usd(zen)}"
            max_used = 0.0
        state = severity(max_used)
        ts = time.time()
        cache_write({"ts": ts, "windows": windows, "zen": zen})
    except RuntimeError as e:
        cached = cache_read()
        if cached is None:
            emit(f"{ICON} ✗", f"OpenCode usage unavailable\n\n{e}", "error")
            return
        windows, zen = cached["windows"], cached.get("zen")
        age = int((time.time() - cached["ts"]) / 60)
        note = f"⚠ stale ({age}m old) — {e}"
        if windows:
            rolling = windows.get("rolling", {"used": 0.0})
            used = 100.0 if rolling.get("status") == "rate-limited" \
                else rolling["used"]
            text = f"~{ICON} 5h {fmt_pct(max(0, 100 - used))}%"
        elif zen is not None:
            text = f"~{ICON} ${fmt_usd(zen)}"
        else:
            return
        state = "stale"
        ts = cached["ts"]

    if ts:
        stamp = datetime.fromtimestamp(ts, timezone.utc).astimezone()
        note = (note + "\n" if note else "") + f"Updated {stamp:%H:%M:%S}"
    emit(text, tooltip_html(windows, zen, note), state)


if __name__ == "__main__":
    main()
