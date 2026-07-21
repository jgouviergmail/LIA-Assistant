/**
 * Rehydrate interactive widgets from conversation history.
 *
 * The registry that resolves a widget sentinel (`data-registry-id`) is filled
 * exclusively by the live SSE `registry_update` — nothing ever rebuilt it. A
 * conversation opened from history therefore rendered "Failed to load skill
 * widget" for every skill frame and MCP app: the message kept its sentinel, but
 * the payload it pointed at only ever existed in the browser that received the
 * stream. Measured on the real production message: two grey error boxes, zero
 * iframes.
 *
 * The backend now persists frame-rendering widgets on the message
 * (`message_metadata.widgets`, in the exact shape the SSE side sends), so
 * rehydration is a pure derivation over the loaded messages — no fetch, no
 * effect, no extra state.
 */

import type { Message, RegistryItem } from '@/types/chat';

/** Shape the backend persists under `message_metadata.widgets`. */
type PersistedWidgets = Record<string, RegistryItem>;

/**
 * Collect every widget persisted on the given messages.
 *
 * @param messages - Messages currently displayed (history + live).
 * @returns A registry map, empty when no message carries a widget.
 */
export function collectHistoryWidgets(messages: readonly Message[]): PersistedWidgets {
  const collected: PersistedWidgets = {};
  for (const message of messages) {
    const widgets = message.metadata?.widgets as PersistedWidgets | undefined;
    if (!widgets || typeof widgets !== 'object') continue;
    for (const [id, item] of Object.entries(widgets)) {
      if (item && typeof item === 'object') collected[id] = item;
    }
  }
  return collected;
}

/**
 * Registry to hand the widget components: history first, live stream on top.
 *
 * The live registry wins on conflict — it is the current turn's truth, and a
 * persisted copy of the same id can only be older.
 *
 * @param liveRegistry - Registry accumulated from SSE this session.
 * @param messages - Messages currently displayed.
 * @returns The merged registry. Returns `liveRegistry` unchanged (same object)
 *   when history contributes nothing, so React sees no new reference.
 */
export function mergeRegistryWithHistory(
  liveRegistry: Record<string, RegistryItem>,
  messages: readonly Message[]
): Record<string, RegistryItem> {
  const fromHistory = collectHistoryWidgets(messages);
  if (Object.keys(fromHistory).length === 0) return liveRegistry;
  return { ...fromHistory, ...liveRegistry };
}
