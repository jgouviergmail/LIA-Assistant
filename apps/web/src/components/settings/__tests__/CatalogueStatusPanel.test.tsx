/**
 * The registry verdict, rendered where the catalogue is (ADR-244).
 *
 * The work the two vendored registries did — 83 rows corrected, 94 of 125
 * corroborated — happened in a migration and was invisible from the screen
 * that shows the catalogue. These tests pin what the panel must say, and the
 * two ways it must stay quiet: no verdict, and nothing to report.
 */
import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';
import type { CatalogueStatus } from '@/lib/actions/settings-actions';
import { CatalogueStatusPanel } from '../CatalogueStatusPanel';

/** Identity translator: assertions target keys, not a locale's wording. */
const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}:${JSON.stringify(options)}` : key;

function status(over: Partial<CatalogueStatus> = {}): CatalogueStatus {
  return {
    compared: 101,
    auto: 0,
    review: 0,
    retiring: [],
    provenance: { imported: 80, declared: 21 },
    snapshot_generated_at: '2026-08-24T09:00:00Z',
    ...over,
  };
}

describe('when there is no verdict', () => {
  it('renders nothing at all', () => {
    const { container } = renderWithProviders(<CatalogueStatusPanel status={null} t={t} />);
    expect(container.firstChild).toBeNull();
  });
});

describe('the provenance breakdown', () => {
  it('shows every value present, with its count', () => {
    renderWithProviders(<CatalogueStatusPanel status={status()} t={t} />);
    expect(screen.getByText(/provenance\.declared.*21/)).toBeTruthy();
    expect(screen.getByText(/provenance\.imported.*80/)).toBeTruthy();
  });

  it('omits a value nothing carries, rather than printing a zero', () => {
    renderWithProviders(<CatalogueStatusPanel status={status()} t={t} />);
    expect(screen.queryByText(/provenance\.verified/)).toBeNull();
  });

  it('lists the untrusted rows first — that is what the reader looks for', () => {
    renderWithProviders(
      <CatalogueStatusPanel status={status({ provenance: { imported: 80, declared: 21 } })} t={t} />
    );
    const badges = screen.getAllByText(/catalogue\.provenance\./);
    expect(badges[0].textContent).toContain('declared');
  });
});

describe('the alignment line', () => {
  it('says the catalogue is aligned when nothing is pending', () => {
    renderWithProviders(<CatalogueStatusPanel status={status()} t={t} />);
    expect(screen.getByText(/catalogue\.aligned/)).toBeTruthy();
    expect(screen.queryByText(/catalogue\.pending/)).toBeNull();
  });

  it('picks the singular key for a single model', () => {
    // `{{count}}` would hand the phrase to i18next's plural resolution; this
    // codebase chooses the key itself (`results_count` / `_plural`), so a
    // catalogue of one never reads "1 models".
    renderWithProviders(<CatalogueStatusPanel status={status({ compared: 1 })} t={t} />);
    const line = screen.getByText(/catalogue\.aligned/);
    expect(line.textContent).toContain('catalogue.aligned:');
    expect(line.textContent).not.toContain('aligned_plural');
    expect(line.textContent).toContain('"total":1');
  });

  it('picks the plural key beyond one', () => {
    renderWithProviders(<CatalogueStatusPanel status={status({ compared: 101 })} t={t} />);
    expect(screen.getByText(/catalogue\.aligned_plural/)).toBeTruthy();
  });

  it('reports the two kinds of pending correction separately', () => {
    // They are different questions: `auto` touches rows nobody curated,
    // `review` would overwrite a human decision.
    renderWithProviders(<CatalogueStatusPanel status={status({ auto: 3, review: 2 })} t={t} />);
    const line = screen.getByText(/catalogue\.pending/);
    expect(line.textContent).toContain('"auto":3');
    expect(line.textContent).toContain('"review":2');
  });
});

describe('the retirement list', () => {
  const retiring: CatalogueStatus['retiring'] = [
    {
      model_name: 'gpt-4.1-nano',
      provider: 'openai',
      state: 'announced',
      deprecation_date: '2026-10-23',
      seen_by: ['litellm', 'modelsdev'],
    },
    {
      model_name: 'gpt-5.2-chat-latest',
      provider: 'openai',
      state: 'disputed',
      deprecation_date: '2026-08-10',
      seen_by: ['litellm'],
    },
  ];

  it('is absent when nothing is retiring', () => {
    renderWithProviders(<CatalogueStatusPanel status={status()} t={t} />);
    expect(screen.queryByText(/retiring_summary/)).toBeNull();
  });

  it('keeps the list folded, so the summary alone tells the reader it exists', () => {
    // A folded block is an index entry: the count is visible, the rows are
    // not in the DOM at all (SettingsDisclosure unmounts its children).
    renderWithProviders(<CatalogueStatusPanel status={status({ retiring })} t={t} />);
    expect(screen.getByText(/retiring_summary/)).toBeTruthy();
    expect(screen.queryByText('gpt-4.1-nano')).toBeNull();
  });

  it('names each model, its state and where the evidence came from', async () => {
    const { user } = renderWithProviders(
      <CatalogueStatusPanel status={status({ retiring })} t={t} />
    );
    await user.click(screen.getByText(/retiring_summary/));
    expect(screen.getByText('gpt-4.1-nano')).toBeTruthy();
    expect(screen.getByText(/catalogue\.state\.announced/)).toBeTruthy();
    expect(screen.getByText(/catalogue\.state\.disputed/)).toBeTruthy();
    expect(screen.getByText('litellm, modelsdev')).toBeTruthy();
  });

  it('does not dress a disputed retirement as a settled one', async () => {
    // Two registries disagreeing is why the model is still offered.
    const { user } = renderWithProviders(
      <CatalogueStatusPanel status={status({ retiring })} t={t} />
    );
    await user.click(screen.getByText(/retiring_summary/));
    const disputed = screen.getByText(/catalogue\.state\.disputed/);
    expect(disputed.className).not.toContain('warning');
  });
});

describe('a payload the panel cannot fully read', () => {
  it('renders what it can rather than taking the catalogue table down with it', () => {
    // This panel is a DIAGNOSTIC above the table. Measured: a response without
    // `provenance` threw inside render and unmounted the whole section — the
    // models disappeared because their diagnostic was malformed.
    const partial = { compared: 12 } as unknown as CatalogueStatus;
    renderWithProviders(<CatalogueStatusPanel status={partial} t={t} />);
    expect(screen.getByText(/catalogue\.title/)).toBeTruthy();
    expect(screen.getByText(/catalogue\.aligned/)).toBeTruthy();
    expect(screen.queryByText(/retiring_summary/)).toBeNull();
  });
});

describe('the snapshot date', () => {
  it('says which snapshot produced the verdict', () => {
    renderWithProviders(<CatalogueStatusPanel status={status()} t={t} />);
    expect(screen.getByText(/catalogue\.snapshot/)).toBeTruthy();
  });

  it('stays silent when the snapshot carries no date', () => {
    renderWithProviders(
      <CatalogueStatusPanel status={status({ snapshot_generated_at: null })} t={t} />
    );
    expect(screen.queryByText(/catalogue\.snapshot/)).toBeNull();
  });
});
