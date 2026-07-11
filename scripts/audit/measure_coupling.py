#!/usr/bin/env python3
"""Reproducible domain-coupling metrics for the 360° technical audit.

Builds the domain-level import graph of ``src/domains`` via AST and reports,
per domain: afferent coupling (Ca — how many domains import it), efferent
coupling (Ce — how many domains it imports) and instability
I = Ce / (Ca + Ce), plus the list of bidirectional import cycles (A imports
B and B imports A).

Two edge semantics are reported side by side:

- **all** (default figures, comparable with audit cycle 3): every
  ``import``/``from ... import`` targeting another domain counts, including
  imports inside ``if TYPE_CHECKING:`` blocks.
- **runtime** (``_rt`` columns): imports inside ``if TYPE_CHECKING:`` blocks
  are excluded. Only runtime edges can create circular-import failures or
  boot-order fragility, so the Stable Dependencies assessment reads these;
  the *all* figures keep the historical series comparable.

Usage (from apps/api/):
    python ../../scripts/audit/measure_coupling.py [DOMAINS_DIR] [--detail DOMAIN]

Defaults to ./src/domains. Standard library only — no dependencies.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

# edges[src][dst] = {"runtime": set of "file:line" sites, "typing": idem}
EdgeMap = dict[str, dict[str, dict[str, set[str]]]]


def _is_type_checking_if(node: ast.If) -> bool:
    """True when the ``if`` guard is a ``TYPE_CHECKING`` block."""
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _type_checking_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    """Line ranges covered by ``if TYPE_CHECKING:`` blocks in the tree."""
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_if(node):
            end = max(
                getattr(child, "end_lineno", node.lineno) or node.lineno
                for child in ast.walk(node)
            )
            ranges.append((node.lineno, end))
    return ranges


def _collect_edges(
    tree: ast.AST, src_domain: str, relpath: str, domain_set: set[str], edges: EdgeMap
) -> None:
    """Record every cross-domain import of one parsed file into ``edges``."""
    tc_ranges = _type_checking_ranges(tree)
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        elif isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        for module in modules:
            if not module.startswith("src.domains."):
                continue
            parts = module.split(".")
            dst = parts[2] if len(parts) > 2 else None
            if not dst or dst not in domain_set or dst == src_domain:
                continue
            lineno = getattr(node, "lineno", 0)
            kind = "typing" if any(a <= lineno <= b for a, b in tc_ranges) else "runtime"
            edges[src_domain][dst][kind].add(f"{relpath}:{lineno}")


def build_edges(domains_root: Path) -> tuple[list[str], EdgeMap, list[str]]:
    """Parse every domain file and return (domains, edge map, unparsable files)."""
    domains = sorted(
        p.name for p in domains_root.iterdir() if p.is_dir() and not p.name.startswith("_")
    )
    domain_set = set(domains)
    edges: EdgeMap = defaultdict(
        lambda: defaultdict(lambda: {"runtime": set(), "typing": set()})
    )
    unparsable: list[str] = []
    for domain in domains:
        for path in sorted((domains_root / domain).rglob("*.py")):
            source = path.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(source)
            except SyntaxError:
                unparsable.append(str(path))
                continue
            _collect_edges(tree, domain, str(path.relative_to(domains_root)), domain_set, edges)
    return domains, edges, unparsable


def bidirectional_cycles(edges: EdgeMap, runtime_only: bool) -> list[tuple[str, str]]:
    """Sorted list of domain pairs importing each other (2-cycles)."""

    def has_edge(src: str, dst: str) -> bool:
        kinds = edges.get(src, {}).get(dst)
        if kinds is None:
            return False
        return bool(kinds["runtime"]) if runtime_only else bool(
            kinds["runtime"] or kinds["typing"]
        )

    pairs = {
        tuple(sorted((src, dst)))
        for src, dsts in edges.items()
        for dst in dsts
        if has_edge(src, dst) and has_edge(dst, src)
    }
    return sorted(pairs)  # type: ignore[arg-type]


def main(argv: list[str]) -> int:
    """Measure and print the domain coupling matrix and cycles."""
    args = [a for a in argv if not a.startswith("--")]
    detail_domain: str | None = None
    if "--detail" in argv:
        idx = argv.index("--detail")
        if idx + 1 >= len(argv):
            print("ERROR: --detail requires a domain name", file=sys.stderr)
            return 1
        detail_domain = argv[idx + 1]
        args = [a for a in args if a != detail_domain]

    domains_root = Path(args[0]) if args else Path("src/domains")
    if not domains_root.is_dir():
        print(f"ERROR: domains directory not found: {domains_root.resolve()}", file=sys.stderr)
        return 1

    domains, edges, unparsable = build_edges(domains_root)

    ca: dict[str, int] = defaultdict(int)
    ce: dict[str, int] = defaultdict(int)
    ca_rt: dict[str, int] = defaultdict(int)
    ce_rt: dict[str, int] = defaultdict(int)
    for src, dsts in edges.items():
        for dst, kinds in dsts.items():
            ce[src] += 1
            ca[dst] += 1
            if kinds["runtime"]:
                ce_rt[src] += 1
                ca_rt[dst] += 1

    print(f"domains={len(domains)} unparsable={len(unparsable)}")
    print(f"{'domain':<20} {'Ca':>3} {'Ce':>3} {'I':>5}   {'Ca_rt':>5} {'Ce_rt':>5} {'I_rt':>5}")
    for domain in sorted(domains, key=lambda d: (-(ca[d] + ce[d]), d)):
        total = ca[domain] + ce[domain]
        if total == 0:
            continue
        total_rt = ca_rt[domain] + ce_rt[domain]
        instability = ce[domain] / total
        instability_rt = (ce_rt[domain] / total_rt) if total_rt else 0.0
        print(
            f"{domain:<20} {ca[domain]:>3} {ce[domain]:>3} {instability:>5.2f}   "
            f"{ca_rt[domain]:>5} {ce_rt[domain]:>5} {instability_rt:>5.2f}"
        )

    for runtime_only, label in ((False, "all imports"), (True, "runtime-only")):
        cycles = bidirectional_cycles(edges, runtime_only)
        print(f"\nbidirectional cycles ({label}): {len(cycles)}")
        for pair in cycles:
            print(f"   {pair[0]} <-> {pair[1]}")

    if detail_domain is not None:
        print(f"\noutgoing edges of '{detail_domain}':")
        for dst, kinds in sorted(edges.get(detail_domain, {}).items()):
            for kind in ("runtime", "typing"):
                for site in sorted(kinds[kind]):
                    print(f"   {detail_domain} -> {dst:<20} [{kind}] {site}")

    if unparsable:
        print("\nWARNING — unparsable files (excluded from metrics):", file=sys.stderr)
        for path in unparsable:
            print(f"  {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
