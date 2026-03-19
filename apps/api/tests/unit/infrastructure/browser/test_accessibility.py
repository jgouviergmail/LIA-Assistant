"""
Unit tests for accessibility tree extraction and formatting.

Phase: evolution F7 — Browser Control (Playwright)
"""

from src.infrastructure.browser.accessibility import AccessibilityTreeExtractor, AXNode


class TestAccessibilityTreeExtractor:
    """Tests for AccessibilityTreeExtractor."""

    def setup_method(self):
        """Create a fresh extractor."""
        self.extractor = AccessibilityTreeExtractor()

    # ========================================================================
    # assign_refs
    # ========================================================================

    def test_assign_refs_interactive_elements(self):
        """Interactive elements get [EN] references."""
        nodes = [
            AXNode(node_id="1", role="button", name="Submit"),
            AXNode(node_id="2", role="link", name="Home"),
            AXNode(node_id="3", role="textbox", name="Email"),
        ]
        result = self.extractor.assign_refs(nodes)
        assert result[0].ref == "E1"
        assert result[1].ref == "E2"
        assert result[2].ref == "E3"

    def test_assign_refs_content_elements_need_name(self):
        """Content elements get refs only if they have a name."""
        nodes = [
            AXNode(node_id="1", role="heading", name="Welcome"),
            AXNode(node_id="2", role="heading", name=""),  # No name
            AXNode(node_id="3", role="paragraph", name="Some text"),
        ]
        result = self.extractor.assign_refs(nodes)
        assert result[0].ref == "E1"
        assert result[1].ref is None  # No name → no ref
        assert result[2].ref == "E2"

    def test_assign_refs_nested(self):
        """Refs are assigned depth-first in nested tree."""
        child = AXNode(node_id="2", role="button", name="Click")
        parent = AXNode(node_id="1", role="generic", name="", children=[child])
        self.extractor.assign_refs([parent])
        assert parent.ref is None  # generic without name
        assert child.ref == "E1"

    def test_assign_refs_structural_elements_skipped(self):
        """Structural elements (generic, group) without name get no ref."""
        nodes = [
            AXNode(node_id="1", role="generic", name=""),
            AXNode(node_id="2", role="group", name=""),
        ]
        result = self.extractor.assign_refs(nodes)
        assert all(n.ref is None for n in result)

    # ========================================================================
    # compact_tree
    # ========================================================================

    def test_compact_removes_empty_branches(self):
        """Branches with no refs are removed."""
        empty_child = AXNode(node_id="2", role="generic", name="")
        ref_child = AXNode(node_id="3", role="button", name="OK", ref="E1")
        root = AXNode(
            node_id="1",
            role="generic",
            name="",
            children=[empty_child, ref_child],
        )
        result = self.extractor.compact_tree([root], max_depth=10)
        assert len(result) == 1
        assert len(result[0].children) == 1  # Only ref_child kept
        assert result[0].children[0].ref == "E1"

    def test_compact_preserves_text_near_refs(self):
        """Text nodes near interactive elements are preserved."""
        price_text = AXNode(node_id="3", role="statictext", name="99,99 EUR")
        link = AXNode(
            node_id="2",
            role="link",
            name="Product",
            ref="E1",
            children=[price_text],
        )
        root = AXNode(node_id="1", role="generic", name="", children=[link])
        result = self.extractor.compact_tree([root], max_depth=10)
        assert len(result) == 1
        assert len(result[0].children) == 1  # link preserved
        assert len(result[0].children[0].children) == 1  # price text preserved

    # ========================================================================
    # format_for_llm
    # ========================================================================

    def test_format_basic(self):
        """Basic formatting produces readable output."""
        nodes = [
            AXNode(node_id="1", role="button", name="Submit", ref="E1"),
            AXNode(node_id="2", role="link", name="Home", ref="E2"),
        ]
        result = self.extractor.format_for_llm(nodes)
        assert '[E1] button "Submit"' in result
        assert '[E2] link "Home"' in result

    def test_format_indentation(self):
        """Nested nodes are indented."""
        child = AXNode(node_id="2", role="button", name="OK", ref="E1")
        parent = AXNode(node_id="1", role="generic", name="", children=[child])
        result = self.extractor.format_for_llm([parent])
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert lines[1].startswith("  ")  # Child indented

    def test_format_properties(self):
        """Properties like required, checked, disabled are shown."""
        node = AXNode(
            node_id="1",
            role="textbox",
            name="Email",
            ref="E1",
            properties={"required": True, "disabled": True},
        )
        result = self.extractor.format_for_llm([node])
        assert "required" in result
        assert "disabled" in result

    def test_format_truncation(self):
        """Output is truncated when exceeding token budget."""
        # Create many nodes to exceed budget
        nodes = [
            AXNode(node_id=str(i), role="button", name=f"Button {i}" * 20, ref=f"E{i}")
            for i in range(500)
        ]
        result = self.extractor.format_for_llm(nodes)
        assert "truncated" in result

    def test_format_empty_tree(self):
        """Empty tree returns empty string."""
        result = self.extractor.format_for_llm([])
        assert result == ""

    # ========================================================================
    # _find_node_by_ref
    # ========================================================================

    def test_find_node_by_ref_found(self):
        """Find existing ref in tree."""
        target = AXNode(node_id="3", role="button", name="OK", ref="E2")
        root = AXNode(
            node_id="1",
            role="generic",
            name="",
            children=[
                AXNode(node_id="2", role="link", name="Home", ref="E1"),
                target,
            ],
        )
        result = self.extractor._find_node_by_ref([root], "E2")
        assert result is target

    def test_find_node_by_ref_not_found(self):
        """Return None for non-existent ref."""
        root = AXNode(node_id="1", role="button", name="OK", ref="E1")
        result = self.extractor._find_node_by_ref([root], "E99")
        assert result is None

    def test_find_node_by_ref_deep_nesting(self):
        """Find ref in deeply nested tree."""
        deep = AXNode(node_id="4", role="button", name="Deep", ref="E1")
        mid = AXNode(node_id="3", role="generic", name="", children=[deep])
        top = AXNode(node_id="2", role="generic", name="", children=[mid])
        root = AXNode(node_id="1", role="generic", name="", children=[top])
        result = self.extractor._find_node_by_ref([root], "E1")
        assert result is deep
