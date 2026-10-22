/** Presentation only. The server enforces these same choices before reading or generating. */
export function contextUsability(
  item: {
    excluded?: boolean;
    proofs: {
      root: string;
      support_roots: string[];
      source: string;
      required_sources?: string[];
      sensitive_topics?: string[];
    }[];
  },
  exclusions: { item_id: string; roots: string[] }[],
  sources: string[],
  topics?: string[]
): 'usable' | 'excluded' | 'source_disabled' | 'topic_disabled' {
  const roots = new Set(exclusions.flatMap(exclusion => exclusion.roots));
  if (
    item.excluded ||
    item.proofs.some(proof => [proof.root, ...proof.support_roots].some(root => roots.has(root)))
  )
    return 'excluded';
  if (
    item.proofs.some(
      proof =>
        !sources.includes(proof.source) ||
        proof.required_sources?.some(source => !sources.includes(source))
    )
  )
    return 'source_disabled';
  if (
    topics &&
    item.proofs.some(proof => proof.sensitive_topics?.some(topic => !topics.includes(topic)))
  )
    return 'topic_disabled';
  return 'usable';
}

/** The first reason the server published for which a requested rebuild cannot start. */
export function rebuildBlockedReason(
  settings: {
    producer_enabled: boolean;
    budget_configured: boolean;
    policy: { enabled: boolean; sources: string[] };
  },
  activity?: { obstacle?: string | null }
): string | undefined {
  if (!settings.producer_enabled) return 'discussions.rebuild_producer_blocked';
  if (!settings.budget_configured) return 'discussions.rebuild_budget_blocked';
  if (!settings.policy.enabled) return 'discussions.rebuild_disabled';
  if (settings.policy.sources.length === 0) return 'discussions.rebuild_sources_missing';
  if (activity?.obstacle === 'ceiling_reached') return 'discussions.rebuild_ceiling_blocked';
  if (activity?.obstacle) return 'discussions.rebuild_controls_over_budget';
  return undefined;
}

/** When an item's evidence happened and when LIA last read it; absent dates stay absent. */
export function contextTimeline(item: {
  proofs: { occurred_at: string | null; observed_at: string }[];
}): { start: string | null; end: string | null; updated: string | null } {
  const byTime = (values: string[]) =>
    [...values].sort((left, right) => Date.parse(left) - Date.parse(right));
  const occurred = byTime(
    item.proofs.flatMap(proof => (proof.occurred_at ? [proof.occurred_at] : []))
  );
  const observed = byTime(item.proofs.map(proof => proof.observed_at));
  return {
    start: occurred[0] ?? null,
    end: occurred.at(-1) ?? null,
    updated: observed.at(-1) ?? null,
  };
}
