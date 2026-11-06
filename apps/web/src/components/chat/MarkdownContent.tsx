import React, { useState, useMemo, memo, lazy, Suspense } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import type { PluggableList } from 'unified';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize from 'rehype-sanitize';
import rehypeKatex from 'rehype-katex';
import { markdownSanitizeSchema } from '@/lib/markdown-sanitize-schema';
import rehypeRestoreDollars from '@/lib/markdown-dollars';
import { prepareMarkdownSource } from '@/lib/markdown-source';
import remarkLiteralHtml from '@/lib/remark-literal-html';
import rehypeMathInText from '@/lib/rehype-math-in-text';
import rehypeSearchHighlight from '@/lib/rehype-search-highlight';
import rehypeTableLabels from '@/lib/rehype-table-labels';
import rehypeContactPhotos from '@/lib/rehype-contact-photos';
import rehypePhoneText from '@/lib/rehype-phone-text';
import { useTranslation } from 'react-i18next';
import { cn, GOOGLE_IMAGE_DOMAINS, proxyGoogleImageUrl } from '@/lib/utils';
import { ImageLightbox } from '@/components/ui/image-lightbox';
import { MarkdownCardImage } from './markdown-card-image';
import { MarkdownCardDetails } from './markdown-card-details';
import { useMarkdownImageLoad } from './use-markdown-image-load';
import { apiImageProps } from '@/lib/utils/api-resource-url';
import { codeBlockOf } from '@/lib/markdown-code-block';
import { MarkdownCardButton } from './markdown-card-actions';
import { MarkdownDiv } from './markdown-presentation-div';
import { MarkdownClassificationSpan } from './ClassificationBadges';
import {
  MarkdownTable,
  MarkdownTableBody,
  MarkdownTableCell,
  MarkdownTableHead,
  MarkdownTableHeaderCell,
  MarkdownTableRow,
} from '@/components/chat/markdown-table';

// Code block with syntax highlighting — lazy loaded to keep Prism out of main bundle
const CodeBlock = lazy(() =>
  import('@/components/chat/CodeBlock').then(m => ({ default: m.CodeBlock }))
);

/**
 * MarkdownContent Component
 *
 * Renders Markdown content with custom styling adapted to the application's design system.
 * Follows Tailwind CSS 4.0 best practices and supports dark mode.
 *
 * Features:
 * - GitHub Flavored Markdown (GFM) support
 * - Custom component styling for headings, lists, links, code blocks
 * - Responsive typography
 * - Dark mode support via Tailwind's dark: variant
 * - Professional appearance aligned with the app's OKLCH color system
 */

/**
 * Resolve a markdown image source: where it lives, and what it needs to load.
 *
 * A markdown image can be an API resource (`/api/v1/connectors/...` for a place
 * photo, a static map, a Drive thumbnail), which must be resolved against the
 * API origin AND asked for with credentials — an embedded cross-origin image is
 * fetched without them under `COEP: credentialless`, and the API answers 401.
 *
 * @param srcProp - The `src` React hands the component (typed to allow a Blob).
 * @returns The resolved source and its credentials, both absent when there is
 *   no usable string source.
 */
function resolveMarkdownImage(srcProp: React.ImgHTMLAttributes<HTMLImageElement>['src']): {
  src?: string;
  crossOrigin?: 'use-credentials';
} {
  if (typeof srcProp !== 'string') return {};
  // All Google photos need the proxy, including structured card images. The
  // preload and rendered image must use this same authenticated request.
  return apiImageProps(proxyGoogleImageUrl(srcProp) || srcProp);
}

/**
 * MarkdownImage - Renders images in markdown with smart detection
 *
 * Detects profile photos (Google Contacts) and uses Avatar component
 * for enhanced styling (rounded, glassmorphism, hover effects).
 * Falls back to standard image rendering for non-profile images.
 * Click to open in lightbox at 3x size.
 *
 * NOTE: This is for standalone markdown images (![](url)).
 *
 * LIA Component System: Images with 'lia-*' classes are part of the
 * LIA design system and must be rendered as-is to preserve flexbox
 * layouts and component styling. This is critical for contact cards,
 * file items, and other structured components.
 *
 * Issue #64: Uses global image cache to prevent scintillation during streaming.
 */
const MarkdownImage = memo(
  ({ src: srcProp, alt, className, loading }: React.ImgHTMLAttributes<HTMLImageElement>) => {
    const [isLightboxOpen, setIsLightboxOpen] = useState(false);
    const { t } = useTranslation();
    const { src, crossOrigin } = resolveMarkdownImage(srcProp);
    const isLiaComponent = className?.startsWith('lia-');
    const {
      loaded,
      failed,
      onError,
      onLoad: handleLoad,
    } = useMarkdownImageLoad(src ?? '', crossOrigin, !isLiaComponent);

    if (!src) return null;

    // =========================================================================
    // LIA COMPONENT SYSTEM - Preserve structured component images
    // =========================================================================
    // Images with 'lia-*' classes are part of the LIA design system (avatars,
    // thumbnails, etc.). They must be rendered as-is to preserve:
    // - Flexbox layouts in card headers (.lia-contact__header, etc.)
    // - Component-specific sizing (.lia-avatar--sm, .lia-avatar--md)
    // - Design system consistency
    //
    // Without this check, transformations below would wrap LIA images in
    // full-width blocks, breaking flexbox layouts and changing CSS classes.
    // =========================================================================
    if (isLiaComponent) {
      return (
        <MarkdownCardImage
          src={src}
          crossOrigin={crossOrigin}
          alt={alt}
          className={className}
          loading={loading}
          loaded={loaded}
          failed={failed}
          onLoad={handleLoad}
          onError={onError}
        />
      );
    }

    // Detect if this is a profile photo (from Google Contacts API or explicit alt text)
    // Exclude place photos (/api/v1/connectors/google-places/photo path) - they use proxy endpoint
    const isPlacePhoto = src.includes('/connectors/google-places/photo');
    const isProfilePhoto =
      !isPlacePhoto &&
      (() => {
        try {
          // Classification uses the original URL; `src` is already proxied.
          const parsed = new URL(typeof srcProp === 'string' ? srcProp : src);
          return GOOGLE_IMAGE_DOMAINS.includes(parsed.hostname);
        } catch {
          return alt?.toLowerCase().includes('photo') ?? false;
        }
      })();

    // Place photo - clickable with lightbox (2x zoom: 200px -> 400px)
    if (isPlacePhoto) {
      return (
        <>
          {/* Real action -> native button around the image (audit F013). */}
          <button
            type="button"
            onClick={() => setIsLightboxOpen(true)}
            aria-label={t('common.expand_image')}
            className="inline-block align-top p-0 border-0 bg-transparent cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={src}
              crossOrigin={crossOrigin}
              alt={alt || 'Photo du lieu'}
              className="place-photo"
              referrerPolicy="no-referrer"
              style={{
                opacity: loaded ? 1 : 0,
                transition: loaded
                  ? 'transform 0.2s ease, box-shadow 0.2s ease'
                  : 'opacity 0.15s ease-in',
              }}
              onLoad={handleLoad}
            />
          </button>
          {typeof document !== 'undefined' &&
            createPortal(
              <ImageLightbox
                src={src}
                crossOrigin={crossOrigin}
                alt={alt || 'Photo du lieu'}
                isOpen={isLightboxOpen}
                onClose={() => setIsLightboxOpen(false)}
                minWidth={400}
              />,
              document.body
            )}
        </>
      );
    }

    // Profile photo (Google Contacts) - Single contact detail view
    // Uses contact-photo CSS class for consistent styling with vignette effect
    if (isProfilePhoto) {
      return (
        <>
          <span
            style={{
              display: 'block',
            }}
            className="flex justify-center my-4 w-full"
          >
            {/* Real action -> native button around the image (audit F013). */}
            <button
              type="button"
              onClick={() => setIsLightboxOpen(true)}
              aria-label={t('common.expand_image')}
              className="inline-block align-top p-0 border-0 bg-transparent cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                crossOrigin={crossOrigin}
                alt={alt || 'Photo de profil'}
                className="contact-photo"
                referrerPolicy="no-referrer"
                style={{
                  opacity: loaded ? 1 : 0,
                }}
                onLoad={handleLoad}
              />
            </button>
          </span>
          {typeof document !== 'undefined' &&
            createPortal(
              <ImageLightbox
                src={src}
                crossOrigin={crossOrigin}
                alt={alt || 'Photo de profil'}
                isOpen={isLightboxOpen}
                onClose={() => setIsLightboxOpen(false)}
                minWidth={250}
              />,
              document.body
            )}
        </>
      );
    }

    // Default image rendering for non-profile images (screenshots, diagrams, etc.)
    return (
      <span className="block relative w-full max-w-[150px] my-3 mx-auto">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          crossOrigin={crossOrigin}
          alt={alt || 'Image'}
          className="w-full h-full object-cover rounded-lg shadow-md"
          referrerPolicy="no-referrer"
          style={{
            opacity: loaded ? 1 : 0,
            transition: 'opacity 0.15s ease-in',
          }}
          loading="lazy"
          onLoad={handleLoad}
        />
      </span>
    );
  }
);
MarkdownImage.displayName = 'MarkdownImage';

interface MarkdownContentProps {
  content: string;
  isUser?: boolean;
  className?: string;
  /**
   * History-search term to highlight in the rendered output (QW-2). Matches
   * are accent/case-insensitive and wrapped in fixed-class `<mark>` elements
   * by the post-sanitize `rehype-search-highlight` plugin.
   */
  searchHighlight?: string;
}

/**
 * MarkdownContent component - Memoized to prevent unnecessary re-renders during streaming.
 * Issue #64: Without memo, images would flash on every token because React recreates the DOM.
 * The memo comparison uses default shallow equality which is sufficient since content changes
 * trigger the necessary re-render anyway.
 */
// singleDollarTextMath: false — remark-math never touches single `$` (so
// currency is never swallowed); all `$…$`/`$$…$$` rendering is owned by
// rehypeMathInText at the hast level, which — unlike remark-math — also sees
// math inside the raw HTML the assistant emits. remark-math still handles
// ```math fences and markdown `$$`.
const ANSWER_REMARK_PLUGINS: PluggableList = [
  remarkGfm,
  [remarkMath, { singleDollarTextMath: false }],
];

// A person's message keeps what looks like a tag as text; the rest is the same
// Markdown. Module-level so the identity is stable across streaming renders.
const USER_REMARK_PLUGINS: PluggableList = [remarkLiteralHtml, ...ANSWER_REMARK_PLUGINS];

export const MarkdownContent: React.FC<MarkdownContentProps> = memo(
  ({ content, isUser = false, className, searchHighlight }) => {
    // Search highlight (QW-2): appended LAST so KaTeX output is already in
    // place (the plugin skips it). Memoized on the term — an empty term keeps
    // the exact base pipeline (no per-render plugin churn while streaming).
    const searchTerm = searchHighlight?.trim() ?? '';
    const rehypePlugins = useMemo(() => {
      const base: PluggableList = [
        rehypeRaw,
        [rehypeSanitize, markdownSanitizeSchema],
        rehypeMathInText,
        // A referenced dollar is a literal one (`lib/markdown-dollars.ts`):
        // written back once the math step ran, before KaTeX renders.
        rehypeRestoreDollars,
        rehypeKatex,
        // Visible text only: formatting the raw HTML corrupts tel: links and
        // the opaque JSON attributes read by native widgets such as Position.
        rehypePhoneText,
        // Names every body cell after its column, for the stacked-card layout
        // of an overflowing table on a narrow screen (B2). After KaTeX, so a
        // formula in a header reads as its source; before the search marks.
        rehypeTableLabels,
        // Saved contact photos predate the explicit structured-image class.
        // Restore only that fixed class on the already-sanitized AST.
        rehypeContactPhotos,
      ];
      if (searchTerm) base.push([rehypeSearchHighlight, { query: searchTerm }]);
      return base;
    }, [searchTerm]);

    // The string repairs of LIA's own HTML, and the math notations of both
    // authors: `lib/markdown-source.ts`.
    const source = useMemo(() => prepareMarkdownSource(content, isUser), [content, isUser]);

    return (
      <div className={cn('markdown-content text-px-13 mobile:text-sm leading-relaxed', className)}>
        <ReactMarkdown
          remarkPlugins={isUser ? USER_REMARK_PLUGINS : ANSWER_REMARK_PLUGINS}
          remarkRehypeOptions={{ allowDangerousHtml: true }}
          // Order matters: rehypeRaw parses embedded HTML, rehypeSanitize is
          // the XSS boundary (schema audited against all legitimate card /
          // rich-HTML markup). rehypeMathInText then converts `$…$`/`$$…$$`
          // found in the (now expanded) HTML text into math markers, and
          // rehypeKatex runs AFTER sanitize so its generated markup is not
          // stripped while the math nodes it consumes survive sanitization
          // (className allowed globally). Every step after sanitize is exempt
          // by design: the math steps read already-sanitized text and emit
          // fixed-class spans, rehypeTableLabels only writes attribute VALUES
          // (a column's name, a role) computed from that text, contact-photo
          // repair only adds a fixed class to an existing image, phone formatting
          // only rewrites text values, and the search
          // marks wrap it in a fixed-class <mark>.
          rehypePlugins={rehypePlugins}
          // Custom URL transform to allow tel: and mailto: protocols
          // Default only allows: http, https, irc, ircs, mailto, xmpp
          urlTransform={(url: string) => {
            // Allow tel: protocol for click-to-call
            if (url.startsWith('tel:')) return url;
            // Allow mailto: protocol for email links
            if (url.startsWith('mailto:')) return url;
            // Allow safe protocols
            if (url.startsWith('http://') || url.startsWith('https://')) return url;
            // Allow relative URLs
            if (url.startsWith('/') || url.startsWith('#') || url.startsWith('?')) return url;
            // Block other protocols (javascript:, data:, etc.)
            if (url.includes(':')) return '';
            // Allow protocol-relative URLs
            return url;
          }}
          components={{
            span: MarkdownClassificationSpan,
            button: MarkdownCardButton,
            // Headings
            h1: ({ children }) => (
              <h1 className="text-2xl font-bold mt-6 mb-4 first:mt-0 border-b border-border pb-2">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-xl font-semibold mt-5 mb-3 first:mt-0 border-b border-border/50 pb-1.5">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-lg font-semibold mt-4 mb-2 first:mt-0">{children}</h3>
            ),
            h4: ({ children }) => (
              <h4 className="text-base font-semibold mt-3 mb-2 first:mt-0">{children}</h4>
            ),
            h5: ({ children }) => (
              <h5 className="text-sm font-semibold mt-3 mb-1.5 first:mt-0">{children}</h5>
            ),
            h6: ({ children }) => (
              <h6 className="text-sm font-semibold mt-3 mb-1.5 first:mt-0 text-muted-foreground">
                {children}
              </h6>
            ),

            // Paragraphs - preserve LIA component classes
            p: ({ className, children, node: _node, ...props }) => {
              // LIA components (e.g., lia-email__snippet) need their original class preserved
              const isLiaComponent = className?.startsWith('lia-');
              return (
                <p
                  className={
                    isLiaComponent
                      ? className
                      : cn('mb-3 last:mb-0 whitespace-pre-wrap break-words', className)
                  }
                  {...props}
                >
                  {children}
                </p>
              );
            },

            // Strong (bold)
            strong: ({ children }) => (
              <strong className="font-semibold text-foreground">{children}</strong>
            ),

            // Emphasis (italic)
            em: ({ children }) => <em className="italic text-foreground">{children}</em>,

            // Links
            a: ({ href, className, children, node: _node, ...props }) => {
              // LIA components (e.g., lia-event__title) need their original class preserved
              const isLiaComponent = className?.startsWith('lia-');

              // tel: and mailto: links should NOT open in new tab (breaks native handlers)
              const isProtocolLink = href?.startsWith('tel:') || href?.startsWith('mailto:');

              return (
                <a
                  href={href}
                  // Only external links open in new tab - tel:/mailto: use native handlers
                  {...(!isProtocolLink && { target: '_blank', rel: 'noopener noreferrer' })}
                  className={
                    isLiaComponent
                      ? className
                      : cn(
                          'underline decoration-primary/40 hover:decoration-primary transition-colors',
                          isUser
                            ? 'text-primary-foreground hover:text-primary-foreground/90'
                            : 'text-primary hover:text-primary/90'
                        )
                  }
                  {...props}
                >
                  {children}
                </a>
              );
            },

            // Unordered lists - balanced spacing between items.
            // LIA component classes (e.g. future lia-* list variants) are
            // preserved verbatim — same contract as the `p`/`a` overrides.
            ul: ({ className, children }) => {
              const isLiaComponent = className?.startsWith('lia-');
              return (
                <ul
                  className={
                    isLiaComponent
                      ? className
                      : cn('list-disc list-outside pl-5 mb-2 space-y-1.5 last:mb-0', className)
                  }
                >
                  {children}
                </ul>
              );
            },

            // Ordered lists - generous spacing (numbered items often contain
            // rich content). `lia-steps` (ADR-177 styled counters) must keep
            // its class: the stylesheet resets list-style and draws numbered
            // bullets itself, so the default decimal classes would fight it.
            ol: ({ className, children, start }) => {
              const isLiaComponent = className?.startsWith('lia-');
              return (
                <ol
                  start={start}
                  className={
                    isLiaComponent
                      ? className
                      : cn('list-decimal list-outside pl-5 mb-2 space-y-3 last:mb-0', className)
                  }
                >
                  {children}
                </ol>
              );
            },

            // List items - normal leading for readability
            li: ({ children, value }) => (
              <li value={value} className="pl-1 leading-normal">
                {children}
              </li>
            ),

            // Blockquotes
            blockquote: ({ children }) => (
              <blockquote
                className={cn(
                  'border-l-4 pl-4 py-2 my-3 italic',
                  isUser
                    ? 'border-primary-foreground/30 bg-primary-foreground/5'
                    : 'border-primary/40 bg-muted/30'
                )}
              >
                {children}
              </blockquote>
            ),

            // Code blocks: the <pre> is the unit. A fence with or without a
            // language, an indented block and a raw <pre><code> all reach
            // CodeBlock (measured 2026-09-17: routed on the code element's
            // `language-*` class alone, three of the four fell through to the
            // inline chip below — no header, no copy button, no scroll box).
            pre: ({ node, children }) => {
              const block = codeBlockOf(node);
              if (!block) return <pre>{children}</pre>;

              // Suspense fallback matches the old plain <pre> look so the
              // visual transition on lazy-load is imperceptible.
              const fallback = (
                <div className="my-3 rounded-lg overflow-hidden border border-border/50 shadow-sm">
                  <div className="px-3 py-1 text-xs font-mono bg-muted/50 text-muted-foreground border-b border-border/50">
                    {block.language}
                  </div>
                  <pre className="code-scroll p-3 bg-muted/20">
                    <code className="text-sm font-mono text-foreground block">{block.text}</code>
                  </pre>
                </div>
              );

              return (
                <Suspense fallback={fallback}>
                  <CodeBlock language={block.language}>{block.text}</CodeBlock>
                </Suspense>
              );
            },

            // Inline code — every block was taken by `pre` above.
            code: ({ className: codeClassName, children }) => (
              <code
                className={cn(
                  'px-1.5 py-0.5 rounded text-xs font-mono',
                  isUser
                    ? 'bg-primary-foreground/20 text-primary-foreground'
                    : 'bg-muted text-foreground',
                  codeClassName
                )}
              >
                {children}
              </code>
            ),

            // Horizontal rule
            hr: () => <hr className="my-4 border-t border-border/50" />,

            // Tables: a table where it fits, a scroll box with a visible cue
            // where it does not, stacked cards on a narrow screen (B2). Stable
            // module-level components — see `markdown-table.tsx`.
            table: MarkdownTable,
            thead: MarkdownTableHead,
            tbody: MarkdownTableBody,
            tr: MarkdownTableRow,
            th: MarkdownTableHeaderCell,
            td: MarkdownTableCell,

            // Task lists (GFM extension)
            input: ({ checked, ...props }) => (
              <input
                type="checkbox"
                checked={checked}
                disabled
                className="mr-2 align-middle accent-primary cursor-default"
                {...props}
              />
            ),

            // Images - using separate component to comply with React hooks rules
            img: MarkdownImage,
            details: MarkdownCardDetails,

            // Divs - intercept photo galleries and MCP Apps for enhanced interactivity
            div: MarkdownDiv,
          }}
        >
          {source}
        </ReactMarkdown>
      </div>
    );
  }
);
MarkdownContent.displayName = 'MarkdownContent';
