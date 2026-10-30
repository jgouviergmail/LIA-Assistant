/**
 * The address book's labels (`home`, `work`, `mobile`…) in the reader's language.
 *
 * One reading for every surface that shows them — the contact card and the
 * menu of an action bar entry — so a label cannot read « domicile » on one and
 * « home » on the other.
 */

import type { TFunction } from 'i18next';

/**
 * Localize a provider label, keeping the provider's own word as a fallback.
 *
 * `home`, `work`, `spouse`, `anniversary`… are vocabulary, not prose, and the
 * six locales carry the ones we know. Anything else is what the user typed into
 * their address book and is shown untouched.
 *
 * @param t - The reader's translation function.
 * @param label - The provider's label, or null when it stored none.
 * @returns The label to show, or null when there is none.
 */
export function localizeContactLabel(t: TFunction, label: string | null): string | null {
  if (!label) return null;
  const key = label.trim().toLowerCase();
  return t(`relations.contact_label.${key}`, { defaultValue: label });
}
