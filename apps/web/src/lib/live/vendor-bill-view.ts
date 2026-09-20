/**
 * What the toast SAYS of the vendor's bill (owner request 2026-09-20): the
 * figures the provider itself stated for the session that just ended, read
 * on the person's key and shown once — recorded nowhere, since the platform
 * re-bills nothing of a session on their own key. Pure, so the wording is
 * tested without React.
 */
import type { TFunction } from 'i18next';

import { liveProviderLabel } from '@/lib/live/providers';

import type { LiveVendorBill } from './types';

/** The vendor's total, in the locale's digits: « 0,1234 $ ». */
export function formatUsd(amount: number, locale: string): string {
  return `${new Intl.NumberFormat(locale, { minimumFractionDigits: 4, maximumFractionDigits: 4 }).format(amount)} $`;
}

/**
 * One line: the brand, the total (USD, else credits), the shares when the
 * vendor stated them, the models it charged for, its own duration.
 */
export function describeVendorBill(bill: LiveVendorBill, t: TFunction, locale: string): string {
  const brand = liveProviderLabel(bill.provider);
  const total =
    bill.cost_usd !== null
      ? formatUsd(bill.cost_usd, locale)
      : bill.credits !== null
        ? t('live.vendor_bill.credits', { count: bill.credits })
        : t('live.vendor_bill.unstated');
  const parts: string[] = [t('live.vendor_bill.total', { brand, total })];
  if (bill.llm_credits !== null && bill.call_credits !== null) {
    parts.push(
      t('live.vendor_bill.shares', {
        llm: bill.llm_credits,
        call: bill.call_credits,
        llmModel: bill.llm_model ?? '?',
        voice: bill.tts_model ?? '?',
      })
    );
  }
  if (bill.duration_seconds !== null) {
    parts.push(t('live.vendor_bill.duration', { seconds: bill.duration_seconds }));
  }
  return parts.join(' · ');
}
