#!/usr/bin/env python3
"""Build consumer-ready color outputs from tokens.json.

For every semantic set it emits:
  - dist/<set>.hex.json   flat role -> lowercase hex
  - dist/<set>.hsl.css    custom-property block, stylelint-compliant hsl()

and one paired email file:
  - dist/email.css        light defaults + dark @media block, literal hex

Run after any change to tokens.json. CI fails if dist/ is left stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import tokenkit as tk

GENERATED = "AUTO-GENERATED from tokens.json by tools/build.py — do not edit by hand."


def role_to_var(prefix: str, role: str) -> str:
    return prefix + role.replace(".", "-")


def hex_json(resolver: tk.Resolver, set_name: str) -> str:
    data = {e["role"]: tk.normalize_hex(e["hex"]) for e in resolver.entries(set_name)}
    return json.dumps(data, indent=2) + "\n"


def hsl_css(resolver: tk.Resolver, set_name: str, prefix: str, selector: str) -> str:
    lines = [f"/* {GENERATED} (set: {set_name}) */", f"{selector} {{"]
    for e in resolver.entries(set_name):
        var = role_to_var(prefix, e["role"])
        trace = e["ref"] or "literal"
        # Trailing "/* <set> <role> ... */" is the annotation check_drift.py reads.
        lines.append(f"    {var}: {tk.hex_to_css_hsl(e['hex'])}; /* {set_name} {e['role']} ← {trace} */")
    lines.append("}")
    return "\n".join(lines) + "\n"


def email_css(resolver: tk.Resolver, email_cfg: dict) -> str:
    light, dark = email_cfg["light"], email_cfg["dark"]
    lmap, dmap = resolver.role_map(light), resolver.role_map(dark)
    roles = list(lmap) + [r for r in dmap if r not in lmap]

    lines = [f"/* {GENERATED} */",
             f"/* Email palette — light default = {light}, dark = {dark}. Hex only;",
             "   email clients support neither hsl() nor var(). */",
             "",
             "/*  role                       light      dark"]
    width = max(len(r) for r in roles)
    for r in roles:
        lh = lmap.get(r, "        -")
        dh = dmap.get(r, "        -")
        lines.append(f"    {r.ljust(width)}  {lh}    {dh}")
    lines.append("*/")

    rules = email_cfg.get("rules") or []
    if rules:
        lines.append("")
        lines.append("/* Example generated rules (light = default rule set). */")
        for rule in rules:
            lines.append(f"{rule['selector']} {{")
            for prop, role in rule["properties"].items():
                lines.append(f"    {prop}: {lmap[role]}; /* {light} {role} */")
            lines.append("}")
        lines.append("")
        lines.append("@media (prefers-color-scheme: dark) {")
        for rule in rules:
            lines.append(f"    {rule['selector']} {{")
            for prop, role in rule["properties"].items():
                # !important: the CSS inliner moves base rules inline, so the
                # dark overrides must win against those inline styles.
                lines.append(f"        {prop}: {dmap[role]} !important; /* {dark} {role} */")
            lines.append("    }")
        lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    tokens = tk.load_tokens()
    config = tk.load_config()
    global_set = config.get("globalSet", "global")
    resolver = tk.Resolver(tokens, global_set)

    out_dir = tk.REPO_ROOT / config.get("outputDir", "dist")
    out_dir.mkdir(exist_ok=True)

    css_cfg = config.get("css", {})
    default_prefix = css_cfg.get("defaultPrefix", "--color-")
    set_cfg = css_cfg.get("sets", {})

    written: list[Path] = []
    for set_name in tk.semantic_sets(tokens, global_set):
        (out_dir / f"{set_name}.hex.json").write_text(hex_json(resolver, set_name))
        cfg = set_cfg.get(set_name, {})
        prefix = cfg.get("prefix", default_prefix)
        selector = cfg.get("selector", f".{set_name}")
        (out_dir / f"{set_name}.hsl.css").write_text(
            hsl_css(resolver, set_name, prefix, selector)
        )
        written += [out_dir / f"{set_name}.hex.json", out_dir / f"{set_name}.hsl.css"]

    if "email" in config:
        (out_dir / "email.css").write_text(email_css(resolver, config["email"]))
        written.append(out_dir / "email.css")

    rel = sorted(str(p.relative_to(tk.REPO_ROOT)) for p in written)
    print(f"✓ wrote {len(written)} file(s):")
    for r in rel:
        print(f"    {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
