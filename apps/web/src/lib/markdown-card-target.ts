/** Presentation-only card identification; signed authority stays opaque. */
import type { Element } from 'hast';
import { cardTargetKind, type CardTargetKind } from './workbench/card-target';

const FAMILIES: Record<string, CardTargetKind> = {
  'lia-email': 'email',
  'lia-event': 'event',
  'lia-calendar': 'calendar',
  'lia-contact': 'contact',
  'lia-task': 'task',
  'lia-file': 'file',
  'lia-hues': 'hue_light',
};
const TITLES = new Set(['lia-email__subject', 'lia-card-top__title', 'lia-card__title-link']);
export interface CardTargetPresentation {
  kind: CardTargetKind | null;
  token: string | null;
  sourceHrefs: ReadonlySet<string>;
  hasTitleLink: boolean;
}

function classes(node: Element): string[] {
  const value = node.properties.className;
  return Array.isArray(value)
    ? value.map(String)
    : typeof value === 'string'
      ? value.split(/\s+/)
      : [];
}

/** Only the wrapper carries opaque navigation metadata, never a nested card. */
function bindingMetadata(node: Element | undefined, binding: boolean) {
  if (!binding) return { kind: null, token: null };
  const token = node?.properties.dataCardTarget;
  return {
    kind: cardTargetKind(node?.properties.dataCardKind),
    token: typeof token === 'string' && token ? token : null,
  };
}

/** A sender's mailto title remains contextual and cannot replace the item opener. */
function sourceTitleHref(node: Element, names: string[]): string | null {
  const href = node.properties.href;
  if (node.tagName !== 'a' || !names.some(name => TITLES.has(name))) return null;
  return typeof href === 'string' && !/^(?:mailto|tel):/i.test(href) ? href : null;
}

export function cardTargetPresentation(
  node: Element | undefined,
  binding: boolean
): CardTargetPresentation {
  const result: CardTargetPresentation = {
    ...bindingMetadata(node, binding),
    sourceHrefs: new Set(),
    hasTitleLink: false,
  };
  const hrefs = new Set<string>();
  const pending = node ? [node] : [];
  while (pending.length) {
    const current = pending.pop()!;
    const names = classes(current);
    if (current !== node && names.includes('lia-card-binding')) continue;
    result.kind ??= names.map(name => FAMILIES[name]).find(Boolean) ?? null;
    const href = sourceTitleHref(current, names);
    if (href !== null) {
      result.hasTitleLink = true;
      hrefs.add(href);
    }
    for (const child of current.children) if (child.type === 'element') pending.push(child);
  }
  result.sourceHrefs = hrefs;
  return result;
}

export function isCardSourceLink(
  node: Element | undefined,
  presentation: CardTargetPresentation
): boolean {
  if (!node || !presentation.kind) return false;
  const href = node.properties.href;
  if (typeof href === 'string' && /^(?:mailto|tel):/i.test(href)) return false;
  const names = classes(node);
  return (
    node.properties.dataCardOpen === 'true' ||
    node.properties.dataCardOpen === true ||
    names.some(name => TITLES.has(name) || name === 'lia-file__preview') ||
    (names.includes('lia-action-btn') &&
      typeof href === 'string' &&
      presentation.sourceHrefs.has(href))
  );
}
