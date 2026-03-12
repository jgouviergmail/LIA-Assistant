#!/usr/bin/env python3
"""
Diagnostic script to check what fields Google API returns for a specific contact.

Usage:
    python scripts/diagnose_contact_fields.py people/c8792255687986101
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import asyncio

from src.domains.agents.tools.contacts_models import GetContactDetailsInput
from src.domains.agents.tools.google_contacts_tools import get_contact_details_tool


async def diagnose_contact(resource_name: str):
    """Diagnose what fields are returned for a contact."""

    print("=" * 80)
    print(f"DIAGNOSING CONTACT: {resource_name}")
    print("=" * 80)

    # This won't work standalone because it needs authentication
    # But we can analyze the tool's code to understand the issue

    print("\nChecking tool signature...")
    import inspect

    sig = inspect.signature(get_contact_details_tool.func)
    print(f"Function signature: {sig}")

    print("\nChecking tool input schema...")
    print(f"Input fields: {GetContactDetailsInput.model_fields.keys()}")

    print("\nChecking if 'fields' parameter is used...")
    source = inspect.getsource(get_contact_details_tool.func)

    # Find where fields parameter is used
    if "fields" in source:
        print("✅ 'fields' parameter found in tool code")

        # Look for FIELD_SETS or similar
        if "FIELD_SETS" in source:
            print("✅ FIELD_SETS reference found")
        else:
            print("⚠️  No FIELD_SETS reference")

        # Look for default fields
        if "fields =" in source or "fields=" in source:
            lines = [line for line in source.split("\n") if "fields" in line and "=" in line]
            print("\nField assignment lines:")
            for line in lines[:10]:
                print(f"  {line.strip()}")
    else:
        print("❌ 'fields' parameter NOT found in tool code")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    resource_name = sys.argv[1] if len(sys.argv) > 1 else "people/c8792255687986101"
    asyncio.run(diagnose_contact(resource_name))
