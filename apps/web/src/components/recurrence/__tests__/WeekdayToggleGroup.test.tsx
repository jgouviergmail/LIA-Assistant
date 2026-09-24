/**
 * The seven weekday toggles, shared by the recurrence editor (which days a
 * schedule fires) and the LLM pricing windows (which UTC days a peak window
 * applies on — DeepSeek bills its peaks Monday to Friday).
 *
 * One component for both, because the two copies would drift: the keep-one
 * rule, the named sets and the weekend break are the reader's contract, not
 * each screen's.
 */

import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import enDict from '../../../../locales/en/translation.json';
import frDict from '../../../../locales/fr/translation.json';
import { WeekdayToggleGroup } from '../WeekdayToggleGroup';

function setup(days: number[]) {
  const onChange = vi.fn();
  const view = renderWithProviders(
    <WeekdayToggleGroup days={days} onChange={onChange} label="Days it applies" />
  );
  return { onChange, ...view };
}

describe('WeekdayToggleGroup', () => {
  it('is ONE group, named by its label', () => {
    setup([1]);
    const group = screen.getByRole('group', { name: 'Days it applies' });
    expect(group.querySelectorAll('button')).toHaveLength(7);
  });

  it('names each day and states whether it is chosen', () => {
    setup([1, 5]);
    expect(screen.getByRole('button', { name: 'scheduled_actions.days.d1' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByRole('button', { name: 'scheduled_actions.days.d6' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
  });

  it('adds a day in week order, without dropping the others', async () => {
    const { onChange, user } = setup([5]);
    await user.click(screen.getByRole('button', { name: 'scheduled_actions.days.d2' }));
    expect(onChange).toHaveBeenCalledWith([2, 5]);
  });

  it('never lets the last day go, and says why beforehand', async () => {
    const { onChange, user } = setup([3]);
    const wednesday = screen.getByRole('button', { name: 'scheduled_actions.days.d3' });
    expect(wednesday).toHaveAttribute('aria-disabled', 'true');
    expect(wednesday).toHaveAccessibleDescription('recurrence.error_no_weekday');

    await user.click(wednesday);

    expect(onChange).not.toHaveBeenCalled();
  });

  it('offers the working week and the weekend in one press', async () => {
    const { onChange, user } = setup([3]);
    await user.click(screen.getByRole('button', { name: 'recurrence.weekday_set.workdays' }));
    expect(onChange).toHaveBeenLastCalledWith([1, 2, 3, 4, 5]);
    await user.click(screen.getByRole('button', { name: 'recurrence.weekday_set.weekend' }));
    expect(onChange).toHaveBeenLastCalledWith([6, 7]);
  });
});

describe('the words it renders really exist', () => {
  // The i18n stub echoes keys: a component test cannot tell a translated label
  // from a missing one. What is checked here is that both reference locales
  // SAY something for every string the group shows.
  type Dict = {
    scheduled_actions: { days: Record<string, string> };
    recurrence: { error_no_weekday: string; weekday_set: Record<string, string> };
  };

  it.each<[string, Dict]>([
    ['en', enDict as never],
    ['fr', frDict as never],
  ])('%s names the seven days, the keep-one rule and the named sets', (_lng, dict) => {
    for (let day = 1; day <= 7; day += 1) {
      expect(dict.scheduled_actions.days[`d${day}`]).toBeTruthy();
    }
    expect(dict.recurrence.error_no_weekday).toBeTruthy();
    for (const set of ['all', 'workdays', 'weekend']) {
      expect(dict.recurrence.weekday_set[set]).toBeTruthy();
    }
  });
});
