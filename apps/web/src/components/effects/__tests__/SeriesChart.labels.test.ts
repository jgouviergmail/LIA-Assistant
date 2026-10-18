/**
 * The folded remainder reads in the reader's language, on every chart.
 *
 * The server folds each series' long tail into one bar labelled « other ». The
 * label tables a chart passes never knew it, and five charts pass none: the
 * bar read « other », in English, in every language.
 */
import { describe, expect, it, vi } from 'vitest';

import { displayedSliceLabel, FOLDED_SLICE_LABEL } from '../SeriesChart';

describe('displayedSliceLabel', () => {
  it('names the folded remainder in the reader’s language', () => {
    expect(displayedSliceLabel(FOLDED_SLICE_LABEL, 'Autres')).toBe('Autres');
  });

  it('never hands the folded remainder to the chart’s own vocabulary', () => {
    const renderLabel = vi.fn((label: string) => `rendered:${label}`);
    expect(displayedSliceLabel(FOLDED_SLICE_LABEL, 'Autres', renderLabel)).toBe('Autres');
    expect(renderLabel).not.toHaveBeenCalled();
  });

  it('renders every other label through the chart’s vocabulary, or as stored', () => {
    expect(displayedSliceLabel('answered', 'Autres', label => `rendered:${label}`)).toBe(
      'rendered:answered'
    );
    expect(displayedSliceLabel('gpt-5-mini', 'Autres')).toBe('gpt-5-mini');
  });
});
