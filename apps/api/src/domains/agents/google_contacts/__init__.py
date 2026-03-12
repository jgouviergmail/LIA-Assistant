"""
Google Contacts Agent module.

NOTE: Legacy manifest exports removed (Phase 5 cleanup).
All manifests now loaded via registry/catalogue_loader.py
See: src/domains/agents/google_contacts/catalogue_manifests.py

This package follows modern Python conventions: imports are done explicitly
where needed rather than re-exported through __init__.py.

Main components (import directly from their modules):
- catalogue_manifests: Tool manifests for contacts operations
- common_mappings: GOOGLE_CONTACTS_FIELD_MAPPINGS, get_contacts_field_mappings
"""
