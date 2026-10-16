import { EFFICACY_DOMAINS, type PsycheEfficacyProfile } from '../../src/types/psyche';

/** Independent axes with partial/unknown outcomes and mixed-domain feedback. No paid provider. */
export function psycheEfficacyProfile(): PsycheEfficacyProfile {
  return {
    version: 1,
    window_days: 90,
    collection_enabled: true,
    influence_enabled: true,
    unassigned_feedback_count: 2,
    domains: EFFICACY_DOMAINS.map(domain =>
      domain === 'technical'
        ? {
            domain,
            status: 'observed',
            results: { success: 4, failure: 1, partial: 2, unknown: 3 },
            feedback: { helpful: 1, unhelpful: 2 },
            result_count: 5,
            feedback_count: 3,
            result_score: 0.7142857142857143,
            feedback_score: 0.4,
            last_observed_at: '2026-10-16T10:00:00Z',
          }
        : {
            domain,
            status: 'unobserved',
            results: { success: 0, failure: 0, partial: 0, unknown: 0 },
            feedback: { helpful: 0, unhelpful: 0 },
            result_count: 0,
            feedback_count: 0,
            result_score: null,
            feedback_score: null,
            last_observed_at: null,
          }
    ),
  };
}
