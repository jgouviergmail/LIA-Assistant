/**
 * Metadata of the `/maps` pages: the shape every public page of the site
 * declares (`lib/public-page-metadata.ts`), under the section's own name so
 * its four pages read as one.
 */

import { publicPageMetadata, siteUrl } from '@/lib/public-page-metadata';

export { siteUrl };

/** Canonical URL, language alternates, Open Graph and Twitter of one map page. */
export const mapsMetadata = publicPageMetadata;
