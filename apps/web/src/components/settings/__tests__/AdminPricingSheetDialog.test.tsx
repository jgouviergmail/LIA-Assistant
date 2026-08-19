/**
 * The import dialog is where an administrator decides whether to change every
 * price in the product. It therefore has to be readable before it is clever:
 * the preview groups changes by nature, shows only what moves, puts problems
 * first with the cell that carries them, and never lets an apply happen on a
 * plan nobody looked at.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { AdminPricingSheetDialog } from '../AdminPricingSheetDialog';
import type { PricingSheetImportReport } from '@/hooks/useLLMPricingSheet';

vi.mock('@/i18n/client', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && Object.keys(options).length
        ? `${key}:${Object.entries(options)
            .map(([k, v]) => `${k}=${v}`)
            .join(',')}`
        : key,
  }),
}));

function report(overrides: Partial<PricingSheetImportReport> = {}): PricingSheetImportReport {
  return {
    applied: false,
    plan: {
      plan_fingerprint: 'fp-1',
      counts: { update: 1, unchanged: 2 },
      changes: [
        {
          model_name: 'gpt-4.1-mini',
          action: 'update',
          fields: [{ field: 'input_unit_price', before: '0.400000', after: '0.500000' }],
          slots_before: 0,
          slots_after: 0,
          row_number: 3,
        },
        {
          model_name: 'quiet-a',
          action: 'unchanged',
          fields: [],
          slots_before: 0,
          slots_after: 0,
          row_number: 4,
        },
        {
          model_name: 'quiet-b',
          action: 'unchanged',
          fields: [],
          slots_before: 0,
          slots_after: 0,
          row_number: 5,
        },
      ],
      issues: [],
      is_applicable: true,
      pricing_changes: ['gpt-4.1-mini'],
      ...overrides.plan,
    },
    created: [],
    updated: [],
    deactivated: [],
    reactivated: [],
    unchanged: 2,
    ...overrides,
  };
}

function setup(props: Partial<Parameters<typeof AdminPricingSheetDialog>[0]> = {}) {
  // The EFFECTIVE handlers are returned, not the defaults: returning the
  // defaults while rendering an override makes every assertion watch a spy the
  // component never calls.
  const effective = {
    onOpenChange: vi.fn(),
    onApply: vi.fn().mockResolvedValue(report({ applied: true })),
    onPreview: vi.fn().mockResolvedValue(report()),
    busy: false,
    lng: 'en' as const,
    ...props,
  };
  render(<AdminPricingSheetDialog open {...effective} />);
  return effective;
}

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

function workbook(name = 'catalogue.xlsx'): File {
  return new File(['x'], name, { type: XLSX });
}

async function upload(file = workbook()) {
  const input = screen.getByLabelText(/choose_file/i);
  await userEvent.upload(input, file);
}

describe('AdminPricingSheetDialog', () => {
  describe('accessibility and naming', () => {
    it('is a dialog with an accessible name', () => {
      setup();
      expect(screen.getByRole('dialog', { name: /import_title/i })).toBeInTheDocument();
    });

    it('names the file control', () => {
      setup();
      expect(screen.getByLabelText(/choose_file/i)).toBeInTheDocument();
    });

    it('offers a real button to reach the input', () => {
      // The native file control cannot be styled and looks like nothing else in
      // the product, so it is hidden behind a button — which must be a button,
      // not a decorated div.
      setup();
      expect(screen.getByRole('button', { name: /choose_file/i })).toBeInTheDocument();
    });

    it('accepts only spreadsheet files', () => {
      setup();
      expect(screen.getByLabelText(/choose_file/i)).toHaveAttribute(
        'accept',
        expect.stringContaining('.xlsx')
      );
    });

    it('shows which file was chosen', async () => {
      // A hidden input tells the reader nothing; the chosen name has to appear
      // somewhere or they cannot tell whether their pick registered.
      setup();

      await upload(workbook('tarifs-aout.xlsx'));

      expect(await screen.findByText('tarifs-aout.xlsx')).toBeInTheDocument();
    });

    it('offers no apply before anything has been reviewed', () => {
      setup();
      expect(screen.queryByRole('button', { name: /apply/i })).not.toBeInTheDocument();
    });
  });

  describe('preview', () => {
    it('previews the chosen file without applying it', async () => {
      const { onPreview, onApply } = setup();

      await upload();

      await waitFor(() => expect(onPreview).toHaveBeenCalledTimes(1));
      expect(onApply).not.toHaveBeenCalled();
    });

    it('summarises the plan by nature', async () => {
      setup();
      await upload();

      await waitFor(() => {
        expect(screen.getByText(/action\.update/)).toBeInTheDocument();
      });
    });

    it('shows a changed field as before and after', async () => {
      setup();
      await upload();

      await waitFor(() => expect(screen.getByText('0.400000')).toBeInTheDocument());
      expect(screen.getByText('0.500000')).toBeInTheDocument();
    });

    it('names the model each change applies to', async () => {
      setup();
      await upload();

      await waitFor(() => expect(screen.getByText('gpt-4.1-mini')).toBeInTheDocument());
    });

    it('does not list untouched rows among the changes', async () => {
      setup();
      await upload();

      await waitFor(() => expect(screen.getByText('gpt-4.1-mini')).toBeInTheDocument());
      expect(screen.queryByText('quiet-a')).not.toBeInTheDocument();
    });

    it('states how many rows it left alone', async () => {
      setup();
      await upload();

      await waitFor(() => expect(screen.getByText(/unchanged.*2|2.*unchanged/i)).toBeInTheDocument());
    });
  });

  describe('problems', () => {
    const failing = report({
      plan: {
        plan_fingerprint: 'fp-x',
        counts: {},
        changes: [],
        issues: [
          {
            code: 'not_a_number',
            sheet: 'Modeles',
            cell: 'M42',
            column: 'input_unit_price',
            params: { value: 'gratuit' },
          },
        ],
        is_applicable: false,
        pricing_changes: [],
      },
    });

    it('shows the problem and refuses to offer an apply', async () => {
      setup({ onPreview: vi.fn().mockResolvedValue(failing) });
      await upload();

      await waitFor(() => expect(screen.getByText(/issue\.not_a_number/)).toBeInTheDocument());
      expect(screen.queryByRole('button', { name: /apply/i })).not.toBeInTheDocument();
    });

    it('points at the cell that carries the problem', async () => {
      setup({ onPreview: vi.fn().mockResolvedValue(failing) });
      await upload();

      await waitFor(() => expect(screen.getByText(/Modeles/)).toBeInTheDocument());
      expect(screen.getByText(/M42/)).toBeInTheDocument();
    });

    it('surfaces a rejected upload instead of failing silently', async () => {
      setup({ onPreview: vi.fn().mockRejectedValue(new Error('workbook exceeds the limit')) });
      await upload();

      await waitFor(() =>
        expect(screen.getByRole('alert')).toHaveTextContent(/exceeds the limit/)
      );
    });
  });

  describe('apply', () => {
    it('carries the fingerprint of the plan that was shown', async () => {
      const { onApply } = setup();
      await upload();
      await waitFor(() => expect(screen.getByRole('button', { name: /apply/i })).toBeEnabled());

      await userEvent.click(screen.getByRole('button', { name: /apply/i }));

      await waitFor(() => expect(onApply).toHaveBeenCalledWith(expect.any(File), 'fp-1'));
    });

    it('reports what was actually written', async () => {
      const applied = report({
        applied: true,
        updated: ['gpt-4.1-mini'],
        unchanged: 2,
      });
      const { onApply } = setup({ onApply: vi.fn().mockResolvedValue(applied) });
      await upload();
      await waitFor(() => expect(screen.getByRole('button', { name: /apply/i })).toBeEnabled());

      await userEvent.click(screen.getByRole('button', { name: /apply/i }));

      await waitFor(() => expect(onApply).toHaveBeenCalled());
      expect(await screen.findByText(/applied_title/)).toBeInTheDocument();
    });

    it('does not fire twice when the control is clicked twice', async () => {
      // A guard in the handler, not `disabled` on a focused control: disabling
      // it blurs the button and drops the keyboard user back on the body.
      //
      // The first call is held open deliberately. Letting it settle between the
      // two clicks would test two SEQUENTIAL clicks — which are allowed to fire
      // twice — and the assertion would pass or fail on timing alone.
      let release: (value: PricingSheetImportReport) => void = () => {};
      const held = vi.fn(
        () => new Promise<PricingSheetImportReport>(resolve => (release = resolve))
      );
      setup({ onApply: held });
      await upload();
      await waitFor(() => expect(screen.getByRole('button', { name: /apply/i })).toBeEnabled());

      const button = screen.getByRole('button', { name: /apply/i });
      await userEvent.click(button);
      await userEvent.click(button);

      expect(held).toHaveBeenCalledTimes(1);
      release(report({ applied: true }));
    });

    it('keeps the control focusable while it works', async () => {
      let release: (value: PricingSheetImportReport) => void = () => {};
      const held = vi.fn(
        () => new Promise<PricingSheetImportReport>(resolve => (release = resolve))
      );
      setup({ onApply: held });
      await upload();
      await waitFor(() => expect(screen.getByRole('button', { name: /apply/i })).toBeEnabled());

      const button = screen.getByRole('button', { name: /apply/i });
      await userEvent.click(button);

      expect(button).toHaveAttribute('aria-disabled', 'true');
      expect(button).not.toBeDisabled();
      release(report({ applied: true }));
    });
  });

  describe('reset', () => {
    it('forgets the previous plan when a new file is chosen', async () => {
      const onPreview = vi
        .fn()
        .mockResolvedValueOnce(report())
        .mockResolvedValueOnce(
          report({ plan: { ...report().plan, changes: [], counts: {}, plan_fingerprint: 'fp-2' } })
        );
      setup({ onPreview });

      await upload(workbook('first.xlsx'));
      await waitFor(() => expect(screen.getByText('gpt-4.1-mini')).toBeInTheDocument());

      await upload(workbook('second.xlsx'));

      await waitFor(() => expect(screen.queryByText('gpt-4.1-mini')).not.toBeInTheDocument());
    });
  });
});
