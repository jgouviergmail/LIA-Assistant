"""Complete bounded tree witnesses reject leaks and detect replacement/content changes."""

import pytest

from src.domains.plugins.tree_state import tree_state

pytestmark = pytest.mark.unit


def test_complete_witness_changes_with_nested_bytes_or_empty_directory(tmp_path):
    root = tmp_path / "account" / "plugin"
    root.mkdir(parents=True)
    file = root / "manifest"
    file.write_bytes(b"original")
    original = tree_state(root, max_files=10, max_bytes=100)
    file.write_bytes(b"modified")
    assert tree_state(root, max_files=10, max_bytes=100) != original
    file.write_bytes(b"original")
    (root / "empty").mkdir()
    assert tree_state(root, max_files=10, max_bytes=100) != original


@pytest.mark.parametrize("kind", ["bytes", "entries", "link"])
def test_witness_refuses_oversize_or_linked_tree(tmp_path, kind):
    root = tmp_path / "account" / "plugin"
    root.mkdir(parents=True)
    if kind == "bytes":
        (root / "file").write_bytes(b"oversize")
    elif kind == "entries":
        for i in range(2):
            (root / str(i)).touch()
    else:
        outside = tmp_path / "secret"
        outside.write_bytes(b"secret")
        try:
            (root / "link").symlink_to(outside)
        except OSError:
            pytest.skip("this system refuses symbolic links")
    with pytest.raises(ValueError):
        tree_state(root, max_files=1, max_bytes=3)
