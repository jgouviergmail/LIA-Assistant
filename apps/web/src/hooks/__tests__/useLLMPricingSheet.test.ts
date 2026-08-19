/**
 * The hook owns the two-phase contract of the workbook import.
 *
 * Previewing and applying are the SAME upload sent twice: the second call
 * carries the fingerprint of the plan the administrator actually looked at, so
 * a catalogue that moved in between is refused rather than silently written.
 * Everything below pins that, plus the failure paths — a network error must
 * surface, never resolve into a fake empty report.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useLLMPricingSheet } from '../useLLMPricingSheet';

const PLAN = {
  plan_fingerprint: 'abc123',
  counts: { update: 1, unchanged: 3 },
  changes: [
    {
      model_name: 'gpt-4.1-mini',
      action: 'update',
      fields: [{ field: 'input_unit_price', before: '0.4', after: '0.5' }],
      slots_before: 0,
      slots_after: 0,
      row_number: 3,
    },
  ],
  issues: [],
  is_applicable: true,
  pricing_changes: ['gpt-4.1-mini'],
};

const REPORT = { applied: false, plan: PLAN, created: [], updated: [], deactivated: [], reactivated: [], unchanged: 3 };

function file(name = 'catalogue.xlsx'): File {
  return new File(['x'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

function mockFetch(response: unknown, ok = true, status = 200) {
  const spy = vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => response,
  });
  vi.stubGlobal('fetch', spy);
  return spy;
}

describe('useLLMPricingSheet', () => {
  beforeEach(() => {
    vi.stubGlobal('open', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe('export', () => {
    it('opens the export endpoint so the browser handles the download', () => {
      const { result } = renderHook(() => useLLMPricingSheet());

      act(() => result.current.exportSheet());

      expect(window.open).toHaveBeenCalledWith(
        expect.stringContaining('/admin/llm/pricing/sheet/export.xlsx'),
        expect.anything()
      );
    });
  });

  describe('preview', () => {
    it('uploads the file and returns the plan', async () => {
      const spy = mockFetch(REPORT);
      const { result } = renderHook(() => useLLMPricingSheet());

      let report;
      await act(async () => {
        report = await result.current.preview(file());
      });

      expect(report).toEqual(REPORT);
      expect(spy).toHaveBeenCalledTimes(1);
    });

    it('asks for a dry run so nothing is written', async () => {
      const spy = mockFetch(REPORT);
      const { result } = renderHook(() => useLLMPricingSheet());

      await act(async () => {
        await result.current.preview(file());
      });

      expect(String(spy.mock.calls[0][0])).toContain('dry_run=true');
    });

    it('sends the file as multipart form data', async () => {
      const spy = mockFetch(REPORT);
      const { result } = renderHook(() => useLLMPricingSheet());

      await act(async () => {
        await result.current.preview(file());
      });

      expect(spy.mock.calls[0][1].body).toBeInstanceOf(FormData);
      expect(spy.mock.calls[0][1].credentials).toBe('include');
    });

    it('reports it is working while the upload is in flight', async () => {
      let release: (value: unknown) => void = () => {};
      vi.stubGlobal(
        'fetch',
        vi.fn().mockReturnValue(new Promise(resolve => (release = resolve)))
      );
      const { result } = renderHook(() => useLLMPricingSheet());

      act(() => {
        void result.current.preview(file());
      });
      await waitFor(() => expect(result.current.busy).toBe(true));

      await act(async () => {
        release({ ok: true, status: 200, json: async () => REPORT });
      });
      await waitFor(() => expect(result.current.busy).toBe(false));
    });

    it('surfaces a server refusal instead of resolving empty', async () => {
      mockFetch({ detail: 'workbook exceeds the limit' }, false, 400);
      const { result } = renderHook(() => useLLMPricingSheet());

      await expect(result.current.preview(file())).rejects.toThrow(/limit/);
    });

    it('surfaces a network failure', async () => {
      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
      const { result } = renderHook(() => useLLMPricingSheet());

      await expect(result.current.preview(file())).rejects.toThrow(/offline/);
    });

    it('stops reporting busy after a failure', async () => {
      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
      const { result } = renderHook(() => useLLMPricingSheet());

      await act(async () => {
        await result.current.preview(file()).catch(() => undefined);
      });

      expect(result.current.busy).toBe(false);
    });
  });

  describe('apply', () => {
    it('carries the fingerprint of the reviewed plan', async () => {
      const spy = mockFetch({ ...REPORT, applied: true });
      const { result } = renderHook(() => useLLMPricingSheet());

      await act(async () => {
        await result.current.apply(file(), 'abc123');
      });

      const url = String(spy.mock.calls[0][0]);
      expect(url).toContain('dry_run=false');
      expect(url).toContain('plan_fingerprint=abc123');
    });

    it('re-sends the same file rather than trusting server-side state', async () => {
      const spy = mockFetch({ ...REPORT, applied: true });
      const { result } = renderHook(() => useLLMPricingSheet());

      await act(async () => {
        await result.current.apply(file('edited.xlsx'), 'abc123');
      });

      expect(spy.mock.calls[0][1].body).toBeInstanceOf(FormData);
    });

    it('surfaces a stale-plan refusal', async () => {
      mockFetch({ detail: 'the catalogue changed since this plan was reviewed' }, false, 400);
      const { result } = renderHook(() => useLLMPricingSheet());

      await expect(result.current.apply(file(), 'stale')).rejects.toThrow(/changed/);
    });
  });
});
