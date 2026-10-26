'use client';

import { useState } from 'react';
import { ArrowDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { UsageLine } from '@/components/ui/usage-line';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorldPublicMessage } from './public-message-protocol';
import type { WorldMessage } from './message-protocol';
import { useMessageLogScroll } from './useMessageLogScroll';
import type { MessageScrollStore } from './message-scroll-store';

export function WorldMessageList({
  lng,
  publicMode = false,
  messages,
  tokensVisible,
  canTranslate,
  onTranslate,
  scrollStore,
}: {
  lng: Language;
  messages: (WorldMessage | WorldPublicMessage)[];
  publicMode?: boolean;
  tokensVisible: boolean;
  canTranslate: boolean;
  onTranslate(id: string): void;
  scrollStore?: MessageScrollStore;
}) {
  const { t } = useTranslation(lng);
  const { scroller, anchored, remember, latest } = useMessageLogScroll(messages, scrollStore);
  return (
    <div className="relative flex min-h-0 flex-col">
      <div
        ref={scroller}
        role="log"
        aria-label={t(publicMode ? 'world.public.caption' : 'world.messages.title')}
        aria-live="polite"
        aria-relevant="additions text"
        tabIndex={0}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-xl border border-border bg-background/50 p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onScroll={event => remember(event.currentTarget)}
      >
        {messages.length === 0 && (
          <p className="p-5 text-center text-sm text-foreground/80">
            {t(publicMode ? 'world.public.empty' : 'world.messages.empty')}
          </p>
        )}
        {messages.map(message => (
          <MessageBubble
            key={message.id}
            lng={lng}
            message={message}
            tokensVisible={tokensVisible}
            canTranslate={canTranslate}
            onTranslate={onTranslate}
          />
        ))}
      </div>
      {!anchored && messages.length > 0 && (
        <Button
          type="button"
          size="sm"
          className="absolute bottom-3 right-3 min-h-11 max-w-[calc(100%-1.5rem)] whitespace-normal shadow-lg"
          onClick={latest}
        >
          <ArrowDown className="size-4 shrink-0" aria-hidden="true" />
          {t('world.messages.latest')}
        </Button>
      )}
    </div>
  );
}

function MessageBubble({
  lng,
  message,
  tokensVisible,
  canTranslate,
  onTranslate,
}: {
  lng: Language;
  message: WorldMessage | WorldPublicMessage;
  tokensVisible: boolean;
  canTranslate: boolean;
  onTranslate(id: string): void;
}) {
  const { t } = useTranslation(lng);
  const [original, setOriginal] = useState(false);
  const showOriginal = !message.outgoing && message.status !== 'original';
  const translatable =
    'recipient_alias' in message &&
    !message.outgoing &&
    ['failed', 'uncertain', 'unavailable'].includes(message.status);
  const receipt = tokensVisible ? message.receipt : null;
  return (
    <article
      data-world-message={message.id}
      className={
        'max-w-[94%] rounded-xl border border-border p-3 ' +
        (message.outgoing ? 'ml-auto bg-accent/65' : 'bg-card')
      }
    >
      <MessageAddress lng={lng} message={message} />
      {message.text !== null && (
        <p
          dir="auto"
          className="whitespace-pre-wrap break-words text-sm leading-relaxed [overflow-wrap:anywhere]"
        >
          {message.text}
        </p>
      )}
      {message.status !== 'original' && (
        <p role="status" className="mt-1 text-xs text-foreground/80">
          {t('world.messages.' + message.status)}
        </p>
      )}
      {showOriginal && (
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="min-h-11 whitespace-normal"
            aria-expanded={original}
            onClick={() => setOriginal(value => !value)}
          >
            {t('world.messages.' + (original ? 'hide_original' : 'show_original'))}
          </Button>
          {original && (
            <div className="mt-1 rounded-lg border border-border bg-muted/40 p-2">
              <p className="mb-1 text-xs font-semibold">{t('world.messages.original')}</p>
              <p
                dir="auto"
                className="whitespace-pre-wrap break-words text-sm [overflow-wrap:anywhere]"
              >
                {message.original}
              </p>
            </div>
          )}
        </>
      )}
      <PublicTranslationHint lng={lng} message={message} />
      {translatable && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="min-h-11 max-w-full whitespace-normal"
          disabled={!canTranslate}
          onClick={() => onTranslate(message.id)}
        >
          {t('world.messages.translate')}
        </Button>
      )}
      {receipt && (
        <UsageLine
          figures={[
            ['🟠', t('world.messages.tokens_in'), receipt.tokens_in],
            ['🟢', t('world.messages.tokens_out'), receipt.tokens_out],
          ]}
          cost={receipt.cost_eur}
          decimals={6}
          locale={lng}
          unknownCostLabel={t('world.messages.cost_unknown')}
        />
      )}
    </article>
  );
}

function MessageAddress({
  lng,
  message,
}: {
  lng: Language;
  message: WorldMessage | WorldPublicMessage;
}) {
  const { t } = useTranslation(lng);
  return (
    <p className="mb-1 text-xs font-semibold text-foreground/80">
      <span dir="auto">{message.sender_alias}</span>
      <span aria-hidden="true"> → </span>
      <span dir="auto">
        {'recipient_alias' in message ? message.recipient_alias : t('world.public.title')}
      </span>
    </p>
  );
}
function PublicTranslationHint({
  lng,
  message,
}: {
  lng: Language;
  message: WorldMessage | WorldPublicMessage;
}) {
  const { t } = useTranslation(lng);
  return (
    <>
      {!('recipient_alias' in message) &&
        !message.outgoing &&
        ['failed', 'uncertain', 'unavailable'].includes(message.status) && (
          <p className="mt-2 text-xs text-muted-foreground">{t('world.public.failed_hint')}</p>
        )}
    </>
  );
}
