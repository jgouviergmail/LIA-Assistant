/**
 * How a person wants LIA's generated documents made — two choices on the account.
 *
 * Mirrors the backend vocabulary (`DocumentIllustrations`, `DocumentAnimations`,
 * apps/api/src/core/document_preferences.py), and a backend contract test reads
 * these lists so the two cannot drift. The API publishes the stored choice, else
 * the owner's default, so one option of each is always selected.
 */
export const DOCUMENT_ILLUSTRATIONS = ['auto', 'on_request', 'never'] as const;

export type DocumentIllustrations = (typeof DOCUMENT_ILLUSTRATIONS)[number];

export const DOCUMENT_ANIMATIONS = ['presented', 'always', 'never'] as const;

export type DocumentAnimations = (typeof DOCUMENT_ANIMATIONS)[number];

/** The two profile fields, as the generic profile update names them. */
export type DocumentPreferenceField = 'document_illustrations' | 'document_animations';
