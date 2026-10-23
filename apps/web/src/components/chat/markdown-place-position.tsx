'use client';

import {
  useContext,
  useCallback,
  useMemo,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
} from 'react';
import type { ExtraProps } from 'react-markdown';
import { useTranslation } from 'react-i18next';
import { ExternalLink, LocateFixed, MapPinned } from 'lucide-react';
import { AppConfigSeedContext, type AppConfig } from '@/hooks/useAppConfig';
import { usePaidMap } from '@/hooks/usePaidMap';
import { usePlaceRoute } from '@/hooks/usePlaceRoute';
import { AuthContext } from '@/lib/auth';
import { parsePlacePosition, type PlacePositionData } from '@/lib/place-position-data';
import { hasSearchMatch } from './markdown-search-matches';
import { PlaceMapPopup, type PlacePopup } from './place-map-popup';

type Props = ComponentPropsWithoutRef<'div'> & ExtraProps & { 'data-place-position'?: string };

export function MarkdownPlacePosition({
  node,
  children,
  'data-place-position': wire,
  ...props
}: Props) {
  const data = useMemo(() => parsePlacePosition(wire), [wire]);
  const owner = useContext(AuthContext)?.user?.id ?? null;
  return (
    <div {...props}>
      {data && !hasSearchMatch(node) ? (
        <PositionMap key={`${owner}:${wire}`} data={data} owner={owner}>
          {children}
        </PositionMap>
      ) : (
        children
      )}
    </div>
  );
}

function positionOffer(
  config: AppConfig | null,
  owner: string | null,
  data: PlacePositionData,
  language: string
) {
  const offer = config?.place_maps;
  if (!owner || !offer?.enabled || !data.places.some(place => place.position)) return null;
  const price = Number(offer.estimated_cost_eur);
  if (!Number.isFinite(price) || price <= 0) return null;
  return new Intl.NumberFormat(language, {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 5,
  }).format(price);
}

function PositionMap({
  data,
  owner,
  children,
}: {
  data: PlacePositionData;
  owner: string | null;
  children: React.ReactNode;
}) {
  const { t, i18n } = useTranslation();
  const config = useContext(AppConfigSeedContext);
  const [selected, setSelected] = useState(data.places.find(place => place.position)?.ref ?? '');
  const route = usePlaceRoute(owner);
  const [popup, setPopup] = useState<PlacePopup | null>(null);
  const popupRef = useRef<PlacePopup | null>(null);
  const choices = useRef(new Map<string, HTMLButtonElement>());
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
        data,
        grant.map_id ?? '',
        select,
        failure,
        construct
      ),
  });
  function select(ref: string) {
    setSelected(ref);
    controller.current?.select(ref);
    const place = data.places.find(item => item.ref === ref);
    if (!place?.position || !controller.current) return;
    const element =
      popupRef.current?.place.ref === ref
        ? popupRef.current.element
        : document.createElement('div');
    const header =
      popupRef.current?.place.ref === ref ? popupRef.current.header : document.createElement('div');
    header.className = 'lia-place-details__native-title';
    popupRef.current = { place, element, header, invoker: choices.current.get(ref) ?? null };
    setPopup(popupRef.current);
    calculate(place);
  }
  const dismissPopup = useCallback(() => {
    controller.current?.clearDetails();
    popupRef.current = null;
    setPopup(null);
  }, [controller]);
  function calculate(place: PlacePositionData['places'][number], force = false) {
    if (!place.position) return;
    controller.current?.setRoute(null);
    void route.load(place.ref, place.position, force).then(result => {
      if (result) controller.current?.setRoute(result.route);
    });
  }
  const cost = positionOffer(config, owner, data, i18n.language);
  // Drives the list's layout (lia-cards.css): beside the map on a wide card
  // while there IS a map, a centred line that wraps while there is none —
  // behind its offer, a side column would face nothing.
  const mapShown = state === 'loading' || state === 'ready';
  return (
    <div className="lia-route-map__content lia-place-position__content" data-map-shown={mapShown}>
      {popup && state === 'ready' && (
        <PlaceMapPopup
          popup={popup}
          controller={controller}
          route={route.state}
          onRetry={() => calculate(popup.place, true)}
          onDismiss={dismissPopup}
        />
      )}
      <PlaceMapStage state={state} cost={cost} element={element} detailsActive={popup !== null} />
      {cost && (
        <div className="lia-route-map__toolbar">
          <button
            type="button"
            className="lia-route-map__activate"
            aria-disabled={state === 'loading' || state === 'ready'}
            onClick={() => void activate()}
          >
            <MapPinned aria-hidden="true" size={18} />
            {state === 'loading' ? t('common.loading') : t('chat.position_map.activate')}
          </button>
          <span className="lia-route-map__cost">{t('chat.route_map.cost', { cost })}</span>
          {state === 'ready' && (
            <button
              type="button"
              className="lia-route-map__activate"
              aria-label={t('chat.position_map.recenter')}
              onClick={() => controller.current?.fit()}
            >
              <LocateFixed aria-hidden="true" size={18} />
            </button>
          )}
        </div>
      )}
      {state === 'error' && (
        <p role="alert" className="lia-route-map__notice">
          {t('chat.route_map.error')}
        </p>
      )}
      <ol className="lia-place-position__choices" aria-label={t('chat.position_map.choose')}>
        {data.places.map((place, index) => (
          <li key={place.ref}>
            <span aria-hidden="true" className="lia-place-position__number">
              {index + 1}
            </span>
            {state === 'ready' && place.position ? (
              <>
                <button
                  ref={element => {
                    if (element) choices.current.set(place.ref, element);
                    else choices.current.delete(place.ref);
                  }}
                  type="button"
                  aria-pressed={selected === place.ref}
                  onClick={() => {
                    select(place.ref);
                  }}
                >
                  {place.label}
                </button>
                <a
                  href={place.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={t('chat.position_map.open_place', { name: place.label })}
                >
                  <ExternalLink size={16} aria-hidden="true" />
                </a>
              </>
            ) : (
              <a href={place.url} target="_blank" rel="noopener noreferrer">
                {place.label}
              </a>
            )}
          </li>
        ))}
      </ol>
      {data.unlocated_count > 0 && (
        <p className="lia-route-map__notice">
          {t('chat.position_map.unlocated', { count: data.unlocated_count })}
        </p>
      )}
      {data.omitted_count > 0 && (
        <>
          <p className="lia-route-map__notice">
            {t('chat.position_map.omitted', { count: data.omitted_count })}
          </p>
          <details>
            <summary>{t('chat.position_map.all_places')}</summary>
            {children}
          </details>
        </>
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

function PlaceMapStage({
  state,
  cost,
  element,
  detailsActive,
}: {
  state: ReturnType<typeof usePaidMap>['state'];
  cost: string | null;
  element: React.Ref<HTMLDivElement>;
  detailsActive: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="lia-route-map__stage lia-place-position__stage"
      data-available={Boolean(cost) || state === 'ready'}
      data-details-active={detailsActive}
      hidden={Boolean(cost) && state !== 'loading' && state !== 'ready'}
    >
      <div
        ref={element}
        className="lia-route-map__canvas"
        role="region"
        aria-label={t('chat.position_map.map')}
        aria-hidden={state !== 'ready'}
        data-active={state === 'ready'}
      />
      {state !== 'ready' && (
        <div className="lia-place-position__preview">
          <MapPinned aria-hidden="true" size={32} />
          <p>{t(cost ? 'chat.position_map.preview' : 'chat.position_map.unavailable')}</p>
        </div>
      )}
    </div>
  );
}
