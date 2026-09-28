"""
Display module for v3 architecture.

Pure HTML mode - the markdown ResponseFormatter was removed.

The HtmlRenderer produces clean, semantic HTML with CSS classes the frontend
styles. This approach:
- saves LLM tokens (no formatting in the prompts)
- allows a rich, responsive UI
- separates content from presentation

This package follows modern Python conventions: imports are done explicitly
where needed rather than re-exported through __init__.py.

Main components (import directly from their modules):
- config: DisplayConfig, DisplayContext, Viewport, config_for_viewport, viewport_from_width
- html_renderer: HtmlRenderer, NestedData, get_html_renderer
- icons: Icons, icon, get_weather_icon, get_attachment_icon
- components/: Individual card renderers (contact_card, email_card, etc.)
"""
