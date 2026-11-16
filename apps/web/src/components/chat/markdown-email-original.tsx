'use client';

/**
 * A received message in the chat, opened as the Tools show it (owner, 2026-11-14).
 *
 * The card carries the message's text and the marker naming it (`lia-email-original`). Once the
 * person opens the card's details, and only under the card's own signed source with the Tools
 * offered, the message's original layout is read and drawn in the Tools' isolated frame
 * (`OriginalLayout`): its remote images on a click, its own images read apart, its colours turned
 * down in a dark theme. The text stays a click away; it stays alone while the layout is on its
 * way, where there is none, where it could not be read (said), and where it cannot be asked for: a
 * card with no source proof, or the Tools switched off.
 */
import {
  useContext,
  useEffect,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
  type ReactNode,
  type RefObject,
} from 'react';
import type { ExtraProps } from 'react-markdown';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { OriginalLayout } from '@/components/workbench/mail/OriginalLayout';
import { useInlineImages } from '@/components/workbench/mail/useMailScreen';
import { AppConfigSeedContext } from '@/hooks/useAppConfig';
import { useWorkbenchItem } from '@/hooks/useWorkbenchItem';
import { homeLanguage } from '@/lib/briefing-tools';
import { cn } from '@/lib/utils';
import { workbenchAvailable } from '@/lib/workbench/availability';
import type { MailHtml } from '@/lib/workbench/types';

import { useCardReadSource } from './markdown-card-target';

const HTML_PATH = '/workbench/mail/message/html';
/** A card is narrower and shorter than the Tools' reader. */
const CARD_FRAME = 'h-[min(60dvh,32rem)] min-h-48';
/** Read a little before it scrolls in, as the chat's other previews are. */
const AHEAD = '100px';

type MarkdownDivProps = ComponentPropsWithoutRef<'div'> & ExtraProps;

/** @returns Whether the element has been in view once; nothing is watched while not `watching`. */
function useSeenOnce(element: RefObject<HTMLElement | null>, watching: boolean): boolean {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (!watching || seen || !element.current) return;
    const observer = new IntersectionObserver(
      entries => {
        if (entries.some(entry => entry.isIntersecting)) {
          observer.disconnect();
          setSeen(true);
        }
      },
      { rootMargin: AHEAD }
    );
    observer.observe(element.current);
    return () => observer.disconnect();
  }, [element, watching, seen]);
  return seen;
}

export function MarkdownEmailOriginal({
  className,
  children,
  node: _node,
  ...props
}: MarkdownDivProps) {
  const messageId = (props as Record<string, unknown>)['data-message-id'];
  const id = typeof messageId === 'string' && messageId ? messageId : null;
  const source = useCardReadSource('email');
  // The Tools' door, read where the reader is mounted: switched off, the card asks nothing.
  const offered = workbenchAvailable(useContext(AppConfigSeedContext));
  const holder = useRef<HTMLDivElement>(null);
  const askable = offered && id !== null && source !== null;
  const seen = useSeenOnce(holder, askable);
  // Nothing that needs the session runs before a read is both allowed and wanted: a card is also
  // drawn where nobody is signed in, and a card never opened asks nothing.
  if (!askable || !seen) {
    return (
      <div ref={holder} className={className}>
        {children}
      </div>
    );
  }
  return (
    <OriginalReader id={id} source={source} className={className}>
      {children}
    </OriginalReader>
  );
}

interface OriginalReaderProps {
  id: string;
  source: string;
  className: string | undefined;
  /** The message's text, as the card carries it. */
  children: ReactNode;
}

function OriginalReader({ id, source, className, children }: OriginalReaderProps) {
  const { t, i18n } = useTranslation();
  const lng = homeLanguage(i18n?.language);
  const original = useWorkbenchItem<MailHtml>(HTML_PATH, { id }, source);
  const html = original.item?.html ?? null;
  const inline = useInlineImages(id, html, source);
  const [asText, setAsText] = useState(false);
  // Above the swap to the text, so a look at the text does not take back what was asked for.
  const [images, setImages] = useState(false);

  const swap = (label: string, next: boolean, place?: string) => (
    <Button
      variant="link"
      size="sm"
      className={cn('h-auto p-0 text-xs', place)}
      onClick={() => setAsText(next)}
    >
      {label}
    </Button>
  );

  if (original.item && html !== null && !asText) {
    return (
      <div className={className}>
        <OriginalLayout
          lng={lng}
          original={{ ...original.item, html }}
          inline={inline}
          images={images}
          onShowImages={() => setImages(true)}
          lead={swap(
            t('workbench.mail.show_text'),
            true,
            'col-start-1 justify-self-start text-left'
          )}
          frameClassName={CARD_FRAME}
        />
      </div>
    );
  }
  return (
    <div className={className}>
      {children}
      {html !== null && swap(t('workbench.mail.show_original'), false)}
      {original.error !== null && (
        <p className="text-xs text-muted-foreground">{t('workbench.mail.html_failed')}</p>
      )}
    </div>
  );
}
