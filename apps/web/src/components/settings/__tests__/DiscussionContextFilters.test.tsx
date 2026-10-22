import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import type { Language } from '@/i18n/settings';
import {
  DISCUSSION_SEARCH_DELAY_MS,
  DiscussionContextFilters,
  appliedFilters,
} from '../DiscussionContextFilters';

function lookup(tree: unknown, path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
      tree
    );
}

vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: Language) => ({
    t: (key: string) => {
      const found = lookup(lng === 'fr' ? fr : en, key);
      return typeof found === 'string' ? found : key;
    },
  }),
}));

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe.each(['en', 'fr'] as const)('discussion context filters in %s', lng => {
  const messages = (lng === 'fr' ? fr : en).discussions.filters;

  it('applies a list choice at once, with no apply button left', () => {
    const onChange = vi.fn();
    render(<DiscussionContextFilters lng={lng} filters={{}} onChange={onChange} />);
    expect(screen.queryByRole('button', { name: 'Filtrer' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Apply filters' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: messages.source }), {
      target: { value: 'calendar' },
    });
    expect(onChange).toHaveBeenLastCalledWith({ source: 'calendar' });
  });

  it('applies the search once typing pauses: one read per search, not per keystroke', () => {
    const onChange = vi.fn();
    render(<DiscussionContextFilters lng={lng} filters={{}} onChange={onChange} />);
    const search = screen.getByRole('searchbox', { name: messages.search });
    fireEvent.change(search, { target: { value: 'ran' } });
    fireEvent.change(search, { target: { value: 'rando' } });
    act(() => vi.advanceTimersByTime(DISCUSSION_SEARCH_DELAY_MS - 1));
    expect(onChange).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenLastCalledWith({ query: 'rando' });
  });

  it('applies the search at once on Enter, and never twice for the same filters', () => {
    const onChange = vi.fn();
    render(<DiscussionContextFilters lng={lng} filters={{}} onChange={onChange} />);
    const search = screen.getByRole('searchbox', { name: messages.search });
    fireEvent.change(search, { target: { value: ' hike ' } });
    fireEvent.submit(search.closest('form')!);
    expect(onChange).toHaveBeenLastCalledWith({ query: 'hike' });
    act(() => vi.advanceTimersByTime(DISCUSSION_SEARCH_DELAY_MS));
    // The pending pause was cancelled by Enter, and re-applying is not a new read.
    expect(onChange).toHaveBeenCalledOnce();
  });

  it('a list choice during a pause applies the search typed so far with it', () => {
    const onChange = vi.fn();
    render(<DiscussionContextFilters lng={lng} filters={{}} onChange={onChange} />);
    fireEvent.change(screen.getByRole('searchbox', { name: messages.search }), {
      target: { value: 'hike' },
    });
    fireEvent.change(screen.getByRole('combobox', { name: messages.kind }), {
      target: { value: 'episode' },
    });
    expect(onChange).toHaveBeenLastCalledWith({ query: 'hike', kind: 'episode' });
    act(() => vi.advanceTimersByTime(DISCUSSION_SEARCH_DELAY_MS));
    expect(onChange).toHaveBeenCalledOnce();
  });

  it('resets every filter', () => {
    const onChange = vi.fn();
    render(
      <DiscussionContextFilters lng={lng} filters={{ usable: 'false' }} onChange={onChange} />
    );
    fireEvent.click(screen.getByRole('button', { name: messages.reset }));
    expect(onChange).toHaveBeenLastCalledWith({});
    expect(screen.getByRole('combobox', { name: messages.usability })).toHaveValue('');
  });

  it('names every control by its label, spaced by the application gap', () => {
    render(<DiscussionContextFilters lng={lng} filters={{}} onChange={vi.fn()} />);
    for (const name of [messages.source, messages.kind, messages.usability]) {
      const control = screen.getByRole('combobox', { name });
      // Label and control share one stack with the 12 px gap (`space-y-3`).
      expect(control.parentElement?.className).toContain('space-y-3');
    }
    expect(screen.getByLabelText(messages.created_from)).toHaveAttribute('type', 'date');
  });
});

it('drops blank values and trims the search', () => {
  expect(appliedFilters({ query: '  ', source: '', kind: 'pattern' })).toEqual({
    kind: 'pattern',
  });
  expect(appliedFilters({ query: ' a b ' })).toEqual({ query: 'a b' });
});
