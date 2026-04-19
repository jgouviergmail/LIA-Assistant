"""Skill output builder — construct UnifiedToolOutput with rich skill widgets.

Transforms a parsed ``SkillScriptOutput`` (from stdout) into a
``UnifiedToolOutput`` with a ``SKILL_APP`` ``RegistryItem`` payload that the
frontend mounts as an interactive widget (iframe + image card).

Parallels ``src.infrastructure.mcp.utils.build_mcp_app_output`` but:
    - Simpler payload (no server_id, tool_arguments, resource_uri)
    - Injects a strict CSP into ``frame.html`` for user-owned skills
    - Does NOT inject CSP into ``frame.url`` (external — outside our control)

Security model:
    - User skills emitting ``frame.html`` receive a CSP meta tag that blocks
      outbound network (``connect-src 'none'``), iframes, and scripts other
      than inline. This prevents exfiltration via pixel/fetch.
    - System skills are trusted (admin-curated) and skip CSP injection.
    - All frames (user + system) render under an iframe sandbox without
      ``allow-same-origin`` — cookies and storage of the parent are unreachable.
"""

from __future__ import annotations

import re
import time

from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.constants import CONTEXT_DOMAIN_SKILL_APPS
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.skills.script_output import SkillScriptOutput

# CSP meta tag injected into user-skill frame.html to contain the iframe.
# - default-src 'none': deny by default
# - script-src 'unsafe-inline': allow inline <script> (the skill's own)
# - style-src 'unsafe-inline' https:: inline styles + CDN (e.g. Google Fonts)
# - img-src data: https:: data URIs and https images
# - font-src https:: CDN fonts only
# - connect-src 'none': block all fetch/XHR/WebSocket — prevents exfiltration
# - frame-src 'none': block nested iframes — prevents phishing chains
_USER_SKILL_CSP_META = (
    '<meta http-equiv="Content-Security-Policy" '
    "content=\"default-src 'none'; "
    "script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline' https:; "
    "img-src data: https:; "
    "font-src https:; "
    "connect-src 'none'; "
    "frame-src 'none';\">"
)

# Frame runtime snippet injected into every ``frame.html`` (system + user).
#
# Two behaviors in one snippet, to keep the injection point unique:
#
# 1. **Auto-resize** — emits ``ui/notifications/size-changed`` postMessage
#    events so ``useSkillAppBridge`` can resize the iframe to match the
#    actual content height. Measurement uses
#    ``document.body.getBoundingClientRect().bottom`` (iframe-resizer
#    pattern) rather than ``scrollHeight``/``offsetHeight`` which include
#    the iframe viewport and produce oversized frames. Fires on
#    DOMContentLoaded, load, ResizeObserver(body) and
#    ``document.fonts.ready``.
#
# 2. **Theme sync** — applies the LIA app theme (light/dark) to the iframe
#    so skills respect the user's choice even when it diverges from the OS
#    ``prefers-color-scheme``:
#       - Listens to ``ui/theme-changed`` notifications from the host.
#       - Reads ``hostContext.theme`` from the ``ui/initialize`` response.
#       - Falls back to ``prefers-color-scheme`` if no message is received.
#       - Applies ``document.documentElement.dataset.theme = 'light'|'dark'``,
#         which skill CSS selects via ``[data-theme="dark"]`` (preferred) or
#         ``@media (prefers-color-scheme: dark)`` (legacy fallback — still
#         works because the snippet ALSO keeps OS pref applied).
#
# The snippet is idempotent, self-contained, CSP-compatible (``script-src
# 'unsafe-inline'``). The CSS reset (``html,body { margin:0; padding:0 }``)
# neutralizes default browser margins that would inflate the measurement.
_AUTORESIZE_SCRIPT = """<style>
html,body{margin:0!important;padding:0!important;}
html{height:auto!important;}
body{height:auto!important;overflow:hidden!important;background:transparent!important;}
</style><script>(function(){
// -------- Theme sync --------
function applyTheme(theme){
  if(theme!=='dark'&&theme!=='light') return;
  try{document.documentElement.dataset.theme=theme;}catch(e){}
}
// Initial OS fallback — overridden by host messages if they arrive.
try{
  var mql=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)');
  applyTheme(mql&&mql.matches?'dark':'light');
  if(mql&&mql.addEventListener){
    mql.addEventListener('change',function(e){
      // OS change only applies when host has not taken over (no explicit theme yet).
      if(!document.documentElement.dataset.themeSource||
         document.documentElement.dataset.themeSource==='os'){
        document.documentElement.dataset.themeSource='os';
        applyTheme(e.matches?'dark':'light');
      }
    });
  }
}catch(e){}

// -------- Auto-resize --------
var lastH=0;
function measure(){
  if(!document.body) return 0;
  var rect=document.body.getBoundingClientRect();
  var h=Math.ceil(rect.bottom);
  return isFinite(h)&&h>0?h:0;
}
function report(){
  var h=measure();
  if(h<=0) return;
  if(Math.abs(h-lastH)<4) return;
  lastH=h;
  try{parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/size-changed',params:{height:h}},'*');}catch(e){}
}
function scheduleReport(){
  requestAnimationFrame(function(){requestAnimationFrame(report);});
}
if(document.readyState==='complete'||document.readyState==='interactive'){
  scheduleReport();
}
document.addEventListener('DOMContentLoaded',scheduleReport);
window.addEventListener('load',scheduleReport);
window.addEventListener('resize',report);
if(typeof ResizeObserver!=='undefined'){
  try{
    var ro=new ResizeObserver(scheduleReport);
    if(document.body) ro.observe(document.body);
  }catch(e){}
}
if(document.fonts&&document.fonts.ready&&document.fonts.ready.then){
  document.fonts.ready.then(scheduleReport).catch(function(){});
}

// -------- Host messages (theme + future) --------
window.addEventListener('message',function(ev){
  var msg=ev&&ev.data;
  if(!msg||msg.jsonrpc!=='2.0') return;
  // Response to our ui/initialize — theme lives in hostContext.theme
  if(msg.id!=null&&msg.result&&msg.result.hostContext&&msg.result.hostContext.theme){
    document.documentElement.dataset.themeSource='host';
    applyTheme(msg.result.hostContext.theme);
    return;
  }
  // Live notification: the user toggled the app theme.
  if(msg.method==='ui/theme-changed'&&msg.params&&msg.params.theme){
    document.documentElement.dataset.themeSource='host';
    applyTheme(msg.params.theme);
    return;
  }
  // Live notification: the user switched app locale.
  if(msg.method==='ui/locale-changed'&&msg.params&&msg.params.locale){
    try{document.documentElement.lang=String(msg.params.locale);}catch(e){}
    return;
  }
});

// -------- Kick ui/initialize handshake to receive hostContext.theme --------
try{
  parent.postMessage({jsonrpc:'2.0',id:1,method:'ui/initialize',params:{}},'*');
}catch(e){}
})();</script>"""


def _inject_csp_meta(html: str) -> str:
    """Inject the user-skill CSP meta tag into HTML content.

    Strategy:
        - If ``<head>`` exists: insert meta as first child of ``<head>``
        - If no ``<head>`` but ``<html>`` exists: insert ``<head>...</head>``
        - If neither: wrap the whole HTML in a full document structure

    The CSP is placed as early as possible in ``<head>`` to apply before any
    script executes.

    Args:
        html: Raw HTML from the skill's ``frame.html`` output.

    Returns:
        HTML with CSP meta tag injected.
    """
    head_open_match = re.search(r"<head[^>]*>", html, re.IGNORECASE)
    if head_open_match:
        insert_pos = head_open_match.end()
        return html[:insert_pos] + _USER_SKILL_CSP_META + html[insert_pos:]

    html_open_match = re.search(r"<html[^>]*>", html, re.IGNORECASE)
    if html_open_match:
        insert_pos = html_open_match.end()
        return html[:insert_pos] + f"<head>{_USER_SKILL_CSP_META}</head>" + html[insert_pos:]

    # No <html> or <head> — wrap in a full document
    return (
        "<!DOCTYPE html><html><head>"
        + _USER_SKILL_CSP_META
        + "</head><body>"
        + html
        + "</body></html>"
    )


def _inject_autoresize_script(html: str) -> str:
    """Inject the auto-resize postMessage snippet into HTML content.

    Strategy:
        - If ``</body>`` exists: insert script just before (preferred — runs
          after body content, observes final layout).
        - Else if ``</html>`` exists: insert just before closing tag.
        - Else: append at the very end.

    The snippet notifies the parent frame of the actual content height via
    ``ui/notifications/size-changed`` postMessage events, which
    :func:`useSkillAppBridge` consumes to resize the iframe dynamically.

    Args:
        html: HTML from the skill's ``frame.html`` output (already CSP-injected
            for user skills).

    Returns:
        HTML with auto-resize ``<script>`` appended near the end of the body.
    """
    body_close_match = re.search(r"</body\s*>", html, re.IGNORECASE)
    if body_close_match:
        insert_pos = body_close_match.start()
        return html[:insert_pos] + _AUTORESIZE_SCRIPT + html[insert_pos:]

    html_close_match = re.search(r"</html\s*>", html, re.IGNORECASE)
    if html_close_match:
        insert_pos = html_close_match.start()
        return html[:insert_pos] + _AUTORESIZE_SCRIPT + html[insert_pos:]

    return html + _AUTORESIZE_SCRIPT


def build_skill_app_output(
    output: SkillScriptOutput,
    skill_name: str,
    is_system_skill: bool,
    execution_time_ms: int = 0,
) -> UnifiedToolOutput:
    """Build a ``UnifiedToolOutput`` wrapping a ``SKILL_APP`` registry item.

    The returned output carries:
        - ``message``: the skill's ``text`` (short summary for the LLM reformulator)
        - ``registry_updates``: a single ``SKILL_APP`` item with the full payload

    The frontend detects the sentinel ``<div class="lia-skill-app">`` emitted
    by ``SkillAppSentinel`` and mounts the ``SkillAppWidget`` React component,
    which looks up the registry item by id and renders iframe/image.

    Args:
        output: Parsed ``SkillScriptOutput`` from the skill script.
        skill_name: Name of the emitting skill (for badge/display).
        is_system_skill: True for admin-curated system skills (no CSP forced),
            False for user skills (CSP injected into ``frame.html``).
        execution_time_ms: Script execution duration for telemetry.

    Returns:
        ``UnifiedToolOutput.data_success`` with the SKILL_APP registry item.
    """
    unique_key = f"{skill_name}_{time.time_ns()}"
    rid = generate_registry_id(RegistryItemType.SKILL_APP, unique_key)

    # Prepare frame payload
    html_content: str | None = None
    frame_url: str | None = None
    title: str | None = None
    aspect_ratio: float = 1.333
    if output.frame is not None:
        title = output.frame.title
        aspect_ratio = output.frame.aspect_ratio
        if output.frame.html is not None:
            # Inject CSP for user skills; system skills are trusted
            raw_html = output.frame.html if is_system_skill else _inject_csp_meta(output.frame.html)
            # Inject auto-resize snippet for every inline frame so the widget
            # can size the iframe to the actual content height via the
            # postMessage bridge — eliminates scrollbars caused by static
            # aspect-ratio defaults (system + user skills).
            html_content = _inject_autoresize_script(raw_html)
        elif output.frame.url is not None:
            frame_url = output.frame.url

    # Prepare image payload
    image_url: str | None = None
    image_alt: str | None = None
    if output.image is not None:
        image_url = output.image.url
        image_alt = output.image.alt

    payload: dict[str, object] = {
        FIELD_REGISTRY_ID: rid,
        "skill_name": skill_name,
        "html_content": html_content,
        "frame_url": frame_url,
        "image_url": image_url,
        "image_alt": image_alt,
        "title": title or skill_name,
        "aspect_ratio": aspect_ratio,
        "text_summary": output.text,
        "is_system_skill": is_system_skill,
    }

    registry_item = RegistryItem(
        id=rid,
        type=RegistryItemType.SKILL_APP,
        payload=payload,
        meta=RegistryItemMeta(
            source=f"skill_{skill_name}",
            domain=CONTEXT_DOMAIN_SKILL_APPS,
            tool_name="run_skill_script",
        ),
    )

    # The LLM reformulator receives output.text as the message; the full
    # rich payload stays in the registry for the frontend only.
    return UnifiedToolOutput.data_success(
        message=output.text,
        registry_updates={rid: registry_item},
        structured_data={
            CONTEXT_DOMAIN_SKILL_APPS: [
                {
                    "skill_name": skill_name,
                    "title": title or skill_name,
                    FIELD_REGISTRY_ID: rid,
                }
            ],
        },
        metadata={
            "skill_name": skill_name,
            "execution_time_ms": execution_time_ms,
            "has_frame": output.frame is not None,
            "has_image": output.image is not None,
            "is_system_skill": is_system_skill,
        },
    )
