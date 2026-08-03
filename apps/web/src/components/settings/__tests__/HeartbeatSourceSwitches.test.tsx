/**
 * HeartbeatSourceSwitches — deciding what may interrupt you.
 *
 * Until now a source was shown as connected or not, and the documented way to
 * stop mail-driven nudges was to disconnect the mail connector — which also
 * removes the tool you ask with. These switches separate the two questions:
 *
 *  - CONNECTED (availability) is a fact about the account;
 *  - PERMITTED (this switch) is a decision about interruptions.
 *
 * A source can be connected and refused, or unavailable and permitted. The
 * component must never conflate them, and must never present a switch as
 * "off" merely because the service is not connected.
 */

import { describe, it, expect, vi } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import enDict from '../../../../locales/en/translation.json';
import frDict from '../../../../locales/fr/translation.json';
import { HeartbeatSourceSwitches } from '../HeartbeatSourceSwitches';

const ALL = ['calendar', 'emails', 'tasks', 'weather'];

function makeProps(
  over: Partial<React.ComponentProps<typeof HeartbeatSourceSwitches>> = {}
): React.ComponentProps<typeof HeartbeatSourceSwitches> {
  return {
    allSources: ALL,
    disabledSources: [],
    availableSources: ['calendar', 'emails'],
    updating: false,
    onChange: vi.fn(),
    ...over,
  };
}

const switchFor = (source: string) =>
  screen.getByRole('switch', { name: `heartbeat.source_${source}` });

describe('HeartbeatSourceSwitches — permission, not availability', () => {
  it('offers one named switch per source the server publishes', () => {
    renderWithProviders(<HeartbeatSourceSwitches {...makeProps()} />);

    expect(screen.getAllByRole('switch')).toHaveLength(ALL.length);
    for (const source of ALL) expect(switchFor(source)).toBeInTheDocument();
  });

  it('shows every source ON when nothing is refused', () => {
    // The default is "everything may interrupt me" — an account that never
    // opened this panel behaves exactly as before.
    renderWithProviders(<HeartbeatSourceSwitches {...makeProps()} />);

    for (const source of ALL) expect(switchFor(source)).toBeChecked();
  });

  it('shows a refused source OFF even when it is connected', () => {
    renderWithProviders(
      <HeartbeatSourceSwitches {...makeProps({ disabledSources: ['emails'] })} />
    );

    expect(switchFor('emails')).not.toBeChecked();
    expect(switchFor('calendar')).toBeChecked();
  });

  it('keeps an unavailable source ON — not connected is not the same as refused', () => {
    // `tasks` is absent from availableSources; the switch still reads "on",
    // because the user has refused nothing. Showing it off would state a
    // decision they never made.
    renderWithProviders(<HeartbeatSourceSwitches {...makeProps()} />);

    expect(switchFor('tasks')).toBeChecked();
  });

  it('says which sources are not connected, without disabling their switch', () => {
    renderWithProviders(<HeartbeatSourceSwitches {...makeProps()} />);

    // The fact is surfaced…
    expect(screen.getAllByText('heartbeat.source_not_connected')).toHaveLength(2);
    // …and the decision stays available: connecting later must not require
    // coming back here to re-permit the source.
    expect(switchFor('tasks')).toBeEnabled();
  });
});

describe('HeartbeatSourceSwitches — writing the decision', () => {
  it('adds a source to the refusal set when switched off', () => {
    const onChange = vi.fn();
    renderWithProviders(<HeartbeatSourceSwitches {...makeProps({ onChange })} />);

    switchFor('emails').click();

    expect(onChange).toHaveBeenCalledWith(['emails']);
  });

  it('removes it when switched back on', () => {
    const onChange = vi.fn();
    renderWithProviders(
      <HeartbeatSourceSwitches
        {...makeProps({ onChange, disabledSources: ['emails', 'weather'] })}
      />
    );

    switchFor('emails').click();

    expect(onChange).toHaveBeenCalledWith(['weather']);
  });

  it('sends the full replacement set, never a partial diff', () => {
    // The API replaces the set wholesale; sending one key would silently
    // re-enable everything else.
    const onChange = vi.fn();
    renderWithProviders(
      <HeartbeatSourceSwitches {...makeProps({ onChange, disabledSources: ['calendar'] })} />
    );

    switchFor('weather').click();

    expect(onChange).toHaveBeenCalledWith(['calendar', 'weather']);
  });

  it('refuses a second write while one is in flight, without losing the tab stop', () => {
    // `disabled` on a focused control blurs it and drops it from the tab
    // order; `aria-disabled` + a guard in the handler prevents the double
    // submit while the keyboard user keeps their place.
    const onChange = vi.fn();
    renderWithProviders(<HeartbeatSourceSwitches {...makeProps({ onChange, updating: true })} />);

    const target = switchFor('emails');
    expect(target).toHaveAttribute('aria-disabled', 'true');
    expect(target).toBeEnabled();

    target.click();

    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('HeartbeatSourceSwitches — every source is named in the locale', () => {
  const SOURCES = [
    'calendar',
    'emails',
    'tasks',
    'weather',
    'interests',
    'memories',
    'journals',
    'health_signals',
    'birthdays',
    'open_loops',
    'departure',
  ];

  // `unknown` values, not `string`: the `heartbeat` namespace also holds
  // nested groups (`settings: { title, description }`), so a `Record<string,
  // string>` annotation would be a lie the compiler rightly refuses.
  type Namespace = { heartbeat: Record<string, unknown> };

  it.each<[string, Namespace]>([
    ['en', enDict],
    ['fr', frDict],
  ])('%s labels all eleven sources plus the availability note', (_lng, dict) => {
    for (const source of SOURCES) {
      expect(dict.heartbeat[`source_${source}`]).toBeTruthy();
    }
    expect(dict.heartbeat.source_not_connected).toBeTruthy();
    expect(dict.heartbeat.sources_permission_title).toBeTruthy();
    expect(dict.heartbeat.sources_permission_description).toBeTruthy();
  });
});

describe('a switch that is on and yields nothing', () => {
  // `fetch_departure_advice` returns None without calendar events. Refusing
  // `calendar` therefore neutralises `departure` — the switch stays on and
  // nothing ever arrives, with no way to find out why. The server publishes
  // the constraint (ADR-184); this is the panel saying it.
  const DEPENDENCIES = { departure: ['calendar'] };

  function renderPanel(disabled: string[]) {
    return renderWithProviders(
      <HeartbeatSourceSwitches
        allSources={['calendar', 'departure']}
        disabledSources={disabled}
        availableSources={['calendar', 'departure']}
        sourceDependencies={DEPENDENCIES}
        updating={false}
        onChange={vi.fn()}
      />
    );
  }

  it('says what a dependent source is waiting for', () => {
    renderPanel(['calendar']);

    const note = screen.getByText('heartbeat.source_requires');
    expect(note).toBeInTheDocument();
  });

  it('attaches the note to the switch without renaming it', () => {
    renderPanel(['calendar']);

    // The accessible NAME stays the source. A requirement folded into it
    // would read as a state of the control ("Departure requires Calendar"),
    // which is not what the switch is set to.
    const toggle = screen.getByRole('switch', { name: 'heartbeat.source_departure' });
    const described = toggle.getAttribute('aria-describedby');
    expect(described).toBeTruthy();
    expect(document.getElementById(described!)).toHaveTextContent('heartbeat.source_requires');
  });

  it('stays quiet while the dependency is satisfied', () => {
    renderPanel([]);

    expect(screen.queryByText('heartbeat.source_requires')).not.toBeInTheDocument();
  });

  it('stays quiet when the reader refused the dependent source too', () => {
    // They turned departure off themselves — there is no surprise to explain,
    // and saying it anyway would be noise on a decision already made.
    renderPanel(['calendar', 'departure']);

    expect(screen.queryByText('heartbeat.source_requires')).not.toBeInTheDocument();
  });

  it('does not require the prop — an older payload simply says nothing', () => {
    renderWithProviders(
      <HeartbeatSourceSwitches
        allSources={['calendar', 'departure']}
        disabledSources={['calendar']}
        availableSources={['calendar', 'departure']}
        updating={false}
        onChange={vi.fn()}
      />
    );

    expect(screen.queryByText('heartbeat.source_requires')).not.toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'heartbeat.source_departure' })).toBeInTheDocument();
  });
});
