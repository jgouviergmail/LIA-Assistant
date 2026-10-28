'use client';
import { useCallback, useMemo, useState } from 'react';
import { BookOpen, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { observeGame, type GameObservation, type WorldGameClient } from './game-client';
import { useWorldArcade } from './useWorldArcade';
import { CABINET_GAMES, type CabinetId } from './game-catalogue';
import type { GameAction, GameMove } from './game-protocol';
import { WorldArcadeContent, type ArcadeContext } from './WorldArcadeContent';

export function WorldArcadePanel({
  lng,
  ownerId,
  cabinet,
  client,
  onClose,
}: {
  lng: Language;
  ownerId: string;
  cabinet: CabinetId;
  client: WorldGameClient;
  onClose(): void;
}) {
  const { t } = useTranslation(lng);
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const state = useWorldArcade(client);
  const [changed, setChanged] = useState(false);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const observed = useMemo(() => observeGame(state, cabinet), [state, cabinet]);
  const perform = useCallback(
    (action: GameAction, move?: GameMove) => {
      if (!isCurrent() || client.getSnapshot().pending) return;
      if (!client.canRequest(observed, action, move)) {
        // An aria-disabled choice is inert; only a game that moved past what was shown is reported.
        if (!sameObservation(observed, observeGame(client.getSnapshot(), cabinet)))
          setChanged(true);
        return;
      }
      const sent = client.request(observed, action, move);
      setChanged(!sent);
      if (sent) setLastAction(client.getSnapshot().pending?.intent.action_id ?? null);
    },
    [client, observed, isCurrent, cabinet]
  );
  function leave() {
    if (!isCurrent()) return;
    client.close(cabinet);
    onClose();
  }
  function resynchronize() {
    if (!isCurrent()) return;
    client.resynchronize();
    setLastAction(null);
    setChanged(false);
  }
  if (!isCurrent()) return null;
  if (!client.available()) return <p role="status">{t('world.arcade.unavailable')}</p>;
  const interaction = state.game ?? state.request;
  if (interaction && interaction.cabinet !== cabinet)
    return (
      <div className="space-y-3">
        <p role="status">{t('world.arcade.elsewhere')}</p>
        <Button
          className="min-h-11"
          variant="outline"
          onClick={() => {
            if (isCurrent()) client.close(interaction.cabinet);
          }}
        >
          {t('world.arcade.leave_other_cabinet')}
        </Button>
      </div>
    );
  const context: ArcadeContext = {
    lng,
    cabinet,
    client,
    state,
    observed,
    isCurrent,
    perform,
    leave,
  };
  return (
    <section
      aria-label={t(`world.arcade.games.${CABINET_GAMES[cabinet]}.title`)}
      className="h-full space-y-4 overflow-y-auto overscroll-contain pb-2 pr-1"
    >
      <ArcadeToolbar context={context} />
      <ArcadeFeedback
        context={context}
        changed={changed}
        lastAction={lastAction}
        resynchronize={resynchronize}
      />
      <WorldArcadeContent {...context} />
      <ArcadeRules lng={lng} cabinet={cabinet} />
    </section>
  );
}
function sameObservation(shown: GameObservation | null, current: GameObservation | null): boolean {
  return (
    shown?.generation === current?.generation &&
    shown?.round_id === current?.round_id &&
    shown?.revision === current?.revision
  );
}
function ArcadeToolbar({ context }: { context: ArcadeContext }) {
  const { t } = useTranslation(context.lng);
  if (!context.state.game) return null;
  return (
    <div className="flex justify-end">
      <Button variant="outline" className="min-h-11" onClick={context.leave}>
        <LogOut className="size-4" aria-hidden="true" />
        {t('world.arcade.leave')}
      </Button>
    </div>
  );
}
function ArcadeFeedback({
  context,
  changed,
  lastAction,
  resynchronize,
}: {
  context: ArcadeContext;
  changed: boolean;
  lastAction: string | null;
  resynchronize(): void;
}) {
  const { t } = useTranslation(context.lng);
  const { state } = context;
  if (state.pending?.uncertain)
    return (
      <div className="space-y-2 rounded-lg border p-3">
        <p role="status">{t('world.arcade.uncertain')}</p>
        <Button className="min-h-11" variant="outline" onClick={resynchronize}>
          {t('world.arcade.resynchronize')}
        </Button>
      </div>
    );
  if (changed)
    return (
      <p role="status" className="text-sm">
        {t('world.arcade.changed')}
      </p>
    );
  const outcome = state.outcome;
  if (outcome && outcome.action_id === lastAction && outcome.result !== 'accepted')
    return (
      <p role="status" className="text-sm">
        {t('world.arcade.feedback.' + outcome.result)}
      </p>
    );
  return state.pending ? (
    <p role="status" className="text-sm">
      {t('world.arcade.pending')}
    </p>
  ) : null;
}
function ArcadeRules({ lng, cabinet }: { lng: Language; cabinet: CabinetId }) {
  const { t } = useTranslation(lng);
  return (
    <details className="rounded-lg border p-3">
      <summary className="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-medium">
        <BookOpen className="size-4 text-primary" aria-hidden="true" />
        {t('world.arcade.rules')}
      </summary>
      <p className="mt-2 text-sm text-muted-foreground">
        {t(`world.arcade.games.${CABINET_GAMES[cabinet]}.rules`)}
      </p>
      <p className="mt-2 text-xs text-muted-foreground">{t('world.arcade.keyboard')}</p>
    </details>
  );
}
