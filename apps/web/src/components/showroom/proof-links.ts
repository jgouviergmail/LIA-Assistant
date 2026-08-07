/**
 * Immutable proof links for the showroom drawer (P0 Task 5).
 *
 * The registry is code-owned: every entry maps a stable id to one
 * repository-relative path — callers can never inject a URL or path. Links
 * resolve through the full 40-hex commit SHA supplied at release-build time
 * (`NEXT_PUBLIC_SHOWROOM_PROOF_SHA`); anything else degrades to honest
 * repository-root links flagged `isImmutable: false`, and the UI must then
 * not claim "exact source".
 */

const REPO_URL = 'https://github.com/jgouviergmail/LIA-Assistant';

const FULL_SHA = /^[0-9a-f]{40}$/;

export type ProofLinkKind = 'product-core' | 'p0-fixture';

export interface ProofLink {
  /** Stable registry id (also the i18n label suffix). */
  id: string;
  /** i18n key for the human label. */
  labelKey: string;
  kind: ProofLinkKind;
  url: string;
}

export interface ShowroomProofLinks {
  isImmutable: boolean;
  links: readonly ProofLink[];
}

/** Code-owned registry: id → { path, kind }. Paths are repo-relative. */
const PROOF_REGISTRY = [
  {
    id: 'routing',
    kind: 'product-core',
    path: 'apps/api/src/domains/agents/nodes/routing.py',
  },
  {
    id: 'planner',
    kind: 'product-core',
    path: 'apps/api/src/domains/agents/nodes/planner_node_v3.py',
  },
  {
    id: 'orchestrator',
    kind: 'product-core',
    path: 'apps/api/src/domains/agents/nodes/task_orchestrator_node.py',
  },
  {
    id: 'hitl',
    kind: 'product-core',
    path: 'apps/api/src/domains/agents/services/hitl_classifier.py',
  },
  {
    id: 'hitl_card',
    kind: 'product-core',
    path: 'apps/web/src/components/chat/HitlActionCard.tsx',
  },
  {
    id: 'trace',
    kind: 'product-core',
    path: 'apps/api/src/domains/agents/services/streaming/trace_capture.py',
  },
  {
    id: 'fixture',
    kind: 'p0-fixture',
    path: 'apps/web/src/components/showroom/missions/overloaded-morning.ts',
  },
  {
    id: 'mission_tests',
    kind: 'p0-fixture',
    path: 'apps/web/src/components/showroom/__tests__/reducer.test.ts',
  },
] as const satisfies readonly {
  id: string;
  kind: ProofLinkKind;
  path: string;
}[];

/** Build the drawer links for a candidate SHA. Never throws. */
export function getShowroomProofLinks(
  sha: string | undefined
): ShowroomProofLinks {
  const isImmutable = typeof sha === 'string' && FULL_SHA.test(sha);
  return {
    isImmutable,
    links: PROOF_REGISTRY.map((entry) => ({
      id: entry.id,
      labelKey: `showroom.proof.links.${entry.id}`,
      kind: entry.kind,
      url: isImmutable ? `${REPO_URL}/blob/${sha}/${entry.path}` : REPO_URL,
    })),
  };
}

/** Read the release-supplied SHA (statically inlined by Next). */
export function getConfiguredProofSha(): string | undefined {
  const raw = process.env.NEXT_PUBLIC_SHOWROOM_PROOF_SHA;
  return raw ? raw : undefined;
}
