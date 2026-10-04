import { cardCompositionWire, isCardActionLabel } from '@/lib/card-actions';
import { CHAT_INPUT_MAX_LENGTH } from '@/lib/constants';
import type { CardCompositionDraft } from '@/types/card-actions';

const PREFIX = '\u001eLIA-card-draft-v1:';

export function encodeCompositionDraft(text: string, composition?: CardCompositionDraft): string {
  const bounded = text.slice(0, CHAT_INPUT_MAX_LENGTH);
  return composition ? PREFIX + JSON.stringify({ ...composition, text: bounded }) : bounded;
}

export function decodeCompositionDraft(stored: string | undefined): {
  text?: string;
  composition?: CardCompositionDraft;
} {
  if (!stored?.startsWith(PREFIX)) return { text: stored };
  try {
    const value: unknown = JSON.parse(stored.slice(PREFIX.length));
    return compositionEnvelope(value);
  } catch {
    return {};
  }
}

function compositionEnvelope(value: unknown): {
  text?: string;
  composition?: CardCompositionDraft;
} {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return {};
  if (!('text' in value) || !('label' in value) || !('selection' in value)) return {};
  if (
    typeof value.text !== 'string' ||
    !value.text.trim() ||
    value.text.length > CHAT_INPUT_MAX_LENGTH
  )
    return {};
  if (!isCardActionLabel(value.label)) return {};
  const selection = cardCompositionWire(value.selection);
  if (!selection) return {};
  const composition = { text: value.text, label: value.label, selection };
  return { text: value.text, composition };
}
