"""Shared helpers for the zulip-colors token build pipeline.

Loads ``tokens.json`` (Tokens Studio / W3C format), resolves ``{dot.path}``
references against the ``global`` primitive ramps, and converts hex values to
stylelint-compliant ``hsl()`` at the minimum precision that round-trips exactly
back to the source RGB.

Pure stdlib (json + colorsys) so the build needs no dependencies.
"""

from __future__ import annotations

import colorsys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKENS_PATH = REPO_ROOT / "tokens.json"
CONFIG_PATH = REPO_ROOT / "build.config.json"

# Keys in tokens.json that are metadata, not token sets.
META_KEYS = {"$themes", "$metadata"}


def load_tokens(path: Path = TOKENS_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


def semantic_sets(tokens: dict, global_set: str = "global") -> list[str]:
    """The non-primitive token sets, in document order."""
    return [k for k in tokens if k not in META_KEYS and k != global_set]


class Resolver:
    """Resolves token references to concrete hex values.

    A reference is the ``{a.b.c}`` form stored in ``$value``. It resolves
    against the global primitive ramps first, then against roles in the same
    semantic set (e.g. ``fill.match-background -> {background.default}``).
    """

    def __init__(self, tokens: dict, global_set: str = "global") -> None:
        self.tokens = tokens
        self.global_set = global_set
        self.prim = self._primitive_map()

    def _primitive_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for group, items in self.tokens[self.global_set].items():
            for key, node in items.items():
                out[f"{group}.{key}"] = node["$value"]
        return out

    def resolve(self, set_name: str, value: str, _seen: frozenset = frozenset()) -> str:
        if not (isinstance(value, str) and value.startswith("{")):
            return value
        ref = value[1:-1]
        if ref in _seen:
            raise ValueError(f"Reference cycle through {{{ref}}}")
        seen = _seen | {ref}
        if ref in self.prim:
            return self.prim[ref]
        node = self._lookup(set_name, ref)
        if node is None:
            raise KeyError(f"Unresolved reference {{{ref}}} in set '{set_name}'")
        return self.resolve(set_name, node["$value"], seen)

    def _lookup(self, set_name: str, dotted: str) -> dict | None:
        node = self.tokens.get(set_name)
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node if isinstance(node, dict) and "$value" in node else None

    def entries(self, set_name: str) -> list[dict]:
        """Flatten a set to ordered ``{role, hex, ref}`` dicts.

        ``role`` is the dotted path (``background.default``), ``hex`` the
        resolved value, ``ref`` the immediate reference path it points at
        (``primary-dim.200``) or ``None`` for a literal.
        """
        out: list[dict] = []

        def walk(node: dict, path: list[str]) -> None:
            if isinstance(node, dict) and "$value" in node:
                raw = node["$value"]
                ref = raw[1:-1] if isinstance(raw, str) and raw.startswith("{") else None
                out.append(
                    {"role": ".".join(path), "hex": self.resolve(set_name, raw), "ref": ref}
                )
                return
            if isinstance(node, dict):
                for k, v in node.items():
                    if k.startswith("$"):
                        continue
                    walk(v, path + [k])

        walk(self.tokens[set_name], [])
        return out

    def role_map(self, set_name: str) -> dict[str, str]:
        """role -> normalized hex."""
        return {e["role"]: normalize_hex(e["hex"]) for e in self.entries(set_name)}


# ---------------------------------------------------------------------------
# Color conversions
# ---------------------------------------------------------------------------

def hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = value.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def normalize_hex(value: str) -> str:
    """Lowercase six-digit hex (what email consumers embed literally)."""
    return "#%02x%02x%02x" % hex_to_rgb(value)


def _fmt(x: float) -> str:
    """Format an HSL component, dropping a pointless trailing ``.0``."""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.3f}".rstrip("0").rstrip(".")


def _hsl_parts(value: str, ndigits: int) -> tuple[float, float, float]:
    r, g, b = (c / 255 for c in hex_to_rgb(value))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return (round(h * 360, ndigits), round(s * 100, ndigits), round(l * 100, ndigits))


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return (round(r * 255), round(g * 255), round(b * 255))


def hsl_round_trips(value: str, max_digits: int = 3) -> tuple[bool, int | None]:
    """Can ``value`` survive hex -> hsl(rounded) -> rgb? Returns (ok, digits)."""
    target = hex_to_rgb(value)
    for nd in range(max_digits + 1):
        if _hsl_to_rgb(*_hsl_parts(value, nd)) == target:
            return True, nd
    return False, None


def hex_to_css_hsl(value: str, max_digits: int = 3) -> str:
    """stylelint-compliant ``hsl(238deg 28% 21%)`` at minimal round-tripping precision."""
    target = hex_to_rgb(value)
    for nd in range(max_digits + 1):
        h, s, l = _hsl_parts(value, nd)
        if _hsl_to_rgb(h, s, l) == target:
            return f"hsl({_fmt(h)}deg {_fmt(s)}% {_fmt(l)}%)"
    raise ValueError(f"{value} does not round-trip within {max_digits} decimals")


def css_hsl_to_rgb(text: str) -> tuple[int, int, int]:
    """Parse an ``hsl(...)`` literal (modern or legacy syntax) to RGB."""
    inner = text[text.index("(") + 1 : text.rindex(")")]
    inner = inner.replace(",", " ").replace("/", " ")
    nums = [tok for tok in inner.split() if tok]
    h = float(nums[0].replace("deg", ""))
    s = float(nums[1].replace("%", ""))
    l = float(nums[2].replace("%", ""))
    return _hsl_to_rgb(h, s, l)
