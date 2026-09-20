import { describe, expect, it } from 'vitest';

import { describeVendorBill, formatUsd } from '../vendor-bill-view';
import type { LiveVendorBill } from '../types';

/** A translator that renders the key and its values, so the wording's PARTS are asserted. */
const t = ((key: string, values?: Record<string, unknown>) =>
  values ? `${key}(${Object.values(values).join(',')})` : key) as never;

const BILL: LiveVendorBill = {
  provider: 'elevenlabs',
  cost_usd: 0.1234,
  credits: 12,
  llm_credits: 4,
  call_credits: 8,
  platform_credits: 0,
  llm_model: 'gemini-3.6-flash',
  tts_model: 'eleven_v3_conversational',
  duration_seconds: 95,
};

describe('describeVendorBill', () => {
  it('the brand, the total in USD, the shares with their models, the duration', () => {
    const line = describeVendorBill(BILL, t, 'fr');
    expect(line).toContain('live.vendor_bill.total(ElevenLabs,0,1234 $)');
    expect(line).toContain('live.vendor_bill.shares(4,8,gemini-3.6-flash,eleven_v3_conversational)');
    expect(line).toContain('live.vendor_bill.duration(95)');
  });

  it('falls back to the credits, then to « unstated », and skips the shares it lacks', () => {
    const credits = describeVendorBill(
      { ...BILL, cost_usd: null, llm_credits: null, duration_seconds: null },
      t,
      'en'
    );
    expect(credits).toBe('live.vendor_bill.total(ElevenLabs,live.vendor_bill.credits(12))');
    const unstated = describeVendorBill({ ...BILL, cost_usd: null, credits: null }, t, 'en');
    expect(unstated).toContain('live.vendor_bill.unstated');
  });

  it('formats the total in the locale with four decimals', () => {
    expect(formatUsd(0.05, 'en')).toBe('0.0500 $');
    expect(formatUsd(1.5, 'fr')).toBe('1,5000 $');
  });
});
