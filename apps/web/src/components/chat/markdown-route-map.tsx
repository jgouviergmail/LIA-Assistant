'use client';

import { useContext, useEffect, useMemo, useState, type ComponentPropsWithoutRef } from 'react';
import type { ExtraProps } from 'react-markdown';
import { useTranslation } from 'react-i18next';
import { MapPinned, LocateFixed } from 'lucide-react';
import { AppConfigSeedContext, type AppConfig } from '@/hooks/useAppConfig';
import { usePaidMap } from '@/hooks/usePaidMap';
import { AuthContext } from '@/lib/auth';
import { parseRouteMap, type MapRoute, type RouteMapData } from '@/lib/route-map-data';
import { loadRouteMaps, mountRouteMap } from '@/lib/google-route-map';
import { hasSearchMatch } from './markdown-search-matches';

type Props = ComponentPropsWithoutRef<'div'> & ExtraProps & { 'data-route-map'?: string };

/** A changed archived source owns a new controller; late promises cannot attach to it. */
export function MarkdownRouteMap({ node, children, 'data-route-map': wire, ...props }: Props) {
  const data = useMemo(() => parseRouteMap(wire), [wire]);
  const owner = useContext(AuthContext)?.user?.id ?? 'anonymous';
  return (
    <div {...props}>
      {data && !hasSearchMatch(node) ? (
        <RouteMap key={`${owner}:${wire}`} data={data}>
          {children}
        </RouteMap>
      ) : (
        children
      )}
    </div>
  );
}

function routeFacts(route: MapRoute, language: string) {
  const format = new Intl.NumberFormat(language, { maximumFractionDigits: 1 });
  return [
    route.distance_meters === null ? null : `${format.format(route.distance_meters / 1000)} km`,
    route.duration_seconds === null ? null : `${format.format(route.duration_seconds / 60)} min`,
  ]
    .filter(Boolean)
    .join(' · ');
}

function mapOffer(config: AppConfig | null, language: string): string | null {
  if (!config?.route_maps?.enabled || !config.features.interactive_route_maps_enabled) return null;
  const price = Number(config.route_maps.estimated_cost_eur);
  if (!Number.isFinite(price) || price <= 0) return null;
  return new Intl.NumberFormat(language, {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 5,
  }).format(price);
}

function RouteMap({ data, children }: { data: RouteMapData; children: React.ReactNode }) {
  const { t, i18n } = useTranslation();
  // The authenticated layout owns the config read; a family of cards adds none.
  const config = useContext(AppConfigSeedContext);
  const [selected, setSelected] = useState(data.primary_id);
  const { state, reportFailed, element, controller, activate, retryReport } = usePaidMap({
    prepare: grant => loadRouteMaps(grant.api_key),
    mount: (maps, element, _grant, failure, construct) =>
      mountRouteMap(maps, element, data, select, failure, construct),
  });
  function select(id: string) {
    setSelected(id);
    controller.current?.select(id);
  }
  useEffect(() => {
    controller.current?.select(selected);
  }, [controller, selected, state]);
  const cost = mapOffer(config, i18n.language);
  return (
    <div className="lia-route-map__content">
      <div className="lia-route-map__stage">
        <div
          className="lia-route-map__canvas"
          ref={element}
          role="region"
          aria-label={t('chat.route_map.map')}
          aria-hidden={state !== 'ready'}
          data-active={state === 'ready'}
        />
        {state !== 'ready' && children}
      </div>
      {cost && (
        <div className="lia-route-map__toolbar">
          <button
            type="button"
            className="lia-route-map__activate"
            aria-disabled={state === 'loading' || state === 'ready'}
            onClick={() => void activate()}
          >
            <MapPinned aria-hidden="true" size={18} />
            {state === 'loading' ? t('common.loading') : t('chat.route_map.activate')}
          </button>
          <span className="lia-route-map__cost">{t('chat.route_map.cost', { cost })}</span>
        </div>
      )}
      {state === 'error' && (
        <p role="alert" className="lia-route-map__notice">
          {t('chat.route_map.error')}
        </p>
      )}
      {state === 'ready' && (
        <RouteMapChoices
          data={data}
          selected={selected}
          onSelect={select}
          onFit={() => controller.current?.fit()}
        />
      )}
      {data.omitted_count > 0 && (
        <p className="lia-route-map__notice">
          {t('chat.route_map.omitted', { count: data.omitted_count })}
        </p>
      )}
      {reportFailed && (
        <p role="alert" className="lia-route-map__notice">
          {t('chat.route_map.report_error')}{' '}
          <button type="button" onClick={retryReport}>
            {t('common.retry')}
          </button>
        </p>
      )}
    </div>
  );
}

function RouteMapChoices({
  data,
  selected,
  onSelect,
  onFit,
}: {
  data: RouteMapData;
  selected: string;
  onSelect: (id: string) => void;
  onFit: () => void;
}) {
  const { t, i18n } = useTranslation();
  const name = (route: MapRoute) => {
    if (route.id === data.primary_id) return t('chat.route_map.primary');
    const index = Number(route.id.split('-')[1]);
    const principal = Number(data.primary_id.split('-')[1]);
    return t('chat.route_map.alternative', { number: index > principal ? index : index + 1 });
  };
  const chosen = data.routes.find(route => route.id === selected) ?? data.routes[0];
  return (
    <>
      <div className="lia-route-map__choices" role="group" aria-label={t('chat.route_map.choose')}>
        {data.routes.map(route => (
          <button
            type="button"
            key={route.id}
            aria-pressed={selected === route.id}
            onClick={() => onSelect(route.id)}
          >
            <span>{name(route)}</span>
            <span className="lia-route-map__facts">{routeFacts(route, i18n.language)}</span>
          </button>
        ))}
        <button type="button" aria-label={t('chat.route_map.recenter')} onClick={onFit}>
          <LocateFixed aria-hidden="true" size={18} />
        </button>
      </div>
      <p className="lia-route-map__notice" role="status">
        {name(chosen)} · {routeFacts(chosen, i18n.language)}
      </p>
      {selected !== data.primary_id && (
        <p className="lia-route-map__notice">{t('chat.route_map.primary_details')}</p>
      )}
    </>
  );
}
