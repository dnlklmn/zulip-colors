#!/usr/bin/env python3
"""Round-trip validator for the color tokens.

Every token value must survive ``hex -> hsl(rounded) -> rgb`` back to the exact
source RGB, so the generated ``hsl()`` for the web/app consumers is lossless.
Exits non-zero (and lists the offenders) if any value fails.
"""

from __future__ import annotations

import sys

import tokenkit as tk


def main() -> int:
    tokens = tk.load_tokens()
    config = tk.load_config()
    global_set = config.get("globalSet", "global")
    resolver = tk.Resolver(tokens, global_set)

    # Check primitives once, plus every resolved semantic value (a role may
    # point at an off-ramp literal, so resolved values are checked too).
    checked: dict[str, str] = {}  # hex -> first source label
    for path, hexval in resolver.prim.items():
        checked.setdefault(hexval.lower(), f"{global_set}.{path}")
    for set_name in tk.semantic_sets(tokens, global_set):
        for entry in resolver.entries(set_name):
            checked.setdefault(entry["hex"].lower(), f"{set_name} {entry['role']}")

    failures = []
    for hexval, label in sorted(checked.items()):
        ok, _ = tk.hsl_round_trips(hexval)
        if not ok:
            failures.append((hexval, label))

    if failures:
        print(f"✗ {len(failures)} value(s) do not round-trip hex -> hsl -> rgb:")
        for hexval, label in failures:
            print(f"    {hexval}  ({label})")
        return 1

    print(f"✓ {len(checked)} unique color values round-trip cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
