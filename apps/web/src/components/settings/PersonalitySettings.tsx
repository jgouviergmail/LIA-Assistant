'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { Palette, RefreshCw, Sparkles } from 'lucide-react';
import { AnimatedEmoji } from '@/components/ui/animated-emoji';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { usePersonality } from '@/hooks/usePersonality';
import { usePersonalityStore } from '@/stores/personalityStore';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import type { PersonalityListItem } from '@/types/personality';
import type { BaseSettingsProps } from '@/types/settings';

interface StyleChoiceProps {
  personality: PersonalityListItem;
  selected: boolean;
  blocked: boolean;
  pending: boolean;
  selectedLabel: string;
  defaultLabel: string;
  onSelect: (id: string) => void;
}

function StyleChoice({
  personality,
  selected,
  blocked,
  pending,
  selectedLabel,
  defaultLabel,
  onSelect,
}: StyleChoiceProps) {
  const id = useId();
  const [active, setActive] = useState(false);
  return (
    <button
      type="button"
      aria-label={personality.title}
      aria-describedby={id}
      aria-pressed={selected}
      aria-disabled={blocked}
      aria-busy={pending || undefined}
      onClick={() => {
        if (!blocked) onSelect(personality.id);
      }}
      onMouseEnter={() => setActive(true)}
      onMouseLeave={() => setActive(false)}
      onFocus={() => setActive(true)}
      onBlur={() => setActive(false)}
      className={cn(
        'flex min-h-20 min-w-0 items-start gap-3 rounded-xl border border-border/60 p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background aria-disabled:cursor-wait motion-reduce:transition-none sm:p-4',
        selected ? 'bg-primary/10' : 'bg-background hover:bg-primary/5'
      )}
    >
      <span
        aria-hidden="true"
        className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/8 text-primary"
      >
        {pending ? (
          <LoadingSpinner />
        ) : (
          <AnimatedEmoji
            glyph={personality.emoji}
            animate={active}
            imgClassName="size-7 object-contain"
            spanClassName="text-2xl"
          />
        )}
      </span>
      <span className="min-w-0 flex-1 space-y-2 [overflow-wrap:anywhere]">
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-sm font-semibold leading-relaxed">{personality.title}</span>
          {selected && <Badge size="sm">{selectedLabel}</Badge>}
        </span>
        <span
          id={id}
          className="block whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground"
        >
          {personality.description}
        </span>
        {personality.is_default && (
          <span className="block text-xs text-muted-foreground">{defaultLabel}</span>
        )}
      </span>
    </button>
  );
}

function selectedStyle(
  personalities: readonly PersonalityListItem[],
  current: PersonalityListItem | null,
  currentId: string | null
) {
  return (
    current ??
    personalities.find(personality => personality.id === currentId) ??
    (currentId === null ? personalities.find(personality => personality.is_default) : undefined)
  );
}

/** Every save and focus recovery belongs to one account lifetime. */
export function PersonalitySettings(props: BaseSettingsProps) {
  const { user } = useAuth();
  return <PersonalitySettingsContent key={user?.id ?? 'anonymous'} {...props} ownerId={user?.id} />;
}

function PersonalitySettingsContent({
  lng,
  ownerId,
}: BaseSettingsProps & { ownerId: string | undefined }) {
  const { t } = useTranslation(lng);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const {
    personalities,
    currentPersonality,
    currentPersonalityId,
    loading,
    refreshing,
    updating,
    error,
    updatePersonality,
    refetch,
  } = usePersonality();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const saveLock = useRef(false);
  const retryLock = useRef(false);
  const recovering = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  const selected = selectedStyle(personalities, currentPersonality, currentPersonalityId);

  useEffect(() => {
    if (recovering.current && !retrying && !loading) {
      recovering.current = false;
      if (!error) heading.current?.focus();
    }
  }, [error, retrying, loading]);

  const selectStyle = async (id: string) => {
    if (!isCurrent() || saveLock.current || updating || selected?.id === id) return;
    saveLock.current = true;
    setPendingId(id);
    try {
      await updatePersonality(id);
      if (!isCurrent()) return;
      const saved = usePersonalityStore.getState();
      if (saved.currentPersonality?.id !== id && saved.currentPersonalityId !== id) return;
      toast.success(t('personality.update_success'));
    } catch {
      if (isCurrent()) toast.error(t('personality.update_error'));
    } finally {
      saveLock.current = false;
      if (isCurrent()) setPendingId(null);
    }
  };

  const retry = async () => {
    if (!isCurrent() || retryLock.current) return;
    retryLock.current = true;
    recovering.current = true;
    setRetrying(true);
    try {
      await refetch();
    } finally {
      retryLock.current = false;
      if (isCurrent()) setRetrying(false);
    }
  };

  return (
    <SettingsSection
      value="personality"
      title={t('personality.settings.title')}
      description={t('personality.settings.description')}
      icon={Sparkles}
    >
      {loading ? (
        <Skeleton label={t('common.loading')} className="h-64 w-full rounded-xl" />
      ) : (
        <div
          aria-busy={refreshing}
          data-selected={!!selected}
          className={cn(
            'group/personality grid min-w-0 items-start gap-x-5 gap-y-3',
            selected && 'xl:grid-cols-[minmax(12rem,0.65fr)_minmax(0,1.8fr)]'
          )}
        >
          {selected && (
            <section
              aria-label={t('personality.current')}
              className="flex min-w-0 items-start gap-4 rounded-2xl border border-primary/15 bg-primary/5 p-4 xl:col-start-1 xl:row-start-2 xl:flex-col xl:p-5"
            >
              <span
                aria-hidden="true"
                className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-primary/10 xl:size-20"
              >
                <AnimatedEmoji
                  glyph={selected.emoji}
                  animate
                  imgClassName="size-10 object-contain xl:size-14"
                  spanClassName="text-4xl xl:text-5xl"
                />
              </span>
              <div className="min-w-0 space-y-3 [overflow-wrap:anywhere]">
                <p className="text-xs font-medium text-primary">{t('personality.current')}</p>
                <h4 className="text-xl font-semibold leading-tight tracking-tight xl:text-2xl">
                  {selected.title}
                </h4>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                  {selected.description}
                </p>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {t('personality.selection_hint')}
                </p>
              </div>
            </section>
          )}
          <section aria-labelledby={headingId} className="contents">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2 xl:group-data-[selected=true]/personality:col-start-2 xl:group-data-[selected=true]/personality:row-start-1">
              <h4
                ref={heading}
                id={headingId}
                tabIndex={-1}
                className="flex min-w-0 items-center gap-2 rounded text-base font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Palette className="size-4 shrink-0 text-primary" aria-hidden="true" />
                {t('personality.catalogue_title')}
              </h4>
              <p className="text-xs tabular-nums text-muted-foreground">
                {t('personality.catalogue_count', { count: personalities.length })}
              </p>
            </div>
            <div className={cn('min-w-0 space-y-3', selected && 'xl:col-start-2 xl:row-start-2')}>
              {error && (
                <p
                  role="alert"
                  className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm leading-relaxed"
                >
                  {t(
                    personalities.length ? 'personality.retained_error' : 'personality.load_error'
                  )}
                </p>
              )}
              {(error || retrying || personalities.length === 0) && (
                <Button
                  variant="outline"
                  onClick={() => void retry()}
                  aria-disabled={retrying}
                  aria-busy={retrying || undefined}
                  className="min-h-11 max-w-full whitespace-normal text-left"
                >
                  <RefreshCw
                    className={retrying ? 'animate-spin motion-reduce:animate-none' : undefined}
                    aria-hidden="true"
                  />
                  {t('common.retry')}
                </Button>
              )}
              {personalities.length > 0 ? (
                <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
                  {personalities.map(personality => (
                    <StyleChoice
                      key={personality.id}
                      personality={personality}
                      selected={selected?.id === personality.id}
                      blocked={updating || pendingId !== null || !ownerId}
                      pending={pendingId === personality.id}
                      selectedLabel={t('personality.selected')}
                      defaultLabel={t('personality.instance_default')}
                      onSelect={id => void selectStyle(id)}
                    />
                  ))}
                </div>
              ) : (
                !error &&
                !retrying && (
                  <EmptyState
                    icon={Sparkles}
                    reason="no-data"
                    description={t('personality.empty')}
                  />
                )
              )}
            </div>
          </section>
        </div>
      )}
    </SettingsSection>
  );
}
