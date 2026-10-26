"""Shrink-only documentation gate for the World domain's functions and wire fields.

The floor is complete coverage, without a debt allowlist. ORM columns and
dataclass implementation attributes are outside the Pydantic wire contract.
Descriptions are checked structurally; their accuracy still needs code review.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "apps/api/src/domains/world"


def pydantic_models(trees: dict[Path, ast.Module]) -> set[str]:
    """Resolve local model inheritance, including the imported environment DTO."""
    names = {"BaseModel", "BaseSettings", "CompanionEnvironment", "TypedDict"}
    while True:
        found = {
            node.name
            for path, tree in trees.items()
            if path.name != "message_models.py"
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and any(isinstance(base, ast.Name) and base.id in names for base in node.bases)
        }
        if found <= names:
            return names
        names |= found


def _field_description(node: ast.AST | None) -> bool:
    """Recognize a nonempty Field description without evaluating contract source."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        return False
    if node.func.id != "Field":
        return False
    for keyword in node.keywords:
        if keyword.arg != "description":
            continue
        value = keyword.value
        return (
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and bool(value.value.strip())
        )
    return False


def _described(field: ast.AnnAssign) -> bool:
    """Accept normal model fields or Annotated metadata on nested TypedDict fields."""
    if _field_description(field.value):
        return True
    annotation = field.annotation
    if not isinstance(annotation, ast.Subscript) or not isinstance(annotation.value, ast.Name):
        return False
    if annotation.value.id != "Annotated" or not isinstance(annotation.slice, ast.Tuple):
        return False
    return any(_field_description(item) for item in annotation.slice.elts[1:])


def _model_fields(node: ast.ClassDef) -> list[ast.AnnAssign]:
    """Select direct contract fields, excluding Pydantic's configuration attribute."""
    return [
        field
        for field in node.body
        if isinstance(field, ast.AnnAssign)
        and isinstance(field.target, ast.Name)
        and field.target.id != "model_config"
    ]


def missing_contract_docs(trees: dict[Path, ast.Module]) -> list[str]:
    """Return every undocumented function or direct Pydantic field, with its location."""
    models = pydantic_models(trees)
    failures: list[str] = []
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not ast.get_docstring(
                node
            ):
                failures.append(f"{path.name}:{node.lineno} function {node.name}")
            if not isinstance(node, ast.ClassDef) or node.name not in models:
                continue
            for field in _model_fields(node):
                if not _described(field):
                    failures.append(
                        f"{path.name}:{field.lineno} field {node.name}.{ast.unparse(field.target)}"
                    )
    return failures


def main() -> int:
    """Report contract debt and fail on any regression above zero."""
    paths = [*DOMAIN.glob("*.py"), ROOT / "apps/api/src/core/config/world.py"]
    trees = {path: ast.parse(path.read_text(encoding="utf-8")) for path in paths}
    failures = missing_contract_docs(trees)
    for failure in failures:
        print(failure)
    print(f"World contract documentation: {len(failures)} missing descriptions/docstrings")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
