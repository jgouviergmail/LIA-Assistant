'use client';

/**
 * PageAppWidget — a page the model wrote, shown live in the chat (ADR-370).
 *
 * Mounted by `MarkdownContent` in place of `<div class="lia-page-app">`. The page
 * runs in a sandboxed `srcDoc` frame and nowhere else; the file sits on the
 * document card below the answer, so this widget has no download of its own.
 *
 * Security: `allow-scripts` runs the page's own code with an opaque origin, so
 * cookies, storage and the parent are out of reach. `allow-forms` lets a submit
 * handler fire (without it Chromium and Firefox never call it), and the page's
 * policy still refuses any submission. Nothing else is granted, and the bridge
 * (`usePageFrameBridge`) only listens.
 *
 * A page read back from history waits for a click: a loop that never ends blocks
 * the host's thread on Chromium, Firefox and WebKit alike (measured 2026-11-04),
 * and a page that started by itself would make its conversation impossible to
 * open again.
 */

import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { AppWindow, Code2, Play, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useFrameLoadWatchdog } from '@/hooks/useFrameLoadWatchdog';
import { usePageFrameBridge } from '@/hooks/usePageFrameBridge';
import { useRegistryItem } from '@/lib/registry-context';
import type { PageAppPayload } from '@/types/page-apps';

// Prism stays out of the bundle until someone opens the code.
const CodeBlock = lazy(() =>
  import('@/components/chat/CodeBlock').then(m => ({ default: m.CodeBlock }))
);

/** The whole grant. Pinned by a test: every added flag undoes a measurement. */
const PAGE_FRAME_SANDBOX = 'allow-scripts allow-forms';

interface PageFrameProps {
  html: string;
  title: string;
  hidden: boolean;
  takesFocus: boolean;
  onFault: (message: string) => void;
}

/** The running page. Its own component so a restart is a remount, state included. */
function PageFrame({ html, title, hidden, takesFocus, onFault }: PageFrameProps) {
  const { t } = useTranslation();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const status = useFrameLoadWatchdog(iframeRef, { kind: 'page', label: 'interactive_page' });
  usePageFrameBridge(iframeRef, onFault);

  useEffect(() => {
    if (!takesFocus) return;
    const frame = iframeRef.current;
    // `focus()` alone centres the frame and hides the top of a page taller than the
    // chat. A click is the person asking to look at it: its top comes first.
    frame?.closest('section')?.scrollIntoView?.({ block: 'start' });
    frame?.focus({ preventScroll: true });
  }, [takesFocus]);

  // The element alone leaves Chromium's Tab outside: the keyboard enters a frame of
  // another process through its window, once its document exists (measured
  // 2026-11-05, three engines).
  const handOverKeyboard = () => {
    if (takesFocus) iframeRef.current?.contentWindow?.focus();
  };

  if (status === 'timeout') {
    return (
      <p className="lia-page-app-widget__notice" role="status">
        {t('page_apps.timeout')}
      </p>
    );
  }
  return (
    <iframe
      ref={iframeRef}
      className="lia-page-app-widget__iframe"
      title={title}
      sandbox={PAGE_FRAME_SANDBOX}
      srcDoc={html}
      hidden={hidden}
      onLoad={handOverKeyboard}
    />
  );
}

interface HeaderActionProps {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}

/** An icon action of the header, its name given to the tooltip and to assistive tech. */
function HeaderAction({ label, onClick, children }: HeaderActionProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button type="button" variant="ghost" size="icon" aria-label={label} onClick={onClick}>
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function PageApp({ payload, restored }: { payload: PageAppPayload; restored: boolean }) {
  const { t } = useTranslation();
  const [showsCode, setShowsCode] = useState(payload.initial_view === 'code');
  const [started, setStarted] = useState(!restored && payload.initial_view === 'page');
  // A page started by a click takes the focus; one that started alone never
  // pulls it away from what the person is typing.
  const [startedByClick, setStartedByClick] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [fault, setFault] = useState<string | null>(null);

  const title = payload.title || t('page_apps.untitled');
  const frameTitle = t('page_apps.frame_title', { title });
  // The first failure explains the next ones.
  const onFault = useCallback((message: string) => setFault(first => first ?? message), []);
  const toggleLabel = showsCode ? t('page_apps.show_page') : t('page_apps.show_code');

  const start = () => {
    setStarted(true);
    setStartedByClick(true);
  };
  const restart = () => {
    setFault(null);
    setAttempt(value => value + 1);
  };

  return (
    <section className="lia-page-app-widget" aria-label={frameTitle}>
      <header className="lia-page-app-widget__header">
        <AppWindow className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <span className="lia-page-app-widget__title">{title}</span>
        <span className="lia-page-app-widget__origin">{t('page_apps.generated_by')}</span>
        <span className="lia-page-app-widget__actions">
          {started && !showsCode ? (
            <HeaderAction label={t('page_apps.restart')} onClick={restart}>
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
            </HeaderAction>
          ) : null}
          <HeaderAction label={toggleLabel} onClick={() => setShowsCode(value => !value)}>
            <Code2 className="h-4 w-4" aria-hidden="true" />
          </HeaderAction>
        </span>
      </header>

      {started ? (
        <PageFrame
          key={attempt}
          html={payload.html_content}
          title={frameTitle}
          hidden={showsCode}
          takesFocus={startedByClick}
          onFault={onFault}
        />
      ) : null}

      {!started && !showsCode ? (
        <div className="lia-page-app-widget__poster">
          <p>{t('page_apps.start_hint')}</p>
          <Button type="button" onClick={start}>
            <Play className="h-4 w-4" aria-hidden="true" />
            {t('page_apps.start')}
          </Button>
        </div>
      ) : null}

      {showsCode ? (
        <Suspense fallback={null}>
          <CodeBlock language="html">{payload.html_content.slice(payload.source_offset)}</CodeBlock>
        </Suspense>
      ) : null}

      {fault ? (
        <p className="lia-page-app-widget__notice" role="status">
          {t('page_apps.failed')} {fault}
        </p>
      ) : null}
    </section>
  );
}

/** A payload read back from history is read, never assumed. */
function isPagePayload(
  payload: Record<string, unknown>
): payload is Record<string, unknown> & PageAppPayload {
  return (
    typeof payload.title === 'string' &&
    typeof payload.html_content === 'string' &&
    typeof payload.source_offset === 'number'
  );
}

/** Resolve the sentinel's registry id to its page. */
export function PageAppWidget({ registryId }: { registryId: string }) {
  const item = useRegistryItem(registryId);
  const { t } = useTranslation();
  if (item?.type !== 'PAGE_APP' || !isPagePayload(item.payload)) {
    return (
      <p className="lia-page-app-widget__notice" role="status">
        {t('page_apps.unavailable')}
      </p>
    );
  }
  return <PageApp payload={item.payload} restored={item.restored === true} />;
}
