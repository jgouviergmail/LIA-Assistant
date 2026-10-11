import { CHAT_INPUT_MAX_LENGTH } from '@/lib/constants';

/** Compose the shared parts into one draft, clamped at the input cap. */
export function composeShareDraft(
  title: string | null,
  text: string | null,
  url: string | null
): string {
  return [title, text, url]
    .map(part => part?.trim())
    .filter((part): part is string => !!part)
    .join('\n')
    .slice(0, CHAT_INPUT_MAX_LENGTH);
}
