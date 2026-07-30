# Peer Connections — Lot 2 (Discovery & Management UI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (INLINE — no
> subagents, standing user rule). **Git rule: NEVER commit/push — checkpoints log the
> proposed message and continue.**

**Goal:** The « Connexions » settings section (features tab): discovery opt-in + exact-name
search, request lifecycle, per-connection shares in BOTH directions, blocks, transparency
log — flag-gated, fully localized (6), accessible, responsive, hermetically e2e-tested.

**Architecture:** One `SettingsSection` shell + five focused subcomponents under
`components/settings/peers/` (CC/size ratchets). One hook file wrapping the Lot 1 REST
surface. Gating rides `/api/v1/config` features (OpenLoopsSection precedent —
`settings-search.ts:154-160`, `page.tsx:169-176`). Master spec §10.

**Tech Stack:** Next.js 16 App Router, React 19, TS strict, shadcn-ui, react-i18next,
vitest, Playwright+axe (hermetic package `apps/web/e2e`).

## Global Constraints

- Frontend CLAUDE.md in full: BFF auth (no fetch — `useApiQuery`/`useApiMutation` only),
  native semantics + stable translated accessible names + keyboard equivalence, ratchets
  shrink-only, no `as any`/double assertions, timers cleaned, `AbortSignal.timeout()`.
- i18n strict parity ×6 (en reference; zh `_one` duplication when plurals appear).
- Error codes from Lot 1 (`peers_self_request`, `peers_context_message_too_long`,
  `peers_already_connected`, `peers_not_pending`, `peers_not_connected`,
  `peers_invalid_share_level`, `peers_self_block`, `peers_conflict`) map client-side to
  localized toasts — one mapping table, unknown codes fall back to a generic message.
- Statuses/domains/levels arrive as strings (`pending|accepted`, `calendar|task`,
  `availability|details|titles`) — render via i18n labels, never raw.
- Responsive: the section must lay out cleanly at 360 px (mobile) and desktop; no
  horizontal overflow (existing e2e overflow guard precedent).
- Validation runs in the containers (`lia-web-dev`), never a local server; container does
  NOT hot-reload host edits — `docker restart lia-web-dev` before any browser proof.

---

### Task 1: Expose `peers_enabled` to the client (`/api/v1/config`)

**Files:** Modify `apps/api/src/api/v1/routes.py:235-238` block (add
`"peers_enabled": getattr(settings, "peers_enabled", False),`), modify
`apps/web/src/hooks/useAppConfig.ts` (`peers_enabled?: boolean` in `features`).
**Test:** extend the existing config-route test (grep `channels_enabled` under
`apps/api/tests/` for the file) asserting the key is present and False by default; run it.
Checkpoint message: `feat(peers): expose peers_enabled instance flag (Lot 2.1)`.

### Task 2: Hook `usePeerConnections`

**Files:** Create `apps/web/src/hooks/usePeerConnections.ts`; Test
`apps/web/src/hooks/__tests__/usePeerConnections.test.ts` (imitate an existing hook test).

**Interfaces (produced, consumed by Tasks 3-4):**

```ts
export interface DiscoveryMatch { peer_id: string; display_name: string; email_hint: string }
export interface ShareItem { domain: 'calendar' | 'task'; level: 'availability' | 'details' | 'titles' }
export interface ConnectionView {
  id: string; peer_id: string; peer_display_name: string; peer_email_hint: string;
  status: 'pending' | 'accepted'; direction: 'incoming' | 'outgoing' | null;
  requested_at: string; responded_at: string | null; context_message: string | null;
  my_shares: ShareItem[]; their_shares: ShareItem[];
}
export interface BlockView { blocked_id: string; blocked_display_name: string | null; created_at: string }
export interface AccessLogEntry { accessor_display_name: string; domain: string; tool_name: string; created_at: string }
export function usePeerConnections(enabled?: boolean): {
  discoveryEnabled: boolean | null; setDiscovery(v: boolean): Promise<boolean>;
  search(fullName: string): Promise<DiscoveryMatch[] | undefined>;   // POST /peers/discovery/search
  requests: ConnectionView[]; connections: ConnectionView[]; blocks: BlockView[];
  accessLog: AccessLogEntry[]; loading: boolean; mutating: boolean;
  sendRequest(peerId: string, contextMessage?: string): Promise<boolean>;
  respond(connectionId: string, accept: boolean): Promise<boolean>;
  removeConnection(connectionId: string): Promise<boolean>;
  setShare(connectionId: string, domain: string, level: string | null): Promise<boolean>;
  block(peerId: string): Promise<boolean>; unblock(peerId: string): Promise<boolean>;
  refetchAll(): void;
}
```

Implementation: 4 `useApiQuery` (me, requests, connections, blocks — access-log fetched
with the others), mutations via one `useApiMutation` per verb-shape; after every
state-changing success, refetch the affected queries (no manual cache surgery). All wrapped
`useCallback`. Errors: return false and surface the API error code to the caller via a
`lastErrorCode` ref-state consumed by the components' toast mapping.
TDD: hook tests mock `useApiQuery`/`useApiMutation` modules; assert URLs, payloads,
refetch-on-success, false-on-failure. Checkpoint: `feat(peers): usePeerConnections hook (Lot 2.2)`.

### Task 3: Components (decomposed)

**Files (create):**
- `apps/web/src/components/settings/PeerConnectionsSettings.tsx` — shell:
  `<SettingsSection value="peer-connections" …>` (BaseSettingsProps, collapsible), renders
  nothing when the hook is disabled; composes the five blocks below; discovery master
  toggle at top (Switch + Label pattern, `HeartbeatSettings.tsx:64-79` model).
- `apps/web/src/components/settings/peers/PeerDiscoveryBlock.tsx` — exact-name search
  `<form>` (native submit, labeled input, min 1 char), results list with display name +
  pinned `email_hint`, per-result « Demander la connexion » button + optional context
  message textarea (maxLength from a shared constant 500), request → toast.
- `apps/web/src/components/settings/peers/PeerRequestsBlock.tsx` — incoming (accept /
  decline / block buttons, context message rendered as plain quoted text) and outgoing
  (badge + cancel-not-in-v1: outgoing shows state only) lists; empty states.
- `apps/web/src/components/settings/peers/PeerConnectionCard.tsx` — one accepted
  connection: identity (name + email hint always visible — spec §12.8), **my shares
  editable** (calendar: none/availability/details Select; task: none/titles Switch),
  **their shares read-only badges** (explicit both-directions requirement), remove (with
  `window.confirm`-free inline confirm pattern — a two-step button), block.
- `apps/web/src/components/settings/peers/PeerBlocksBlock.tsx` — my blocks + unblock.
- `apps/web/src/components/settings/peers/PeerAccessLogBlock.tsx` — transparency list
  ("{name} a consulté {domaine} — {date}"), localized dates in viewer timezone.
- Shared: `apps/web/src/components/settings/peers/peers-error-messages.ts` — the
  code→i18n-key mapping table + `toastPeersError(t, code)` helper.

**Tests:** one behavioral vitest file per block under
`components/settings/peers/__tests__/` + one for the shell: render with mocked hook,
assert accessible names (role/name queries), keyboard activation of accept/decline,
disabled states while mutating, empty/loading/error states, share-select changes call
`setShare` with the right (domain, level|null), toast on each mapped error code, both
share directions rendered. No snapshots as sole oracle.
Checkpoint: `feat(peers): settings section components (Lot 2.3)`.

### Task 4: Registries + page wiring + search

**Files:** Modify `apps/web/src/lib/settings-sections.ts` (features tab entry
`'peer-connections'` → accordionValue `peer-connections`, declaredIn
`components/settings/PeerConnectionsSettings.tsx`, placed in page order), modify
`apps/web/src/lib/settings-search.ts` (entry with
`gate: { kind: 'instanceFlag', flag: 'peersEnabled' }`, group `features`), modify
`apps/web/src/app/[lng]/dashboard/settings/page.tsx` (import + render in BOTH layout
variants next to the other features sections + add `peersEnabled:
!!config?.features?.peers_enabled` to the flags memo `page.tsx:165-176`).
**Tests:** run the existing coverage/consistency tests
(`settings-sections-coverage.test.ts`, search tests) and satisfy them — they are the
oracle; fix what they flag, never their allowlists.
Checkpoint: `feat(peers): section registered, searchable, flag-gated (Lot 2.4)`.

### Task 5: i18n ×6

**Files:** `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — namespace
`settings.peers.*` (title, description, discovery toggle + hint incl. « sans nom complet,
vous êtes introuvable », search, results, request, context placeholder, incoming/outgoing,
accept/decline/remove/block/unblock, shares titles both directions, level labels, access
log, empty states, toasts success) + `settings_search.keywords.peer-connections` + the 8
error-code messages. Title per A5: en "Connections", fr « Connexions », de „Verbindungen“,
es «Conexiones», it «Connessioni», zh 「用户互联」. Full-quality translations (no
truncation trap), parity-checked by the pre-commit diff — run the parity check via
`task lint:i18n`.
Checkpoint: `feat(peers): 6-locale strings (Lot 2.5)`.

### Task 6: Hermetic e2e journey + a11y + responsive

**Files:** Create `apps/web/e2e/smoke/peer-connections.spec.ts` (imitate an existing smoke
spec + fixtures): mock `/api/v1/config` (peers_enabled true), auth, and the /peers
endpoints; journey = open settings → deep link `?section=peer-connections` expands the
section → toggle discovery → search returns one match (assert email hint visible) →
send request → incoming request (mock swap) → accept → connection card shows BOTH share
directions → set calendar share to availability → remove connection. Axe scan on the
expanded section (a11y package pattern); mobile viewport (390×844) re-run of the render
steps asserting no horizontal overflow (existing overflow-guard precedent).
Run: from `apps/web/e2e` per its README (hermetic — no real backend).
Checkpoint: `test(peers): hermetic e2e journey (Lot 2.6)`.

### Task 7: Lot gate + review

1. `task lint:frontend` (includes the 3 shrink-only ratchets + non-incremental tsc)
2. `cd apps/web && pnpm exec tsc --noEmit --incremental false`
3. `task test:frontend:coverage` — **raise the per-file thresholds if headroom ≥2 pts**
   (standing user directive: ratchets up after improvement)
4. e2e package run; `task lint` (full, i18n parity + docs)
5. Adversarial self-review of the diff (states, races on rapid toggles, aria, focus
   return after accept/decline removes a list item, timezone rendering)
6. Report evidence + proposed commit `feat(peers): discovery & management UI (Lot 2)`.
