/**
 * At which anticipated instants LIA may come back (ADR-281, lot 2).
 *
 * The list is the shared `RefusalSwitches`, whose four production-paid
 * properties are already pinned by the source-switch suite. What is pinned HERE
 * is what is specific to the kinds, and one of them is a genuine difference:
 * a requirement is a connector this account does not have — narrowed by the
 * SERVER, because only the server knows what is connected — where a source's
 * requirement is a sibling the reader themselves refused.
 */

import { describe, expect, it, vi } from 'vitest';
import userEvent from '@testing-library/user-event';

import { MomentKindSwitches } from '@/components/settings/MomentKindSwitches';
import { renderWithProviders, screen } from '@/__tests__/test-utils';
import enDict from '../../../../locales/en/translation.json';
import frDict from '../../../../locales/fr/translation.json';

const KINDS = ['event_followup'];

describe('MomentKindSwitches', () => {
  it('offers one named switch per kind the server publishes', () => {
    renderWithProviders(
      <MomentKindSwitches
        allKinds={KINDS}
        disabledKinds={[]}
        updating={false}
        onChange={vi.fn()}
      />
    );

    expect(screen.getAllByRole('switch')).toHaveLength(KINDS.length);
  });

  it('shows a kind ON when nothing is refused', () => {
    renderWithProviders(
      <MomentKindSwitches
        allKinds={KINDS}
        disabledKinds={[]}
        updating={false}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole('switch')).toBeChecked();
  });

  it('shows a refused kind OFF', () => {
    renderWithProviders(
      <MomentKindSwitches
        allKinds={KINDS}
        disabledKinds={['event_followup']}
        updating={false}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole('switch')).not.toBeChecked();
  });

  it('sends the full replacement set, never a partial diff', async () => {
    const onChange = vi.fn();
    renderWithProviders(
      <MomentKindSwitches
        allKinds={KINDS}
        disabledKinds={[]}
        updating={false}
        onChange={onChange}
      />
    );

    await userEvent.click(screen.getByRole('switch'));

    expect(onChange).toHaveBeenCalledWith(['event_followup']);
  });

  it('removes a kind from the set when switched back on', async () => {
    const onChange = vi.fn();
    renderWithProviders(
      <MomentKindSwitches
        allKinds={KINDS}
        disabledKinds={['event_followup']}
        updating={false}
        onChange={onChange}
      />
    );

    await userEvent.click(screen.getByRole('switch'));

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('refuses a second write while one is in flight, without losing the tab stop', async () => {
    const onChange = vi.fn();
    renderWithProviders(
      <MomentKindSwitches
        allKinds={KINDS}
        disabledKinds={[]}
        updating
        onChange={onChange}
      />
    );

    const control = screen.getByRole('switch');
    await userEvent.click(control);

    expect(onChange).not.toHaveBeenCalled();
    // aria-disabled, never disabled: focus must not move out from under the
    // reader mid-interaction.
    expect(control).toHaveAttribute('aria-disabled', 'true');
    expect(control).not.toBeDisabled();
  });

  it('says what a kind is waiting for, without renaming the switch', () => {
    renderWithProviders(
      <MomentKindSwitches
        allKinds={KINDS}
        disabledKinds={[]}
        kindDependencies={{ event_followup: ['calendar'] }}
        updating={false}
        onChange={vi.fn()}
      />
    );

    const control = screen.getByRole('switch');
    // The note is a fact ABOUT the kind, attached by description — inside the
    // label it would read as the switch's own state.
    expect(control).toHaveAttribute('aria-describedby');
    expect(control.getAttribute('aria-describedby')).toContain('moment-kind-event_followup');
  });

  it('stays quiet when every requirement is met', () => {
    renderWithProviders(
      <MomentKindSwitches
        allKinds={KINDS}
        disabledKinds={[]}
        kindDependencies={{}}
        updating={false}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole('switch')).not.toHaveAttribute('aria-describedby');
  });

  it('does not require the dependencies prop — an older payload simply says nothing', () => {
    renderWithProviders(
      <MomentKindSwitches
        allKinds={KINDS}
        disabledKinds={[]}
        updating={false}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole('switch')).not.toHaveAttribute('aria-describedby');
  });

  it('renders nothing at all when the deployment publishes no kind', () => {
    const { container } = renderWithProviders(
      <MomentKindSwitches allKinds={[]} disabledKinds={[]} updating={false} onChange={vi.fn()} />
    );

    expect(container.querySelectorAll('[role="switch"]')).toHaveLength(0);
  });
});

describe('the labels this panel renders really exist', () => {
  // The i18n stub echoes keys, so a component test cannot tell a translated
  // label from a missing one. Six-locale parity is enforced elsewhere; what is
  // checked here is that the reference locales actually SAY something — a key
  // present with an empty value passes parity and renders blank.
  type Namespace = { moments: Record<string, unknown> };

  it.each<[string, Namespace]>([
    ['en', enDict],
    ['fr', frDict],
  ])('%s names every kind, plus the section it lives in', (_lng, dict) => {
    for (const kind of KINDS) {
      expect(dict.moments[`kind_${kind}`]).toBeTruthy();
      expect(dict.moments[`kind_${kind}_help`]).toBeTruthy();
    }
    expect(dict.moments.settings_title).toBeTruthy();
    expect(dict.moments.settings_description).toBeTruthy();
  });
});

describe('what a missing requirement actually SAYS', () => {
  /**
   * A kind's requirement is a connector the account does not have. The source
   * switches' own note reads "…, which you have switched off", which is true
   * of a sibling source a reader refused and FALSE here: it tells someone they
   * turned off a calendar they never connected.
   *
   * The two vocabularies mean different things by "missing", so they cannot
   * share the sentence — the component's docstring already said so while the
   * string did not.
   */
  it('names the connector as absent, never as refused', () => {
    renderWithProviders(
      <MomentKindSwitches
        allKinds={KINDS}
        disabledKinds={[]}
        kindDependencies={{ event_followup: ['calendar'] }}
        updating={false}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText(/moments\.requires_connector/)).toBeInTheDocument();
    expect(screen.queryByText(/heartbeat\.source_requires/)).toBeNull();
  });

  it.each<[string, Record<string, Record<string, unknown>>]>([
    ['en', enDict as never],
    ['fr', frDict as never],
  ])('%s says it in words, and never claims the reader switched it off', (_lng, dict) => {
    const sentence = String(dict.moments.requires_connector ?? '');

    expect(sentence).toBeTruthy();
    expect(sentence).toContain('{{sources}}');
    // The source note's own wording, which must not have been copied here.
    expect(sentence).not.toEqual(String(dict.heartbeat.source_requires ?? ''));
  });
});
