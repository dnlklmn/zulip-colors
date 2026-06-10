#!/usr/bin/env python3
"""Report consumer colors that no longer match the current tokens.

For each configured consumer file it extracts every color literal (hex or
``hsl()``) and checks it against the set of current token values (the global
primitives plus the resolved values of the relevant semantic sets). Any literal
that matches no current token is reported as possible drift, together with the
nearest token so you can see what it likely should become.

Scoping (which files, which sets, an optional line filter, and intentional
non-token exceptions) lives in build.config.json under "consumers"; this keeps
the huge legacy_portico.css from drowning the signal.

Usage:
    python tools/check_drift.py /path/to/zulip
    python tools/check_drift.py /path/to/zulip --file web/styles/portico/legacy_portico.css
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import tokenkit as tk

COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|hsl\([^)]*\)")


def literal_to_rgb(text: str) -> tuple[int, int, int] | None:
    try:
        return tk.hex_to_rgb(text) if text.startswith("#") else tk.css_hsl_to_rgb(text)
    except (ValueError, IndexError):
        return None


def known_palette(resolver: tk.Resolver, set_names: list[str]) -> dict[tuple, str]:
    """rgb -> label for every primitive plus the resolved values of set_names."""
    palette: dict[tuple, str] = {}
    for path, hexval in resolver.prim.items():
        palette.setdefault(tk.hex_to_rgb(hexval), path)
    for set_name in set_names:
        for e in resolver.entries(set_name):
            palette.setdefault(tk.hex_to_rgb(e["hex"]), f"{set_name} {e['role']}")
    return palette


def nearest(rgb: tuple, palette: dict[tuple, str]) -> tuple[str, str, float]:
    best, best_d = None, None
    for prgb, label in palette.items():
        d = sum((a - b) ** 2 for a, b in zip(rgb, prgb)) ** 0.5
        if best_d is None or d < best_d:
            best, best_d, best_rgb = label, d, prgb
    return best, "#%02x%02x%02x" % best_rgb, best_d


def scan(path: Path, palette: dict[tuple, str], include: str | None, ignore: set[str]) -> list[str]:
    inc_re = re.compile(include) if include else None
    problems: list[str] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if inc_re and not inc_re.search(line):
            continue
        for m in COLOR_RE.finditer(line):
            rgb = literal_to_rgb(m.group(0))
            if rgb is None:
                continue
            norm = "#%02x%02x%02x" % rgb
            if norm in ignore or rgb in palette:
                continue
            label, near_hex, dist = nearest(rgb, palette)
            hint = f" — nearest {near_hex} ({label})" if dist <= 32 else ""
            problems.append(f"{path}:{lineno}: {m.group(0)} matches no current token{hint}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zulip_root", help="path to a zulip/zulip checkout")
    parser.add_argument("--file", action="append", dest="only_files",
                        help="restrict to this consumer file (relative path); repeatable")
    args = parser.parse_args()

    root = Path(args.zulip_root)
    if not root.is_dir():
        parser.error(f"not a directory: {root}")

    tokens = tk.load_tokens()
    config = tk.load_config()
    resolver = tk.Resolver(tokens, config.get("globalSet", "global"))
    consumers = config.get("consumers", [])
    if not consumers:
        parser.error("no 'consumers' configured in build.config.json")

    all_problems: list[str] = []
    scanned = 0
    for c in consumers:
        if args.only_files and c["file"] not in args.only_files:
            continue
        path = root / c["file"]
        if not path.exists():
            print(f"… skipping missing file: {c['file']}")
            continue
        scanned += 1
        palette = known_palette(resolver, c.get("sets", tk.semantic_sets(tokens)))
        ignore = {h.lower() for h in c.get("ignore", [])}
        all_problems += scan(path, palette, c.get("include"), ignore)

    if all_problems:
        print(f"✗ {len(all_problems)} color(s) drifted from the tokens:")
        for p in all_problems:
            print(f"    {p}")
        return 1

    print(f"✓ no drift across {scanned} consumer file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
