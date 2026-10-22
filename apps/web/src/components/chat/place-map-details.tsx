'use client';

import { forwardRef, useContext, type ComponentPropsWithoutRef } from 'react';
import {
  Car,
  Clock3,
  ExternalLink,
  Footprints,
  Globe,
  MapPin,
  Phone,
  RefreshCw,
  Route as RouteIcon,
  Star,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { AuthContext } from '@/lib/auth';
import type { PlacePositionData } from '@/lib/place-position-data';
import type { usePlaceRoute } from '@/hooks/usePlaceRoute';

type Place = PlacePositionData['places'][number];
type RouteState = ReturnType<typeof usePlaceRoute>['state'];
type Trip = NonNullable<RouteState['result']>;

export const PlaceMapTitle = forwardRef<
  HTMLHeadingElement,
  ComponentPropsWithoutRef<'h3'> & { place: Place }
>(function PlaceMapTitle({ place, className = '', ...props }, ref) {
  return (
    <h3 ref={ref} className={`lia-place-details__title ${className}`} {...props}>
      <MapPin size={19} className="text-primary" aria-hidden="true" />
      <span>{place.label}</span>
    </h3>
  );
});

function PlaceFacts({ place, showTitle }: { place: Place; showTitle: boolean }) {
  const { t, i18n } = useTranslation();
  const details = place.details;
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 });
  return (
    <header className="lia-place-details__heading">
      {showTitle && <PlaceMapTitle place={place} />}
      {details?.rating !== undefined && details.rating !== null && (
        <p className="lia-place-details__rating">
          <Star size={14} aria-hidden="true" />
          {t(
            details.reviews_count === null
              ? 'chat.position_map.rating'
              : 'chat.position_map.rating_reviews',
            {
              rating: number.format(details.rating),
              count: details.reviews_count ?? 0,
            }
          )}
        </p>
      )}
      {details?.address && <p className="lia-place-details__address">{details.address}</p>}
    </header>
  );
}

function PlaceLinks({ place }: { place: Place }) {
  const { t } = useTranslation();
  const details = place.details;
  return (
    <div className="lia-place-details__links">
      {details?.phone && (
        <a href={`tel:${details.phone.replace(/[^\d+]/g, '')}`}>
          <Phone size={14} aria-hidden="true" />
          {details.phone}
        </a>
      )}
      {details?.website && (
        <a href={details.website} target="_blank" rel="noopener noreferrer">
          <Globe size={14} aria-hidden="true" />
          {t('chat.position_map.website')}
        </a>
      )}
      <a
        href={place.url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={t('chat.position_map.open_place', { name: place.label })}
      >
        <ExternalLink size={14} aria-hidden="true" />
        {t('chat.position_map.maps')}
      </a>
    </div>
  );
}

function PlaceHours({ place }: { place: Place }) {
  const { t } = useTranslation();
  const hours = place.details?.opening_hours;
  if (!hours?.length) return null;
  return (
    <details className="lia-place-details__hours">
      <summary>
        <Clock3 size={14} aria-hidden="true" />
        {t('chat.position_map.hours')}
      </summary>
      <ul>
        {hours.map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>
    </details>
  );
}

function TripFacts({ trip }: { trip: Trip }) {
  const { t, i18n } = useTranslation();
  const timeZone = useContext(AuthContext)?.user?.timezone;
  const number = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 });
  const ModeIcon = trip.travel_mode === 'WALK' ? Footprints : Car;
  return (
    <>
      <div className="lia-place-details__journey">
        <span className="lia-place-details__mode">
          <ModeIcon size={22} aria-hidden="true" />
          {t(`chat.position_map.mode_${trip.travel_mode.toLowerCase()}`)}
        </span>
        <dl className="lia-place-details__metrics">
          <div>
            <dt>{t('chat.position_map.distance')}</dt>
            <dd>
              {number.format(trip.distance_meters / 1000)} <span>km</span>
            </dd>
          </div>
          <div>
            <dt>{t('chat.position_map.duration')}</dt>
            <dd>
              {number.format(trip.duration_seconds / 60)} <span>min</span>
            </dd>
          </div>
        </dl>
      </div>
      <p className="lia-place-details__origin">
        {t(`chat.position_map.route_from_${trip.origin_source}`)}
        {trip.origin_as_of && (
          <time dateTime={trip.origin_as_of}>
            {new Intl.DateTimeFormat(i18n.language, {
              dateStyle: 'short',
              timeStyle: 'short',
              timeZone,
            }).format(new Date(trip.origin_as_of))}
          </time>
        )}
      </p>
    </>
  );
}

function PlaceTrip({
  place,
  route,
  onRetry,
}: {
  place: Place;
  route: RouteState;
  onRetry(): void;
}) {
  const { t } = useTranslation();
  const result = route.ref === place.ref ? route.result : null;
  return (
    <section className="lia-place-details__route" aria-busy={route.status === 'loading'}>
      <div className="lia-place-details__route-heading">
        <h4>
          <RouteIcon size={16} className="text-primary" aria-hidden="true" />
          {t('chat.position_map.route_title')}
        </h4>
        <button
          type="button"
          className="lia-place-details__refresh"
          aria-label={t('chat.position_map.route_refresh')}
          title={t('chat.position_map.route_refresh')}
          aria-disabled={route.status === 'loading'}
          onClick={() => {
            if (route.status !== 'loading') onRetry();
          }}
        >
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      </div>
      <div role="status" aria-live="polite">
        {route.status === 'loading' && (
          <p className="lia-place-details__notice">{t('chat.position_map.route_loading')}</p>
        )}
        {result && <TripFacts trip={result} />}
      </div>
      {route.status === 'error' && (
        <p role="alert" className="lia-place-details__notice">
          {t(
            route.error === 'origin'
              ? 'chat.position_map.route_no_origin'
              : 'chat.position_map.route_error'
          )}
        </p>
      )}
    </section>
  );
}

export function PlaceMapDetails({
  place,
  route,
  onRetry,
  showTitle = true,
}: {
  place: Place;
  route: RouteState;
  onRetry(): void;
  showTitle?: boolean;
}) {
  return (
    <section className="lia-place-details" aria-label={place.label}>
      <PlaceFacts place={place} showTitle={showTitle} />
      <PlaceTrip place={place} route={route} onRetry={onRetry} />
      <PlaceLinks place={place} />
      <PlaceHours place={place} />
    </section>
  );
}
