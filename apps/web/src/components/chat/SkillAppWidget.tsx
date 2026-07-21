'use client';

/**
 * SkillAppWidget — Interactive widget for skill rich outputs (frames + images).
 *
 * Mounted by `MarkdownContent` when it detects a
 * `<div class="lia-skill-app" data-registry-id="...">` sentinel in the chat.
 * Looks up the SKILL_APP payload in the registry and renders one or both of:
 *   - An image (`<img>` + lightbox) when `payload.image_url` is present
 *   - An iframe (srcDoc or src) when `payload.html_content` or `frame_url`
 *     is present
 *
 * Order: image is rendered BEFORE the frame, so frames (typically larger and
 * more interactive) appear below images in the response. This matches the
 * expected reading order (visual artifact first, interactive widget last).
 *
 * Security:
 * - Base sandbox: `allow-scripts allow-popups`. Parent LIA cookies/storage
 *   stay unreachable regardless of iframe source — the parent is always
 *   cross-origin to the iframe, so SOP protects it even if the iframe runs
 *   under its real origin.
 * - `allow-same-origin` is added ONLY for `frame_url` coming from a trusted
 *   `is_system_skill`. This lets the embedded page (e.g. Google Maps) talk
 *   to its own backend over XHR/fetch with credentials — required for
 *   tiles/data to load. Granting it does NOT give the iframe access to
 *   parent data, because the parent origin differs.
 * - User-skill `html_content` keeps the strict sandbox AND receives a CSP
 *   meta tag injected backend-side (blocks outbound fetch, nested iframes).
 * - User-owned `frame_url` (if any) also keeps the strict sandbox — we do
 *   not extend trust to arbitrary URLs emitted by user skills.
 *
 * Failure states (2026-07): an external embed the engine will refuse is never
 * rendered — `canEmbedOpaqueCrossOriginFrame()` answers before render, and the
 * user gets an actionable link instead of a dead rectangle. Frames that pass
 * the probe but never load are caught by `useFrameLoadWatchdog`, which also
 * emits the one log line that makes a remote report diagnosable.
 */

import { lazy, Suspense, useCallback, useRef, useState } from 'react';
import { useRegistryItem } from '@/lib/registry-context';
import { useSkillAppBridge } from '@/hooks/useSkillAppBridge';
import { useFrameLoadWatchdog } from '@/hooks/useFrameLoadWatchdog';
import { canEmbedOpaqueCrossOriginFrame, isCrossOriginUrl } from '@/lib/frame-embedding';
import { useTranslation } from 'react-i18next';
import type { SkillAppRegistryPayload } from '@/types/skill-apps';

const ImageLightbox = lazy(() =>
  import('@/components/ui/image-lightbox').then(m => ({ default: m.ImageLightbox }))
);

interface SkillAppWidgetProps {
  registryId: string;
}

export function SkillAppWidget({ registryId }: SkillAppWidgetProps) {
  const item = useRegistryItem(registryId);
  const { t } = useTranslation();

  if (!item || item.type !== 'SKILL_APP') {
    return (
      <div className="lia-skill-app__placeholder">
        <span className="text-sm text-muted-foreground">
          {t('skill_apps.error', { defaultValue: 'Skill widget unavailable' })}
        </span>
      </div>
    );
  }

  const payload = item.payload as unknown as SkillAppRegistryPayload;

  const hasImage = Boolean(payload.image_url);
  const hasFrame = Boolean(payload.html_content || payload.frame_url);

  return (
    <div className="lia-skill-app-widget">
      <div className="lia-skill-app-widget__header">
        <span className="lia-badge lia-badge--accent">{payload.title || payload.skill_name}</span>
        {payload.frame_url ? (
          <span className="lia-skill-app-widget__external-badge" title={payload.frame_url}>
            {t('skill_apps.external_frame', { defaultValue: 'External' })}
          </span>
        ) : null}
      </div>

      {hasImage ? <SkillImageCard url={payload.image_url!} alt={payload.image_alt || ''} /> : null}

      {hasFrame ? <SkillFrameCard payload={payload} /> : null}
    </div>
  );
}

function SkillImageCard({ url, alt }: { url: string; alt: string }) {
  const [isLightboxOpen, setLightboxOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="lia-skill-app-widget__image-button"
        onClick={() => setLightboxOpen(true)}
        aria-label={alt || 'Open image'}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={url} alt={alt} className="lia-skill-app-widget__image" loading="lazy" />
      </button>
      {isLightboxOpen ? (
        <Suspense fallback={null}>
          <ImageLightbox
            src={url}
            alt={alt}
            isOpen={isLightboxOpen}
            onClose={() => setLightboxOpen(false)}
          />
        </Suspense>
      ) : null}
    </>
  );
}

/**
 * Actionable stand-in for a frame that cannot render.
 *
 * Two callers: an embed the engine will refuse (probe), and one that never
 * loaded (watchdog). Both give the user the same two ways out — open the
 * content in a real tab, or try again — instead of a blank rectangle.
 */
function SkillFrameFallback({
  reason,
  url,
  onRetry,
}: {
  reason: 'unsupported' | 'timeout';
  /**
   * User-facing URL: `link_url` when the skill provides one, else
   * `frame_url`. Embed-only endpoints (Google Maps) refuse to render
   * top-level, which is exactly why `link_url` exists — never hand the
   * user a link that answers "must be used in an iframe".
   */
  url?: string | null;
  onRetry?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="lia-skill-app-widget__fallback" role="status">
      <p className="lia-skill-app-widget__fallback-text">
        {reason === 'unsupported'
          ? t('skill_apps.frame_unsupported')
          : t('skill_apps.frame_timeout')}
      </p>
      <div className="lia-skill-app-widget__fallback-actions">
        {url ? (
          <a
            className="lia-skill-app-widget__fallback-link"
            href={url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('skill_apps.frame_open_external')}
          </a>
        ) : null}
        {onRetry ? (
          <button type="button" className="lia-skill-app-widget__fallback-retry" onClick={onRetry}>
            {t('skill_apps.frame_retry')}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function SkillFrameCard({ payload }: { payload: SkillAppRegistryPayload }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  // Bumping this remounts the iframe (key) and re-arms the watchdog.
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt(n => n + 1), []);
  // The bridge only listens to event.origin === 'null' (srcDoc iframes).
  // External URL iframes are isolated by SOP — the bridge is a no-op for them.
  useSkillAppBridge(iframeRef, payload);

  const aspect = payload.aspect_ratio && payload.aspect_ratio > 0 ? payload.aspect_ratio : 1.333;
  const title = payload.title || payload.skill_name;
  const watchdogStatus = useFrameLoadWatchdog(iframeRef, {
    kind: 'skill',
    label: payload.skill_name,
    attempt,
  });

  // Trusted external embeds (system-skill frame_url) need `allow-same-origin`
  // so the embedded page can load its own XHR/tile data under its real origin.
  // The parent LIA is still cross-origin to the iframe, so SOP protects it.
  // It is ALSO what decides whether `credentialless` is applied below, hence
  // the viability check that follows.
  const isTrustedExternalFrame = Boolean(payload.frame_url) && payload.is_system_skill === true;

  // Refuse to render an embed that would be rejected: under COEP the frame
  // comes back blank, and on Chromium even the watchdog cannot see it (it
  // fires `load` on its error document). Capability alone is not the question —
  // an untrusted frame gets no `credentialless` attribute and is refused on
  // Chromium too. See lib/frame-embedding.ts.
  const isDoomedExternalFrame =
    Boolean(payload.frame_url) &&
    isCrossOriginUrl(payload.frame_url!) &&
    !canEmbedOpaqueCrossOriginFrame({ credentiallessApplied: isTrustedExternalFrame });
  if (isDoomedExternalFrame) {
    return <SkillFrameFallback reason="unsupported" url={payload.link_url ?? payload.frame_url} />;
  }
  const sandbox = isTrustedExternalFrame
    ? 'allow-scripts allow-popups allow-same-origin'
    : 'allow-scripts allow-popups';
  const commonProps = {
    className: 'lia-skill-app-widget__iframe',
    title: `Skill: ${title}`,
    sandbox,
    // background: transparent so the parent (LIA) page shows through the
    // iframe when the skill's own <body> is transparent. Without this the
    // browser default (white) leaks through in dark mode.
    style: { aspectRatio: String(aspect), background: 'transparent' },
  } as const;

  // `credentialless` opts the iframe out of the page's
  // Cross-Origin-Embedder-Policy, letting a cross-origin embed that returns no
  // CORP header load anyway. Kept unconditionally for trusted system-skill
  // URLs: it is what makes the embed work on Chromium under
  // `COEP_MODE=require-corp`, and it is inert everywhere else (engines that do
  // not implement it ignore the attribute — which is precisely why the probe
  // above exists). React doesn't type it yet — spread via a loose record.
  const extraFrameAttrs: Record<string, string> = isTrustedExternalFrame
    ? { credentialless: '' }
    : {};

  // A frame that never fired `load` is dead and will not recover on its own —
  // WebKit cancels a COEP-refused navigation without any event.
  if (watchdogStatus === 'timeout') {
    return (
      <SkillFrameFallback
        reason="timeout"
        url={payload.link_url ?? payload.frame_url}
        onRetry={retry}
      />
    );
  }

  if (payload.html_content) {
    return <iframe key={attempt} ref={iframeRef} srcDoc={payload.html_content} {...commonProps} />;
  }
  if (payload.frame_url) {
    return (
      <iframe
        key={attempt}
        ref={iframeRef}
        src={payload.frame_url}
        {...commonProps}
        {...extraFrameAttrs}
      />
    );
  }
  return null;
}
