'use client';

import { useCallback, type ReactNode } from 'react';
import {
  Bot,
  PanelTopClose,
  PanelTopOpen,
  ChartNoAxesCombined,
  CircleHelp,
  Focus,
  FlaskConical,
  Map as MapIcon,
  Minus,
  MousePointerClick,
  Plus,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { WorldMinimap } from './WorldMinimap';
import { WorldJoystick } from './WorldJoystick';
import type { Point } from './types';
import type { WorldRuntime } from './runtime';
import type { WorldSnapshot } from './types';
import { NEUTRAL_ATMOSPHERE, type Atmosphere } from './atmosphere';
import { WorldSkyBadge } from './WorldSkyBadge';
import { WorldActingStatus } from './WorldActingStatus';
import type { Season } from './season';

interface Props {
  season?: Season;
  conversationOpen?: boolean;
  widgets?: ReactNode;
  gestures?: ReactNode;
  expanded: boolean;
  onExpand(): void;
  joystick: boolean;
  lng: Language;
  snapshot: WorldSnapshot;
  metrics: boolean;
  command(action: (runtime: WorldRuntime) => void): void;
  onMetrics(): void;
  onHelp(): void;
  atmosphere?: Atmosphere;
  prototype?: boolean;
  nearbyLabel?: string;
}

export function WorldHud(props: Props) {
  const { lng, snapshot, command, metrics, onMetrics, onHelp } = props;
  const { t } = useTranslation(lng);
  const compact = useMediaQuery(
    '(max-width: 767px), (max-height: 520px) and (orientation: landscape)'
  );
  const ToggleIcon = props.expanded ? PanelTopClose : PanelTopOpen;
  return (
    <>
      <Button
        className="world-hud-toggle world-touch-button"
        variant="outline"
        size="icon"
        aria-label={t('world.controls')}
        aria-expanded={props.expanded}
        onClick={props.onExpand}
      >
        <ToggleIcon aria-hidden="true" className="size-5" />
      </Button>
      <div
        className="world-top"
        role="region"
        aria-label={t('world.controls')}
        tabIndex={compact ? 0 : undefined}
      >
        <div className="world-hud-left">
          <div className="world-heading border border-border bg-background/95 shadow-lg">
            <div className="flex items-center gap-2">
              <MapIcon className="size-5 shrink-0 text-primary" aria-hidden="true" />
              <p className="min-w-0 text-sm font-semibold">{t('world.title')}</p>
              {props.prototype !== false && (
                <Badge variant="default" className="ml-auto shrink-0">
                  <FlaskConical className="mr-1 size-3" aria-hidden="true" />
                  <span className="sr-only sm:not-sr-only">{t('world.prototype')}</span>
                </Badge>
              )}
            </div>
            <WorldSkyBadge
              lng={lng}
              atmosphere={props.atmosphere ?? NEUTRAL_ATMOSPHERE}
              season={props.season}
            />
            <WorldActingStatus lng={lng} state={snapshot.acting} hidden={props.conversationOpen} />
            <div className="world-place-controls flex items-center gap-1">
              <Button
                size="sm"
                variant="ghost"
                className="world-context-action min-h-11 min-w-11 flex-1 justify-start overflow-hidden px-1 text-xs"
                aria-label={t('world.interaction_action', {
                  activity: props.nearbyLabel ?? t('world.zones.' + snapshot.zone),
                })}
                onClick={() => command(runtime => runtime.interact())}
              >
                <MousePointerClick className="world-context-icon" aria-hidden="true" />
                <span className="world-context-label truncate">
                  {props.nearbyLabel ?? t('world.zones.' + snapshot.zone)}
                </span>
                <kbd className="world-shortcut">E</kbd>
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="world-touch-button"
                aria-label={t('world.metrics')}
                aria-expanded={metrics}
                onClick={onMetrics}
              >
                <ChartNoAxesCombined className="size-5" aria-hidden="true" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="world-touch-button"
                aria-label={t('world.help')}
                onClick={onHelp}
              >
                <CircleHelp className="size-5" aria-hidden="true" />
              </Button>
            </div>
          </div>
          {props.widgets}
          {compact && <WorldTools {...props} />}
        </div>
        <WorldMinimap
          snapshot={snapshot}
          label={t('world.minimap')}
          directoryLabel={t('world.explore_places')}
          placeLabel={id => t('world.zones.' + id)}
          onExplore={point => command(runtime => runtime.explore(point))}
          onRecenter={() => command(runtime => runtime.recenter())}
        />
      </div>
      {metrics && <WorldMetrics lng={lng} snapshot={snapshot} onClose={onMetrics} />}
      <WorldBottomControls {...props} compact={compact} />
    </>
  );
}

function WorldBottomControls(props: Props & { compact: boolean }) {
  const { lng, command, snapshot, compact } = props;
  const { t } = useTranslation(lng);
  const hold = useCallback(
    (source: string, point: Point) => command(runtime => runtime.input.hold(source, point)),
    [command]
  );
  const release = useCallback(
    (source: string) => command(runtime => runtime.input.release(source)),
    [command]
  );
  return (
    <div className="world-bottom">
      {props.joystick && (!compact || !props.expanded) && (
        <WorldJoystick label={t('world.joystick.move')} onHold={hold} onRelease={release} />
      )}
      {props.gestures}
      {compact && !props.expanded && snapshot.nearby && (
        <Button
          className="world-nearby-action"
          variant="outline"
          aria-label={t('world.interaction_action', {
            activity: props.nearbyLabel ?? t('world.zones.' + snapshot.zone),
          })}
          title={props.nearbyLabel ?? t('world.zones.' + snapshot.zone)}
          onClick={() => command(runtime => runtime.interact())}
        >
          <MousePointerClick className="size-4" aria-hidden="true" />
        </Button>
      )}
      {!compact && <WorldTools {...props} />}
    </div>
  );
}

function WorldMetrics({
  lng,
  snapshot,
  onClose,
}: {
  lng: Language;
  snapshot: WorldSnapshot;
  onClose(): void;
}) {
  const { t } = useTranslation(lng);
  const stat = (value: number) =>
    new Intl.NumberFormat(lng, { maximumFractionDigits: 1 }).format(value);
  return (
    <div className="world-metrics border border-border bg-background/95 shadow-lg">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold">{t('world.metrics')}</span>
        <Button
          variant="ghost"
          size="icon"
          className="world-touch-button"
          aria-label={t('world.close_metrics')}
          onClick={onClose}
        >
          <X className="size-4" aria-hidden="true" />
        </Button>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs tabular-nums">
        <dt>{t('world.fps')}</dt>
        <dd data-world-fps>{stat(snapshot.metrics.fps)}</dd>
        <dt>{t('world.frame')}</dt>
        <dd data-world-frame>{stat(snapshot.metrics.frameP95)} ms</dd>
        <dt>{t('world.render')}</dt>
        <dd data-world-render>{stat(snapshot.metrics.renderP95)} ms</dd>
        <dt>{t('world.textures')}</dt>
        <dd>{stat(snapshot.metrics.textureBytes / 1048576)} MiB</dd>
        <dt>{t('world.draws')}</dt>
        <dd>{snapshot.metrics.sprites}</dd>
      </dl>
      <p className="mt-2 max-w-56 text-xs text-muted-foreground">{t('world.measurement_hint')}</p>
    </div>
  );
}

function WorldTools({ lng, snapshot, command }: Props) {
  const { t } = useTranslation(lng);
  return (
    <div className="world-tools">
      <Button
        variant={snapshot.bipFollowing ? 'default' : 'outline'}
        className="world-tool-button shadow-md"
        aria-label={t('world.call_bip')}
        aria-pressed={snapshot.bipFollowing}
        onClick={() => command(runtime => runtime.callBip())}
      >
        <Bot className="size-5" aria-hidden="true" />
        <span className="hidden sm:inline">
          {t(snapshot.bipFollowing ? 'world.following_you' : 'world.follow_me')}
        </span>
      </Button>
      <Button
        variant="outline"
        size="icon"
        className="world-touch-button bg-background/95 shadow-md"
        aria-label={t('world.recenter')}
        aria-pressed={snapshot.following}
        title={snapshot.following ? t('world.follow') : t('world.free')}
        onClick={() => command(runtime => runtime.recenter())}
      >
        <Focus className="size-5" aria-hidden="true" />
      </Button>
      <div
        className="flex overflow-hidden rounded-xl border border-border bg-background/95 shadow-md"
        role="group"
        aria-label={t('world.zoom')}
      >
        <Button
          variant="ghost"
          size="icon"
          className="world-touch-button"
          aria-label={t('world.zoom_out')}
          onClick={() => command(runtime => runtime.zoom(1 / 1.2))}
        >
          <Minus className="size-5" aria-hidden="true" />
        </Button>
        <span
          className="flex min-w-11 items-center justify-center text-xs tabular-nums"
          data-world-zoom
        >
          {Math.round(snapshot.zoom * 100)}%
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="world-touch-button"
          aria-label={t('world.zoom_in')}
          onClick={() => command(runtime => runtime.zoom(1.2))}
        >
          <Plus className="size-5" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
