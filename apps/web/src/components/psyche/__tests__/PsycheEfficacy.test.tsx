import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, within } from '@/__tests__/test-utils';
import en from '../../../../locales/en/translation.json';
import fr from '../../../../locales/fr/translation.json';
import type { Language } from '@/i18n/settings';
import type { PsycheEfficacyProfile } from '@/types/psyche';
import { PsycheEfficacy } from '../PsycheEfficacy';

interface TestOwner {
  id: string;
  timezone?: string;
}
const auth = vi.hoisted((): { user: TestOwner | null } => ({
  user: { id: 'owner-a', timezone: 'Europe/Paris' },
}));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: auth.user }) }));
beforeEach(() => { auth.user = { id: 'owner-a', timezone: 'Europe/Paris' }; });

vi.mock('@/i18n/client', () => ({
  useTranslation: (lng: Language) => ({
    t: (key: string, values?: Record<string, string | number>) => {
      let value: unknown = lng === 'fr' ? fr : en;
      const resolvedKey =
        typeof values?.count === 'number'
          ? `${key}_${new Intl.PluralRules(lng).select(values.count)}`
          : key;
      for (const part of resolvedKey.split('.')) {
        value = value && typeof value === 'object' ? Reflect.get(value, part) : undefined;
      }
      if (typeof value !== 'string') return key;
      return value.replace(/{{(\w+)}}/g, (_, name: string) => String(values?.[name] ?? ''));
    },
  }),
}));

function profile(overrides: Partial<PsycheEfficacyProfile> = {}): PsycheEfficacyProfile {
  return {
    version: 1,
    window_days: 90,
    collection_enabled: true,
    influence_enabled: true,
    unassigned_feedback_count: 2,
    domains: [
      {
        domain: 'technical',
        status: 'observed',
        results: { success: 4, failure: 1, partial: 2, unknown: 3 },
        feedback: { helpful: 1, unhelpful: 2 },
        result_count: 5,
        feedback_count: 3,
        result_score: 0.7142857142857143,
        feedback_score: 0.4,
        last_observed_at: '2026-10-16T10:00:00Z',
      },
    ],
    ...overrides,
  };
}

async function open(lng: Language = 'en', data?: PsycheEfficacyProfile) {
  const result = renderWithProviders(<PsycheEfficacy lng={lng} profile={data} />);
  const control = screen.getByText(lng === 'fr' ? 'Auto-efficacité' : 'Self-efficacy');
  expect(control.closest('details')).not.toHaveAttribute('open');
  await result.user.click(control);
  return result;
}

describe('PsycheEfficacy evidence display', () => {
  it('uses the current account’s civil day for a late UTC observation', async () => {
    const data = profile();
    data.domains[0] = { ...data.domains[0], last_observed_at: '2026-10-16T23:30:00Z' };
    const { rerender } = await open('fr', data);
    expect(screen.getByText('Dernière observation : 17 oct. 2026')).toBeVisible();
    auth.user = { id: 'owner-b', timezone: 'America/New_York' };
    rerender(<PsycheEfficacy lng="fr" />);
    expect(screen.queryByText(/Dernière observation/)).not.toBeInTheDocument();
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
  });

  it.each([undefined, 'Invalid/Timezone'])('omits the observation date when account timezone is %s', async timezone => {
    auth.user = { id: 'owner-a', timezone };
    await open('fr', profile());
    expect(screen.queryByText(/Dernière observation/)).not.toBeInTheDocument();
    expect(screen.getAllByRole('meter')).toHaveLength(2);
  });

  it('keeps all seven domains unknown when no evidence profile exists', async () => {
    await open();
    for (const name of [
      'Planning',
      'Information',
      'Emotional support',
      'Creativity',
      'Technical',
      'Social',
      'Organization',
    ]) {
      expect(screen.getByRole('heading', { name })).toBeVisible();
    }
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    expect(screen.queryByText(/50\s*%/)).not.toBeInTheDocument();
    expect(screen.getAllByText('No index yet')).toHaveLength(7);
  });

  it('names each independent axis and states its own evidence base', async () => {
    await open('en', profile());
    const domain = screen.getByRole('region', { name: 'Technical' });
    expect(within(domain).getByRole('meter', { name: 'Technical · Results' })).toHaveAttribute(
      'aria-valuenow',
      '71'
    );
    expect(within(domain).getByRole('meter', { name: 'Technical · Usefulness' })).toHaveAttribute(
      'aria-valuenow',
      '40'
    );
    expect(within(domain).getByText('5 assessed outcomes')).toBeVisible();
    expect(within(domain).getByText('3 ratings')).toBeVisible();
    expect(within(domain).getByText('4 successful · 1 unsuccessful')).toBeVisible();
    expect(within(domain).getByText('2 partial · 3 undetermined')).toBeVisible();
    expect(within(domain).getByText('1 helpful · 2 unhelpful')).toBeVisible();
    expect(screen.getByText('2 ratings could not be assigned to one domain.')).toBeVisible();
    const planning = screen.getByRole('region', { name: 'Planning' });
    expect(within(planning).queryByRole('meter')).not.toBeInTheDocument();
  });

  it.each(['fr', 'en'] as const)('provides translated meter names and collection state in %s', async lng => {
    await open(lng, profile({ collection_enabled: false, influence_enabled: false }));
    const name = lng === 'fr' ? 'Technique · Résultats' : 'Technical · Results';
    expect(screen.getByRole('meter', { name })).toHaveAttribute(
      'aria-valuetext',
      expect.stringContaining('71')
    );
    expect(
      screen.getByText(lng === 'fr' ? 'Collecte en pause' : 'Collection paused')
    ).toBeVisible();
    expect(
      screen.getByText(lng === 'fr' ? 'Influence désactivée' : 'Influence off')
    ).toBeVisible();
  });

  it('does not retain the old owner’s indices when the profile changes', async () => {
    const { rerender } = await open('en', profile());
    expect(screen.getAllByRole('meter')).toHaveLength(2);
    rerender(<PsycheEfficacy lng="en" />);
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    expect(screen.queryByText('5 assessed outcomes')).not.toBeInTheDocument();
    expect(screen.queryByText('2 ratings could not be assigned to one domain.')).not.toBeInTheDocument();
  });

  it('keeps partial and unknown outcomes visible without inventing a scorable outcome', async () => {
    const data = profile();
    data.domains[0] = {
      ...data.domains[0],
      status: 'unobserved',
      result_count: 0,
      feedback_count: 0,
      result_score: null,
      feedback_score: 0.5,
    };
    await open('en', data);
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    expect(screen.queryByText(/NaN|50\s*%/)).not.toBeInTheDocument();
    expect(screen.getAllByText('No index yet')).toHaveLength(7);
    expect(screen.getByText('2 partial · 3 undetermined')).toBeVisible();
  });

  it.each([Number.NaN, Number.POSITIVE_INFINITY, -0.01, 1.01, null])(
    'does not render an invalid result index %s even with a positive observation count',
    async score => {
      const data = profile();
      data.domains[0] = {
        ...data.domains[0],
        result_score: score,
        feedback_count: 0,
        feedback_score: null,
        last_observed_at: 'invalid date',
      };
      await open('en', data);
      expect(screen.queryByRole('meter')).not.toBeInTheDocument();
      expect(screen.getByText('5 assessed outcomes')).toBeVisible();
      expect(screen.queryByText(/Last observation/)).not.toBeInTheDocument();
    }
  );

  it('preserves valid zero and full indices independently', async () => {
    const data = profile();
    data.domains[0] = { ...data.domains[0], result_score: 0, feedback_score: 1 };
    await open('en', data);
    expect(screen.getByRole('meter', { name: 'Technical · Results' })).toHaveAttribute(
      'aria-valuenow',
      '0'
    );
    expect(screen.getByRole('meter', { name: 'Technical · Usefulness' })).toHaveAttribute(
      'aria-valuenow',
      '100'
    );
  });
});
