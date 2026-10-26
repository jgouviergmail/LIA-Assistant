"""The World documentation gate checks real contract structure, including nested fields."""

import ast
import importlib.util
from pathlib import Path
from types import ModuleType


def checker() -> ModuleType:
    """Load the standalone gate without running its repository scan."""
    path = Path(__file__).resolve().parents[4] / "scripts/audit/world_contract_docs.py"
    spec = importlib.util.spec_from_file_location("world_contract_docs", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate_finds_nested_functions_and_inherited_wire_fields() -> None:
    source = '''
class StrictModel(BaseModel): pass
class Request(StrictModel):
    amount: int = Field(ge=0)
def outer():
    """Own an inner transition."""
    def mutate(): pass
'''
    findings = checker().missing_contract_docs({Path("sample.py"): ast.parse(source)})
    assert len(findings) == 2
    assert any("Request.amount" in finding for finding in findings)
    assert any("mutate" in finding for finding in findings)


def test_gate_checks_typed_dict_field_metadata_as_part_of_the_wire_contract() -> None:
    source = """
class Position(TypedDict):
    x: Annotated[float, Field(description="Ground coordinate.")]
    y: float
"""
    findings = checker().missing_contract_docs({Path("sample.py"): ast.parse(source)})
    assert len(findings) == 1
    assert "Position.y" in findings[0]


def test_gate_rejects_empty_descriptions_and_ignores_orm_columns() -> None:
    gate = checker()
    trees = {
        Path("request.py"): ast.parse(
            'class Request(BaseModel):\n    value: int = Field(description="  ")'
        ),
        Path("message_models.py"): ast.parse(
            "class WorldMessageAttempt(BaseModel):\n    id: Mapped[str] = mapped_column()"
        ),
    }
    findings = gate.missing_contract_docs(trees)
    assert len(findings) == 1
    assert "Request.value" in findings[0]
