"""Reject production regex imports outside an explicit allowlist."""

from __future__ import annotations

import ast
from pathlib import Path

ALLOWED_REGEX_IMPORTS: frozenset[Path] = frozenset()


def find_unapproved_regex_imports(
    root: Path, *, allowed: set[Path] | frozenset[Path] = ALLOWED_REGEX_IMPORTS
) -> list[Path]:
    """Return Python files that import ``re`` without approval."""

    violations: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _imports_regex(tree) and path not in allowed:
            violations.append(path)
    return violations


def _imports_regex(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name == "re" for alias in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "re":
            return True
    return False


def main() -> int:
    """Validate production regex imports."""

    violations = find_unapproved_regex_imports(Path("src"))
    for path in violations:
        print(f"checkregex: unapproved import re: {path}")
    if violations:
        return 1
    print("checkregex: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
