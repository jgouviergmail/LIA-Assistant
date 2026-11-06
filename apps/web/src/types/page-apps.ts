/**
 * Interactive pages (ADR-370): the payload of a `PAGE_APP` registry item.
 *
 * Composed by `apps/api/src/domains/interactive_pages/document.py`: the policy and
 * the runtime come first, then the page as the model wrote it.
 */

/** What the widget shows first. */
export type PageAppView = 'page' | 'code';

/** Payload stored in the Data Registry for PAGE_APP items. */
export interface PageAppPayload {
  /** The page's own name; empty when it gave itself none. */
  title: string;
  /** The document the frame runs: policy, runtime, page. */
  html_content: string;
  /** Where the page's own bytes start in `html_content`. */
  source_offset: number;
  /** `code` when the person asked for the source. */
  initial_view: PageAppView;
}
