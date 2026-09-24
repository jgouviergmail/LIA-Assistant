/**
 * The exchange rhythm a person chooses for LIA (ADR-311).
 *
 * Mirrors the backend vocabulary (`ExchangeRhythm`, apps/api/src/core/exchange_rhythm.py),
 * and a backend contract test reads this list so the two cannot drift. The API
 * publishes the EFFECTIVE rhythm on the profile — the person's choice, else the
 * instance default — so one of the two is always selected.
 */
export const EXCHANGE_RHYTHMS = ['frequent', 'occasional'] as const;

export type ExchangeRhythm = (typeof EXCHANGE_RHYTHMS)[number];
