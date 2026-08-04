/**
 * How a capability's state is put into words — once, for both surfaces.
 *
 * The chart and the list must never describe the same capability differently,
 * and there is one rule they both have to obey: **a count shown to the user is
 * exact, or it does not exist** (ADR-185). `personality` and `proactivity` are
 * switches, not collections — they carry no tally at all, and `detail ?? 0`
 * turned that absence into the claim "Active — 0 item(s)", which reads as an
 * empty capability rather than as one with nothing to count.
 *
 * So: a tally when there is one, and plain "Active" when there is not.
 */

import type { TFunction } from 'i18next';

import type { CapabilityNode } from '@/hooks/useCapabilities';

/** The state line under a capability's name, in the list. */
export function activeLabel(t: TFunction, node: CapabilityNode): string {
  if (!node.active) return t('capabilities.state_dormant');
  return node.detail === null
    ? t('capabilities.state_active_plain')
    : t('capabilities.state_active', { count: node.detail });
}

/** The accessible name of a star, which states subject AND state. */
export function nodeName(t: TFunction, node: CapabilityNode, label: string): string {
  if (!node.active) return t('capabilities.node_dormant', { name: label });
  return node.detail === null
    ? t('capabilities.node_active_plain', { name: label })
    : t('capabilities.node_active', { name: label, count: node.detail });
}
