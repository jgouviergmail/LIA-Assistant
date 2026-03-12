"""
Display module for v3 architecture.

Mode HTML pur - le ResponseFormatter markdown a été supprimé.

Le HtmlRenderer produit du HTML propre et sémantique avec des classes CSS
que le frontend style. Cette approche:
- Économise les tokens LLM (pas de formatage dans les prompts)
- Permet une UI riche et responsive
- Sépare le contenu de la présentation

This package follows modern Python conventions: imports are done explicitly
where needed rather than re-exported through __init__.py.

Main components (import directly from their modules):
- config: DisplayConfig, DisplayContext, Viewport, config_for_viewport, viewport_from_width
- html_renderer: HtmlRenderer, NestedData, get_html_renderer
- icons: Icons, icon, get_weather_icon, get_attachment_icon
- components/: Individual card renderers (contact_card, email_card, etc.)
"""
