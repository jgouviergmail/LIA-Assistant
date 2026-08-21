/**
 * Every platform-key connector the backend ships must be administrable.
 *
 * `google_weather` and `google_environment` (lot E) reached production while
 * the admin section still listed an older set: an operator could not switch
 * them off, and the capability map said "available" for something the panel
 * could not reach. This guard fails on the next such omission instead of
 * waiting for someone to notice in prod.
 *
 * The expected list is deliberately hand-written: it is the CONTRACT the
 * frontend commits to, so adding a backend connector means a deliberate,
 * reviewed edit here — never a silent pass.
 */

import { describe, it, expect } from 'vitest';

import { CONNECTOR_LABELS, CONNECTOR_CATEGORIES } from '@/constants/connectors';
import { ADMIN_CONNECTOR_CATEGORIES } from '../AdminConnectorsSection';

/** Connectors the backend exposes through /connectors/admin/global-config. */
const BACKEND_ADMINISTRABLE = [
  'google_gmail',
  'google_calendar',
  'google_drive',
  'google_contacts',
  'google_tasks',
  'google_places',
  'google_routes',
  'google_weather',
  'google_environment',
  'apple_email',
  'apple_calendar',
  'apple_contacts',
  'microsoft_outlook',
  'microsoft_calendar',
  'microsoft_contacts',
  'microsoft_tasks',
  'openweathermap',
  'wikipedia',
  'perplexity',
  'brave_search',
  'browser',
  'philips_hue',
  'elevenlabs_telephony',
] as const;

describe('Admin connectors — coverage of the backend surface', () => {
  const administrable = new Set(Object.values(ADMIN_CONNECTOR_CATEGORIES).flat());

  it('lists every administrable backend connector', () => {
    const missing = BACKEND_ADMINISTRABLE.filter(type => !administrable.has(type));
    expect(missing).toEqual([]);
  });

  it('lists no connector the backend does not ship', () => {
    const unknown = [...administrable].filter(
      type => !BACKEND_ADMINISTRABLE.includes(type as (typeof BACKEND_ADMINISTRABLE)[number])
    );
    expect(unknown).toEqual([]);
  });

  it('gives every administrable connector a display label', () => {
    const unlabelled = BACKEND_ADMINISTRABLE.filter(
      type => !(type in CONNECTOR_LABELS) || !CONNECTOR_LABELS[type]
    );
    expect(unlabelled).toEqual([]);
  });

  it('places every administrable connector in a shared category', () => {
    const categorised = new Set(Object.values(CONNECTOR_CATEGORIES).flat());
    const orphans = BACKEND_ADMINISTRABLE.filter(type => !categorised.has(type));
    expect(orphans).toEqual([]);
  });
});
