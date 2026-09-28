/**
 * What LIA produced, as the gallery reads it (ADR-279).
 *
 * The wire shapes mirror `domains/attachments/schemas.py` exactly: the backend
 * guard that reads this file (`tests/unit/domains/attachments/
 * test_gallery_wire_shape.py`) fails on a drift, and a field spelled two
 * ways is how a card behaves differently live and after a reload (the
 * `GeneratedImage` lesson).
 */

/** Which gallery. The API resolves each to one `origin`; `upload` is not one. */
export type GeneratedAssetFamily = 'images' | 'documents' | 'screenshots';

/** How a gallery may be ordered — the API refuses anything else. */
export type GeneratedAssetSort = 'created_desc' | 'created_asc' | 'expires_asc' | 'name_asc';

/** One file LIA produced. */
export interface GeneratedAsset {
  id: string;
  /** What it is called for a person; null falls back to `original_filename`. */
  title: string | null;
  original_filename: string;
  mime_type: string;
  file_size: number;
  origin: string;
  /** Where it was produced; null when that conversation is gone or there was none. */
  conversation_id: string | null;
  created_at: string;
  /** When the cleanup removes it — stated, never implied. `null`: the person
   *  kept it from the gallery, and no cleanup will (ADR-319). */
  expires_at: string | null;
  /** Who shared this image, for a copy a connection sent (ADR-316); null otherwise. */
  shared_by_name: string | null;
}

/** What the account keeps past the deadline, against what it may (ADR-319). */
export interface GeneratedAssetKeepUsage {
  /** EXACT count of the account's kept files, every family. */
  kept_files: number;
  /** EXACT bytes those files hold. */
  kept_bytes: number;
  /** Most files the account may keep — 0 means keeping is off. */
  max_files: number;
  /** Most bytes the account may keep. */
  max_bytes: number;
}

/** One page, its EXACT total (ADR-185) and the bounds the API enforces. */
export interface GeneratedAssetList {
  items: GeneratedAsset[];
  total: number;
  total_bytes: number;
  limit: number;
  offset: number;
  /** Largest page the API serves — published because it is enforced (ADR-184). */
  max_limit: number;
  /** The keeping ceilings, published with the page because they are enforced. */
  keep: GeneratedAssetKeepUsage;
}

/** What the reader narrowed a gallery to. */
export interface GeneratedAssetFilters {
  q?: string;
  /** ISO-8601 instants; an unset bound costs no query parameter. */
  createdAfter?: string;
  createdBefore?: string;
  expiresBefore?: string;
  sort?: GeneratedAssetSort;
}

/** What a bulk delete actually removed, and what it did not. */
export interface GeneratedAssetsDeleteResult {
  deleted: string[];
  skipped: string[];
}

/** What a keep or a release actually changed, and the usage after it. */
export interface GeneratedAssetsKeepResult {
  updated: string[];
  skipped: string[];
  keep: GeneratedAssetKeepUsage;
}
