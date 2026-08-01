'use client';

/**
 * useRelations — the personal CRM (N-09 + favorites).
 *
 * Two read hooks over the `/relations` API (overview + one relationship's
 * 360° detail) and the ONE write verb of the CRM: the favorites star.
 * `toggleFavorite` is optimistic — the star flips locally at once, the
 * PUT/DELETE runs behind, and a failure flips it back (the peers-hook
 * doctrine: verbs return `{ ok }`, never leave state to a post-await read).
 */

import { useCallback, useState } from 'react';

import { apiClient } from '@/lib/api-client';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';

/** How the relationship key was matched — honesty over false precision. */
export type IdentityConfidence = 'exact' | 'normalized';

export interface RelationOpenLoop {
  id: string;
  subject: string;
  direction: string;
  due_hint: string | null;
  days_open: number;
}

export interface RelationCall {
  id: string;
  objective: string;
  outcome: string | null;
  summary: string | null;
  created_at: string;
}

export interface RelationMemory {
  id: string;
  content: string;
}

/** Direction of a relayed message, relative to the CRM's owner. */
export type PeerMessageDirection = 'received' | 'sent';

export interface RelationPeerMessage {
  id: string;
  direction: PeerMessageDirection;
  /**
   * Delivered text — null whenever it is not ours to show: a message we SENT
   * left no copy on our side (the relay scrubs it on delivery), and a received
   * one loses its text if the conversation was reset. The exchange itself is
   * never lost, so a count never promises text that cannot be displayed.
   */
  content: string | null;
  occurred_at: string;
}

export interface RelationSummary {
  display_name: string;
  identity_confidence: IdentityConfidence;
  open_loops_count: number;
  calls_count: number;
  /** Messages relayed both ways with this person (peers bridge). */
  peer_messages_count: number;
  last_interaction_at: string | null;
  /** Starred by the user — persisted server-side, survives signal expiry. */
  is_favorite: boolean;
  /** Also a connected LIA user (peers program bridge, read-only). */
  is_peer: boolean;
}

export interface RelationShare {
  /** calendar | task — raw, resolved against the shared label table. */
  domain: string;
  /** availability | details | titles. */
  level: string;
}

/**
 * The LIA connection behind a relationship (peers bridge, read-only).
 *
 * Both directions are stated on purpose: a one-sided view of a two-sided
 * arrangement is misleading. Sharing is granted and revoked in the
 * Connections settings — this panel never writes.
 */
export interface RelationPeerLink {
  connected_since: string | null;
  shared_by_me: RelationShare[];
  shared_with_me: RelationShare[];
}

export interface RelationsOverview {
  relations: RelationSummary[];
  /** Exact number found before the page cap — the list states what it left out. */
  relations_total: number;
}

export interface RelationDetail {
  display_name: string;
  identity_confidence: IdentityConfidence;
  /**
   * Every section ships a PAGE plus its exact TOTAL. The page is capped
   * server-side; the total never is, so the panel can state what it is not
   * showing instead of truncating in silence.
   */
  open_loops: RelationOpenLoop[];
  open_loops_total: number;
  recent_calls: RelationCall[];
  recent_calls_total: number;
  memories: RelationMemory[];
  memories_total: number;
  peer_messages: RelationPeerMessage[];
  peer_messages_total: number;
  /** Present only while an ACCEPTED connection exists. */
  peer_link: RelationPeerLink | null;
  is_favorite: boolean;
  is_peer: boolean;
}

export function useRelationsOverview() {
  // No `initialData`: `data === undefined` is what distinguishes the FIRST
  // load from a refetch, and starring refetches. Seeded with an empty bundle,
  // the two were indistinguishable and the page swapped the whole list for a
  // spinner on every star — wiping the toolbar the user was typing in.
  const { data, loading, error, refetch } = useApiQuery<RelationsOverview>('/relations', {
    componentName: 'RelationsOverview',
  });
  // Optimistic star state: name -> flipped value, cleared on refetch/failure.
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  const put = useApiMutation({ method: 'PUT', componentName: 'RelationsFavorite' });
  const del = useApiMutation({ method: 'DELETE', componentName: 'RelationsFavorite' });

  const toggleFavorite = useCallback(
    async (name: string, nextValue: boolean): Promise<{ ok: boolean }> => {
      setOverrides(prev => ({ ...prev, [name]: nextValue }));
      try {
        const endpoint = `/relations/favorites/${encodeURIComponent(name)}`;
        if (nextValue) {
          await put.mutate(endpoint);
        } else {
          await del.mutate(endpoint);
        }
        // Reconcile: once the fresh overview lands it carries the server
        // truth — dropping the override then lets any LATER server-side
        // change (another tab, another device) show through again.
        void Promise.resolve(refetch()).then(() =>
          setOverrides(prev => {
            const next = { ...prev };
            delete next[name];
            return next;
          })
        );
        return { ok: true };
      } catch {
        // Roll the optimistic flip back — the server said no.
        setOverrides(prev => {
          const next = { ...prev };
          delete next[name];
          return next;
        });
        return { ok: false };
      }
    },
    [put, del, refetch]
  );

  const relations = (data?.relations ?? []).map(relation =>
    relation.display_name in overrides
      ? { ...relation, is_favorite: overrides[relation.display_name] }
      : relation
  );

  return {
    relations,
    // Zero until the first answer — never a claim we cannot back.
    relationsTotal: data?.relations_total ?? 0,
    loading,
    // Monotone: `useApiQuery` only ever sets `data`, so this flips to false at
    // the first answer and stays there. Refreshes are announced, not staged.
    initialLoading: data === undefined && loading,
    error: !!error,
    toggleFavorite,
  };
}

/** Per-section outcome of the provider-backed half of the 360° view. */
export type ContextStatus = 'ok' | 'empty' | 'not_configured' | 'error' | 'no_address';

export interface ContactValue {
  value: string;
  label: string | null;
}

/**
 * The address-book entry, in full.
 *
 * Everything the provider stored — a CRM card showing two fields out of ten is
 * a card the reader stops trusting. Parity is uneven and the payload says so by
 * omission: names, emails, phones, postal addresses, birthday, biography and
 * organization come from all three providers; `relations`, `links`,
 * `important_dates` and `messaging` exist only on Google, and come back empty
 * elsewhere. The photo is deliberately absent — a third party's likeness is an
 * identity decision, not a data-completeness one.
 */
export interface ContactCard {
  display_name: string;
  nickname: string | null;
  organization: string | null;
  occupation: string | null;
  /** `YYYY-MM-DD`, `--MM-DD` when no year was stored, or the provider's text. */
  birthday: string | null;
  biography: string | null;
  emails: ContactValue[];
  phones: ContactValue[];
  addresses: ContactValue[];
  relations: ContactValue[];
  links: ContactValue[];
  /** Same date notation as `birthday`. */
  important_dates: ContactValue[];
  messaging: ContactValue[];
}

export interface ExchangedEmail {
  id: string;
  direction: PeerMessageDirection;
  subject: string;
  occurred_at: string | null;
}

export interface SharedEvent {
  id: string;
  summary: string;
  starts_at: string | null;
  /** Null rather than guessed — a meeting with an invented duration is a claim. */
  ends_at: string | null;
  is_past: boolean;
  /** The person's part in this meeting. */
  role: 'organizer' | 'attendee';
  /** False when the provider exposes no organizer at all (Apple): the split
   * must then read UNKNOWN rather than "organized nothing". */
  organizer_known: boolean;
}

export interface ContextSection {
  status: ContextStatus;
  from_cache: boolean;
  generated_at: string;
  contact: ContactCard | null;
  emails: ExchangedEmail[];
  events: SharedEvent[];
}

export interface RelationContext {
  contact: ContextSection;
  emails: ContextSection;
  events: ContextSection;
  /** How many addresses of the card the mail/event lookups actually used. */
  addresses_used: number;
  /** Half-window in days scanned for shared events — stated, never a total. */
  window_days: number;
  /** How far back mail was searched — wider than the event window. */
  email_window_days: number;
}

/**
 * The provider-backed sections of one relationship (Bloc C).
 *
 * A SEPARATE query from the 360° detail on purpose: it reaches the connectors,
 * so it is slower and fails differently. The detail must render immediately
 * and these sections fill in behind it — never the reverse.
 */
export function useRelationContext(name: string | null) {
  const endpoint = name ? `/relations/${encodeURIComponent(name)}/context` : '';
  const { data, loading, error, setData } = useApiQuery<RelationContext>(endpoint, {
    componentName: 'RelationContext',
    enabled: !!name,
  });
  // WHICH sections are being re-read, not merely "something is". Three
  // spinners turning because the reader pressed one of them claims work that
  // is not happening.
  const [refreshing, setRefreshing] = useState<string[]>([]);

  /**
   * Ask the server to look again, for the given sections.
   *
   * A ONE-SHOT imperative read, deliberately not part of the query key: with
   * `?refresh=` baked into the endpoint, every later refetch of that mounted
   * panel would keep bypassing the cache — a control meant to be pressed once
   * would silently become "never use the cache again", and each press would
   * spend provider quota for good.
   */
  const refreshSections = useCallback(
    async (sections: string[]) => {
      if (!endpoint || sections.length === 0) return;
      setRefreshing(sections);
      try {
        const fresh = await apiClient.get<RelationContext>(
          `${endpoint}?refresh=${sections.join(',')}`
        );
        setData(fresh);
      } catch {
        // A failed refresh leaves the current answer standing: replacing it
        // with nothing would turn "could not look again" into "found nothing".
      } finally {
        setRefreshing([]);
      }
    },
    [endpoint, setData]
  );

  return {
    context: data ?? null,
    loading: loading || refreshing.length > 0,
    /** The sections currently being re-read — never "something, somewhere". */
    refreshing,
    error: !!error,
    refreshSections,
  };
}

export function useRelationDetail(name: string | null) {
  const { data, loading, error } = useApiQuery<RelationDetail>(
    name ? `/relations/${encodeURIComponent(name)}` : '',
    { componentName: 'RelationDetail', enabled: !!name }
  );
  return { detail: data ?? null, loading, error: !!error };
}

// =============================================================================
// The 360° scope — what a "point 360°" is allowed to read
// =============================================================================

/** A source the 360° may draw from — mirrors the backend enum exactly. */
export const OVERVIEW_SECTIONS = [
  'contact',
  'open_loops',
  'calls',
  'memories',
  'peer_messages',
  'emails',
  'events',
] as const;
export type OverviewSection = (typeof OVERVIEW_SECTIONS)[number];

export const OVERVIEW_DIRECTIONS = ['received', 'sent'] as const;
export type OverviewDirection = (typeof OVERVIEW_DIRECTIONS)[number];

export const OVERVIEW_ROLES = ['attendee', 'organizer'] as const;
export type OverviewRole = (typeof OVERVIEW_ROLES)[number];

/**
 * The scope one 360° point applies.
 *
 * Every field is a set of INCLUSIONS: an empty list means "not part of my
 * 360°", never "everything". Silence must not be generous here — a scope that
 * grew when the reader cleared it would spend provider quota they just asked
 * to save.
 */
export interface RelationOverviewScope {
  sections: OverviewSection[];
  directions: OverviewDirection[];
  roles: OverviewRole[];
  max_items: number;
}

/**
 * Read the stored scope, and write it back before opening the chat.
 *
 * The 360° request leaves the browser as a chat `?intent=`, which carries text
 * and nothing else. Letting the planner infer the scope from that prose would
 * make the reader's selection a HINT; saving it server-side FIRST is what makes
 * it a guarantee. `save` therefore resolves before the caller navigates — a
 * fire-and-forget write would race the tool that reads it.
 */
export function useOverviewScope() {
  const { data, loading, setData } = useApiQuery<RelationOverviewScope>(
    '/relations/overview-scope',
    { componentName: 'RelationOverviewScope' }
  );
  const { mutate, loading: saving } = useApiMutation<RelationOverviewScope, RelationOverviewScope>({
    method: 'PUT',
    componentName: 'RelationOverviewScope',
  });

  const save = useCallback(
    async (scope: RelationOverviewScope): Promise<boolean> => {
      const saved = await mutate('/relations/overview-scope', scope);
      if (!saved) return false;
      // The server echoes what it stored; adopting THAT rather than what was
      // sent means a value it clamped is what the panel shows next time.
      setData(saved);
      return true;
    },
    [mutate, setData]
  );

  return { scope: data ?? null, loading, saving, save };
}
