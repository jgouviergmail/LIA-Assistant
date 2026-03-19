"""
Accessibility tree extraction and formatting for LLM consumption.

Uses Chrome DevTools Protocol (CDP) to extract the full accessibility tree,
assigns [EN] references to interactive and content elements, and formats
the tree as indented text for the browser agent LLM.

Phase: evolution F7 — Browser Control (Playwright)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.constants import BROWSER_CONTENT_ROLES, BROWSER_INTERACTIVE_ROLES
from src.infrastructure.observability.metrics_browser import browser_snapshot_tokens

if TYPE_CHECKING:
    from playwright.async_api import CDPSession, Locator, Page

logger = structlog.get_logger(__name__)


@dataclass
class AXNode:
    """Represents a node in the accessibility tree."""

    node_id: str = ""
    role: str = ""
    name: str = ""
    value: str = ""
    description: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    children: list[AXNode] = field(default_factory=list)
    backend_dom_node_id: int | None = None
    ref: str | None = None  # [E1], [E2], etc.
    depth: int = 0


class AccessibilityTreeExtractor:
    """Extracts and formats accessibility trees from browser pages via CDP.

    The accessibility tree provides a semantic view of the page that is more
    token-efficient and LLM-friendly than raw HTML. Interactive elements
    (buttons, links, form fields) receive [EN] references that the browser
    agent uses to target actions.
    """

    async def extract(self, page: Page) -> list[AXNode]:
        """Extract the full accessibility tree using Chrome DevTools Protocol.

        Args:
            page: The Playwright page to extract the tree from.

        Returns:
            List of AXNode objects representing the tree structure.
        """
        from src.infrastructure.resilience.circuit_breaker import get_circuit_breaker

        cdp: CDPSession = await page.context.new_cdp_session(page)
        try:
            async with get_circuit_breaker("browser_cdp"):
                result = await cdp.send("Accessibility.getFullAXTree")
            nodes_raw = result.get("nodes", [])
            return self._parse_nodes(nodes_raw)
        except Exception as e:
            logger.error("browser_ax_tree_extraction_error", error=str(e))
            return []
        finally:
            await cdp.detach()

    def _parse_nodes(self, nodes_raw: list[dict[str, Any]]) -> list[AXNode]:
        """Parse raw CDP accessibility nodes into AXNode objects.

        Args:
            nodes_raw: Raw node dicts from CDP Accessibility.getFullAXTree.

        Returns:
            Flat list of AXNode objects with hierarchy via children.
        """
        nodes_by_id: dict[str, AXNode] = {}
        root_nodes: list[AXNode] = []

        for raw in nodes_raw:
            node = AXNode(
                node_id=raw.get("nodeId", ""),
                role=raw.get("role", {}).get("value", ""),
                name=raw.get("name", {}).get("value", ""),
                value=raw.get("value", {}).get("value", ""),
                description=raw.get("description", {}).get("value", ""),
                backend_dom_node_id=raw.get("backendDOMNodeId"),
            )

            # Extract properties
            for prop in raw.get("properties", []):
                prop_name = prop.get("name", "")
                prop_value = prop.get("value", {}).get("value", "")
                if prop_name and prop_value:
                    node.properties[prop_name] = prop_value

            nodes_by_id[node.node_id] = node

            # Build hierarchy
            parent_id = raw.get("parentId")
            if parent_id and parent_id in nodes_by_id:
                parent = nodes_by_id[parent_id]
                node.depth = parent.depth + 1
                parent.children.append(node)
            else:
                root_nodes.append(node)

        return root_nodes

    def assign_refs(self, nodes: list[AXNode]) -> list[AXNode]:
        """Assign [E1], [E2], ... references to interactive and content elements.

        Args:
            nodes: Tree of AXNode objects.

        Returns:
            Same tree with ref fields populated on qualifying nodes.
        """
        counter = [0]  # Mutable for closure

        def _walk(node_list: list[AXNode]) -> None:
            for node in node_list:
                if node.role in BROWSER_INTERACTIVE_ROLES:
                    counter[0] += 1
                    node.ref = f"E{counter[0]}"
                elif node.role in BROWSER_CONTENT_ROLES and node.name:
                    counter[0] += 1
                    node.ref = f"E{counter[0]}"
                _walk(node.children)

        _walk(nodes)
        return nodes

    def compact_tree(self, nodes: list[AXNode], max_depth: int | None = None) -> list[AXNode]:
        """Remove structural branches that contain no referenced elements.

        This typically reduces token count by ~60% while preserving all
        actionable elements and named content.

        Args:
            nodes: Tree of AXNode objects with refs assigned.
            max_depth: Maximum depth to retain (default: from settings).

        Returns:
            Compacted tree with structural-only branches removed.
        """
        if max_depth is None:
            max_depth = settings.browser_accessibility_max_depth

        # Roles that carry textual content (prices, descriptions) worth preserving
        # even without a ref, when they're near interactive elements.
        _text_roles = frozenset({"statictext", "text", "none", ""})

        # Navigation/chrome roles that clutter the tree without adding value
        # for content extraction. We keep them only at depth 0-1.
        _nav_roles = frozenset({"navigation", "banner", "complementary", "contentinfo"})

        def _has_refs(node: AXNode) -> bool:
            """Check if node or any descendant has a ref."""
            if node.ref:
                return True
            return any(_has_refs(child) for child in node.children)

        def _has_named_text(node: AXNode) -> bool:
            """Check if node has meaningful text content (e.g., prices, labels)."""
            return bool(node.name and node.role.lower() in _text_roles)

        def _compact(
            node_list: list[AXNode], depth: int, parent_has_ref: bool = False
        ) -> list[AXNode]:
            result: list[AXNode] = []
            for node in node_list:
                if depth >= max_depth and not node.ref:
                    continue
                # Skip deep navigation regions (menus, headers, footers)
                # They consume token budget without adding data value
                if node.role.lower() in _nav_roles and depth >= 1:
                    continue
                keep = (
                    node.ref
                    or _has_refs(node)
                    # Keep text nodes near interactive elements (prices, labels)
                    or (parent_has_ref and _has_named_text(node))
                )
                if keep:
                    node.children = _compact(
                        node.children, depth + 1, parent_has_ref=bool(node.ref)
                    )
                    result.append(node)
            return result

        return _compact(nodes, 0)

    def format_for_llm(self, nodes: list[AXNode]) -> str:
        """Format the accessibility tree as indented text for LLM consumption.

        Applies hard truncation if the result exceeds the configured
        max token budget (settings.browser_ax_tree_max_tokens).

        Args:
            nodes: Compacted tree of AXNode objects.

        Returns:
            Formatted string with [EN] references and indentation.
        """
        lines: list[str] = []
        max_tokens = settings.browser_ax_tree_max_tokens
        truncated_count = 0
        char_count = [0]  # Mutable for closure, tracks running total

        def _format(node_list: list[AXNode], indent: int) -> None:
            nonlocal truncated_count
            prefix = "  " * indent

            for node in node_list:
                # Estimate current token count (~4 chars per token)
                if char_count[0] // 4 >= max_tokens:
                    truncated_count += 1
                    continue

                parts: list[str] = []

                # Add ref if present
                if node.ref:
                    parts.append(f"[{node.ref}]")

                # Add role (skip empty/none roles for text nodes)
                if node.role and node.role.lower() not in ("none", ""):
                    parts.append(node.role)

                # Add name in quotes
                if node.name:
                    parts.append(f'"{node.name}"')

                # Add value if present (for form fields)
                if node.value:
                    parts.append(f'value="{node.value}"')

                # Add key properties
                if node.properties.get("required"):
                    parts.append("required")
                if node.properties.get("checked"):
                    parts.append("checked")
                if node.properties.get("disabled"):
                    parts.append("disabled")
                if "level" in node.properties:
                    parts.append(f"level={node.properties['level']}")

                line = f"{prefix}{' '.join(parts)}"
                lines.append(line)
                char_count[0] += len(line) + 1  # +1 for newline

                _format(node.children, indent + 1)

        _format(nodes, 0)

        result = "\n".join(lines)

        # Track estimated token count
        estimated_tokens = char_count[0] // 4
        browser_snapshot_tokens.observe(estimated_tokens)

        if truncated_count > 0:
            result += f"\n[... {truncated_count} additional elements truncated]"
            logger.info(
                "browser_ax_tree_truncated",
                truncated_count=truncated_count,
                max_tokens=max_tokens,
                estimated_tokens=estimated_tokens,
            )

        return result

    async def find_element_by_ref(self, page: Page, ref: str) -> Locator | None:
        """Resolve an [EN] reference to a Playwright Locator.

        Re-extracts a fresh accessibility tree to avoid stale references,
        finds the matching node, and resolves it to a DOM element via CDP.

        Args:
            page: The Playwright page containing the element.
            ref: The element reference (e.g., 'E3' — without brackets).

        Returns:
            A Playwright Locator for the element, or None if not found.
        """
        # Fresh tree extraction to avoid stale refs
        nodes = await self.extract(page)
        nodes = self.assign_refs(nodes)

        # Find the node with matching ref
        target_node = self._find_node_by_ref(nodes, ref)
        if not target_node or not target_node.backend_dom_node_id:
            logger.warning("browser_element_ref_not_found", ref=ref)
            return None

        # Resolve via CDP DOM.resolveNode
        cdp = await page.context.new_cdp_session(page)
        try:
            resolve_result = await cdp.send(
                "DOM.resolveNode",
                {"backendNodeId": target_node.backend_dom_node_id},
            )
            object_id = resolve_result.get("object", {}).get("objectId")
            if not object_id:
                return None

            # Use role-based locator for reliability
            if target_node.role and target_node.name:
                locator = page.get_by_role(target_node.role, name=target_node.name)  # type: ignore[arg-type]
                if await locator.count() > 0:
                    return locator.first

            # Fallback: evaluate to get a CSS selector
            desc_result = await cdp.send(
                "DOM.describeNode",
                {"backendNodeId": target_node.backend_dom_node_id},
            )
            node_desc = desc_result.get("node", {})
            node_name = node_desc.get("nodeName", "").lower()
            if node_name:
                # Try locating by combined role + attributes
                locator = page.locator(node_name).first
                return locator

            return None
        except Exception as e:
            logger.error("browser_element_resolve_error", ref=ref, error=str(e))
            return None
        finally:
            await cdp.detach()

    def _find_node_by_ref(self, nodes: list[AXNode], ref: str) -> AXNode | None:
        """Recursively find a node by its ref value.

        Args:
            nodes: Tree to search.
            ref: Reference string (e.g., 'E3').

        Returns:
            The matching AXNode, or None.
        """
        for node in nodes:
            if node.ref == ref:
                return node
            found = self._find_node_by_ref(node.children, ref)
            if found:
                return found
        return None
