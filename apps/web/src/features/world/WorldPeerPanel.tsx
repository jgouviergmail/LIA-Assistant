'use client';

import { useEffect, useState } from 'react';
import { Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { z } from '@/lib/zod';
import type { MailboxScope } from './message-protocol';

const pageSchema = z
  .object({
    peers: z
      .array(
        z
          .object({
            connection: z.uuid(),
            name: z.string().min(1).max(255),
            presence: z.enum(['online', 'home', 'away', 'offline']),
          })
          .strict()
      )
      .max(12),
    next_cursor: z.uuid().nullable(),
  })
  .strict();
type Page = z.infer<typeof pageSchema>;
const PRESENCE_COLOUR: Record<Page['peers'][number]['presence'], string> = {
  online: 'bg-emerald-500',
  home: 'bg-red-500',
  away: 'bg-orange-300',
  offline: 'bg-gray-400',
};
interface Result {
  pageKey: string;
  key: string;
  page: Page | null;
  failed: boolean;
}

/** Neutral authored vignette. No peer room, avatar URL or profile is fetched. */
function PeerVignette() {
  return (
    <svg viewBox="0 0 240 140" aria-hidden="true" className="h-28 w-full rounded-lg bg-[#e6e9df]">
      <path d="M25 85 120 35 216 85 120 135Z" fill="#c6b99f" />
      <path d="M25 85V25L120 0v35Z" fill="#dfd6c1" />
      <path d="m120 0 96 48v37l-96-50Z" fill="#c8cbb9" />
      <path d="m43 47 32-12v28L43 77Z" fill="#83b9bf" stroke="#f5eee1" strokeWidth="4" />
      <path d="m127 55 49 25-27 14-49-25Z" fill="#a38160" />
      <path d="M108 74v22m55-10v23" stroke="#71614c" strokeWidth="5" />
      <path d="m125 44 25 12v18l-25-12Z" fill="#37545a" />
      <path d="m129 50 17 8v9l-17-8Z" fill="#95c6cb" />
      <path d="m52 91 36-18 30 16-36 19Z" fill="#bd9e86" />
      <path d="M52 91v9l30 17v-9Z" fill="#927b68" />
      <path d="m57 88 31-15 24 13-30 15Z" fill="#8b9f88" />
      <path d="m61 87 13-6 12 6-13 7Z" fill="#f2e9d5" />
      <path d="m180 92 14-7 14 7-14 8Z" fill="#e6d9bf" />
      <path d="M182 93v13l12 7 12-7V93l-12 7Z" fill="#c4b899" />
      <path d="m181 82 13-7 14 7v10l-14 7-13-7Z" fill="#6c9175" />
    </svg>
  );
}

export function WorldPeerPanel({
  lng,
  ownerId,
  getScope,
  onCompose,
  presenceKey = '',
}: {
  lng: Language;
  ownerId: string;
  getScope(): MailboxScope | null;
  onCompose(draft: string): void;
  presenceKey?: string;
}) {
  const { t } = useTranslation(lng);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const { cursor, setCursor, setAttempt, current, pending } = usePeerPage(
    ownerId,
    getScope,
    presenceKey,
    isCurrent
  );
  const page = current?.page;
  return (
    <div className="h-full space-y-4 overflow-y-auto pb-3 pr-1" aria-busy={pending}>
      <p className="text-sm leading-relaxed text-foreground/80">{t('world.peers.privacy')}</p>
      {!current && <Skeleton className="h-44 w-full" />}
      {current?.failed && (
        <div role="status" className="space-y-3 text-sm">
          {t('world.functions.unavailable')}
          <Button
            className="min-h-11"
            variant="outline"
            onClick={() => setAttempt(value => value + 1)}
          >
            {t('common.retry')}
          </Button>
        </div>
      )}
      {page?.peers.length === 0 && (
        <p role="status" className="rounded-xl border border-dashed border-border p-5 text-sm">
          {t('world.peers.empty')}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {page?.peers.map(peer => (
          <article
            key={peer.connection}
            className="space-y-2 rounded-xl border border-border bg-card p-3"
          >
            <PeerVignette />
            <h3 className="break-words text-sm font-semibold" dir="auto">
              {peer.name}
            </h3>
            <p
              className="flex items-center gap-2 text-xs text-foreground/80"
              data-world-peer-presence={current?.failed ? 'unknown' : peer.presence}
            >
              <span
                aria-hidden="true"
                className={
                  'size-2.5 shrink-0 rounded-full border border-border ' +
                  (current?.failed ? 'bg-gray-400' : PRESENCE_COLOUR[peer.presence])
                }
              />
              {t('world.peers.' + (current?.failed ? 'presence_unavailable' : peer.presence))}
            </p>
            <Button
              className="min-h-11 w-full whitespace-normal"
              variant="outline"
              onClick={() => {
                if (isCurrent())
                  onCompose(
                    t('chat.message.share_peer_draft', { recipient: peer.name, content: '' })
                  );
              }}
            >
              <Send className="size-4" aria-hidden="true" />
              {t('world.peers.relay')}
            </Button>
          </article>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {cursor && (
          <Button variant="outline" className="min-h-11" onClick={() => setCursor(null)}>
            {t('world.peers.first')}
          </Button>
        )}
        {page?.next_cursor && (
          <Button
            variant="outline"
            className="min-h-11"
            onClick={() => setCursor(page.next_cursor)}
          >
            {t('world.peers.next')}
          </Button>
        )}
      </div>
    </div>
  );
}

/** Keep transport lifetime separate from the interactive directory presentation. */
function usePeerPage(
  ownerId: string,
  getScope: () => MailboxScope | null,
  presenceKey: string,
  isCurrent: () => boolean
) {
  const [cursor, setCursor] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const pageKey = `${ownerId}:${cursor ?? 'first'}`;
  const key = `${pageKey}:${attempt}:${presenceKey}`;
  const { mutate } = useApiMutation<MailboxScope & { after: string | null }, unknown>({
    method: 'POST',
    componentName: 'WorldPeers',
    retainResponse: false,
  });
  useEffect(() => {
    const abort = new AbortController();
    let active = true;
    let loading = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const failed = () => {
      if (active && isCurrent())
        setResult(previous => ({
          pageKey,
          key,
          page: previous?.pageKey === pageKey ? previous.page : null,
          failed: true,
        }));
    };
    const load = async () => {
      if (!active || loading || document.hidden) return;
      clearTimeout(timer);
      loading = true;
      try {
        const scope = getScope();
        if (!scope) throw new Error('world_scope_unavailable');
        const value = await mutate(
          '/world/messages/peers',
          { ...scope, after: cursor },
          { signal: abort.signal }
        );
        const parsed = pageSchema.safeParse(value);
        if (!parsed.success) failed();
        else if (active && isCurrent())
          setResult({
            pageKey,
            key,
            page: parsed.data,
            failed: false,
          });
      } catch {
        failed();
      } finally {
        loading = false;
        if (active && !document.hidden) timer = setTimeout(() => void load(), 10000);
      }
    };
    const visibility = () => {
      if (document.hidden) clearTimeout(timer);
      else void load();
    };
    document.addEventListener('visibilitychange', visibility);
    void load();
    return () => {
      active = false;
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', visibility);
      abort.abort();
    };
  }, [cursor, pageKey, key, mutate, getScope, isCurrent]);
  const current = result?.pageKey === pageKey ? result : null;
  return { cursor, setCursor, setAttempt, current, pending: !current || current.key !== key };
}
