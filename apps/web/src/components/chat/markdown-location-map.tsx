'use client';

import {
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
} from 'react';
import type { ExtraProps } from 'react-markdown';
import { useTranslation } from 'react-i18next';
import { ExternalLink, LocateFixed, MapPinned } from '@/lib/icons';
import { AppConfigSeedContext } from '@/hooks/useAppConfig';
import { usePaidMap } from '@/hooks/usePaidMap';
import { AuthContext } from '@/lib/auth';
import {
  locationMapPresentation,
  parseLocationMap,
  type LocationMapData,
} from '@/lib/location-map-data';
import { placeMapOffer } from '@/lib/place-map-offer';
import { hasSearchMatch } from './markdown-search-matches';
import { MapDetailsPopup, type MapPopupTarget } from './map-details-popup';

type Props = ComponentPropsWithoutRef<'div'> & ExtraProps & { 'data-location-map'?: string };

/** A location enhancement owns only received address facts and one admitted map. */
export function MarkdownLocationMap({
  node,
  children,
  'data-location-map': wire,
  ...props
}: Props) {
  const data = useMemo(() => parseLocationMap(wire), [wire]);
  const owner = useContext(AuthContext)?.user?.id ?? null;
  return (
    <div {...props}>
      {data && !hasSearchMatch(node) ? (
        <LocationMap key={`${owner}:${wire}`} data={data} owner={owner}>
          {children}
        </LocationMap>
      ) : (
        children
      )}
    </div>
  );
}

function LocationMap({
  data,
  owner,
  children,
}: {
  data: LocationMapData;
  owner: string | null;
  children: React.ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const config = useContext(AppConfigSeedContext);
  const projection = useMemo(() => locationMapPresentation(data), [data]);
  const point = projection.places[0];
  const choice = useRef<HTMLButtonElement>(null);
  const [popup, setPopup] = useState<MapPopupTarget | null>(null);
  const { state, reportFailed, element, controller, activate, retryReport } = usePaidMap({
    purpose: 'places',
    prepare: async grant => {
      const native = await import('@/lib/google-place-map');
      return { native, ...(await native.loadPlaceMaps(grant.api_key)) };
    },
    mount: (prepared, element, grant, failure, construct) =>
      prepared.native.mountPlaceMap(
        prepared.maps,
        prepared.marker,
        element,
        projection,
        grant.map_id ?? '',
        select,
        failure,
        construct
      ),
  });
  function select(ref: string) {
    if (ref !== point.ref || !controller.current) return;
    controller.current.select(ref);
    const header = document.createElement('div');
    header.className = 'lia-place-details__native-title';
    setPopup({
      ref,
      label: data.label,
      element: document.createElement('div'),
      header,
      invoker: choice.current,
    });
  }
  const dismiss = useCallback(() => {
    setPopup(null);
  }, []);
  const cost = placeMapOffer(config, owner, true, i18n.language);
  return (
    <div className="lia-route-map__content lia-location-map__content">
      {popup && state === 'ready' && (
        <MapDetailsPopup popup={popup} controller={controller} onDismiss={dismiss}>
          <section className="lia-place-details" aria-label={data.label}>
            {data.address && <p className="lia-place-details__address">{data.address}</p>}
            <p>
              {data.position.lat.toFixed(6)}, {data.position.lng.toFixed(6)}
            </p>
            <div className="lia-place-details__links">
              <a href={point.url} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={14} aria-hidden="true" />
                {t('chat.position_map.maps')}
              </a>
            </div>
          </section>
        </MapDetailsPopup>
      )}
      <div
        className="lia-route-map__stage"
        data-map-shown={state === 'loading' || state === 'ready'}
      >
        <div
          ref={element}
          className="lia-route-map__canvas"
          role="region"
          aria-label={t('chat.location_map.map')}
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
            {state === 'loading' ? t('common.loading') : t('chat.location_map.activate')}
          </button>
          <span className="lia-route-map__cost">{t('chat.route_map.cost', { cost })}</span>
        </div>
      )}
      {state === 'ready' && (
        <div
          className="lia-route-map__choices"
          role="group"
          aria-label={t('chat.location_map.details')}
        >
          <button ref={choice} type="button" onClick={() => select(point.ref)}>
            {data.label}
          </button>
          <button
            type="button"
            aria-label={t('chat.position_map.recenter')}
            onClick={() => controller.current?.fit()}
          >
            <LocateFixed aria-hidden="true" size={18} />
          </button>
        </div>
      )}
      {state === 'error' && (
        <p role="alert" className="lia-route-map__notice">
          {t('chat.route_map.error')}
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
