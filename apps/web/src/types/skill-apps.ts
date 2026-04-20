/**
 * Skill Apps Types — Rich skill outputs (frames + images) rendered in the chat.
 *
 * Mirrors the MCP Apps pattern (evolution F2.5) but is dedicated to skill
 * scripts emitting the `SkillScriptOutput` contract via stdout JSON.
 *
 * The backend builds a `SKILL_APP` RegistryItem with this payload and emits a
 * sentinel `<div class="lia-skill-app" data-registry-id="...">` in the chat
 * markdown. The frontend mounts `SkillAppWidget` in place of the sentinel and
 * renders the image and/or frame based on the payload.
 *
 * Security:
 * - User-skill frame.html is served with a CSP meta injected backend-side
 *   (blocks outbound fetch, nested iframes).
 * - The iframe sandbox (see SkillAppWidget) is strict by default; it grants
 *   `allow-same-origin` only for trusted system-skill `frame_url` embeds
 *   that need credentialed requests to their own origin (e.g. Google Maps).
 *   The parent LIA remains cross-origin to the iframe, so parent
 *   cookies/storage stay unreachable regardless.
 */

/** Payload stored in the Data Registry for SKILL_APP items. */
export interface SkillAppRegistryPayload {
  /** Emitting skill name (used in header badge). */
  skill_name: string;

  /** Inline HTML (rendered via iframe `srcDoc`). Exclusive with `frame_url`. */
  html_content?: string | null;

  /** External frame URL (rendered via iframe `src`). Exclusive with `html_content`. */
  frame_url?: string | null;

  /** Image URL (data: or https://). */
  image_url?: string | null;

  /** Image alt text (required when image_url is present). */
  image_alt?: string | null;

  /** Frame header title (falls back to skill_name). */
  title?: string | null;

  /** Width/height ratio for responsive rendering. Default 1.333 (4:3). */
  aspect_ratio?: number | null;

  /** Short textual summary — used for voice/accessibility fallback. */
  text_summary: string;

  /** True for admin-curated system skills, false for user-owned skills. */
  is_system_skill: boolean;
}

/** JSON-RPC 2.0 message shape used by the skill-app postMessage bridge. */
export interface SkillAppBridgeMessage {
  jsonrpc: '2.0';
  id?: string | number;
  method?: string;
  params?: Record<string, unknown>;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}
