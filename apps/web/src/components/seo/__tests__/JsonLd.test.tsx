/**
 * JsonLd — SEO structured-data script safety (CA-5, audit hardening).
 *
 * Every JSON-LD block is injected via `dangerouslySetInnerHTML`. Schema fields
 * carry app-compiled dynamic content (FAQ questions, blog article titles/
 * excerpts, how-to steps, breadcrumb names). A raw `JSON.stringify` lets a
 * `</script>` sequence inside any field close the `<script>` element early and
 * inject arbitrary markup. `serializeJsonLd` escapes `<` to its `<` form
 * so no closing-tag sequence survives in the rendered HTML.
 */

import { readdirSync, readFileSync } from 'fs';
import { join } from 'path';

import { describe, it, expect, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { serializeJsonLd, FAQPageJsonLd, BlogListJsonLd } from '../JsonLd';

// A field value that, unescaped, closes the ld+json <script> and opens a new one.
const SCRIPT_BREAKOUT = '</script><script>window.__xss=1//</script>';

describe('serializeJsonLd — script-context escaping', () => {
  it('escapes every "<" so no closing-tag sequence survives', () => {
    const out = serializeJsonLd({ name: SCRIPT_BREAKOUT });

    expect(out).not.toContain('<');
    expect(out).toContain('\\u003c/script>');
  });

  it('stays valid JSON that round-trips to the original value', () => {
    const out = serializeJsonLd({ name: SCRIPT_BREAKOUT });

    expect(JSON.parse(out).name).toBe(SCRIPT_BREAKOUT);
  });
});

describe('JsonLd components — no <script> breakout in rendered HTML', () => {
  it('FAQPageJsonLd neutralizes a </script> payload in a question', () => {
    const html = renderToStaticMarkup(
      <FAQPageJsonLd questions={[{ question: SCRIPT_BREAKOUT, answer: 'safe answer' }]} />
    );

    // Exactly one real <script> open and one </script> close — no breakout.
    expect(html.match(/<script/g)?.length).toBe(1);
    expect(html.match(/<\/script>/g)?.length).toBe(1);
    expect(html).not.toContain('</script><script>');
    // The payload's "<" is escaped, so its closing tag is inert.
    expect(html).toContain('\\u003c/script>');
  });

  it('BlogListJsonLd neutralizes a </script> payload in an article title', () => {
    // BlogListJsonLd is ORIGIN-BEARING: since the release image became
    // host-neutral (ADR-215/B03) it renders nothing at all when no origin is
    // configured, because emitting a canonical URL it cannot know would be a
    // fabricated claim. The escaping oracle therefore needs an origin, stubbed
    // here rather than inherited: `task test:frontend` supplies one through the
    // Taskfile's global `dotenv: .env`, CI does not — so without this stub the
    // test passes locally and fails in CI on `match(...)` returning null.
    vi.stubEnv('NEXT_PUBLIC_APP_URL', 'https://lia.test');
    vi.stubEnv('APP_URL_SERVER', '');

    const html = renderToStaticMarkup(
      <BlogListJsonLd
        lng="en"
        title="Blog"
        description="desc"
        articles={[
          {
            title: SCRIPT_BREAKOUT,
            url: 'https://example.test/post',
            date: '2026-07-07',
            excerpt: 'excerpt',
          },
        ]}
      />
    );

    expect(html.match(/<script/g)?.length).toBe(1);
    expect(html.match(/<\/script>/g)?.length).toBe(1);
    expect(html).not.toContain('</script><script>');

    vi.unstubAllEnvs();
  });

  it('BlogListJsonLd emits nothing when no origin is configured', () => {
    // Non-vacuity for the stub above: proves the previous test needs it, and
    // pins the host-neutral contract — no origin means no fabricated canonical.
    vi.stubEnv('NEXT_PUBLIC_APP_URL', '');
    vi.stubEnv('APP_URL_SERVER', '');

    const html = renderToStaticMarkup(
      <BlogListJsonLd
        lng="en"
        title="Blog"
        description="desc"
        articles={[
          { title: 'safe', url: 'https://example.test/post', date: '2026-07-07', excerpt: 'e' },
        ]}
      />
    );

    expect(html).toBe('');

    vi.unstubAllEnvs();
  });
});

// Raw `JSON.stringify` piped straight into a script's innerHTML. Tolerant of
// any whitespace between `__html:` and `JSON.stringify(` — a single space
// (Prettier default), no space (compact), or a line wrap — so a reformatted
// regression cannot evade the guard.
const RAW_STRINGIFY_SINK = /__html:\s*JSON\.stringify\(/;

describe('JSON-LD script safety — systemic guard (CA-5)', () => {
  it('matcher catches every whitespace variant of the raw sink and ignores the safe helper', () => {
    // Non-vacuity: prove the guard actually fires on bad shapes before we
    // trust an empty offender list to mean "clean".
    expect(RAW_STRINGIFY_SINK.test('{{ __html: JSON.stringify(s) }}')).toBe(true); // spaced
    expect(RAW_STRINGIFY_SINK.test('{{__html:JSON.stringify(s)}}')).toBe(true); // compact
    expect(RAW_STRINGIFY_SINK.test('{{ __html:\n  JSON.stringify(s) }}')).toBe(true); // wrapped
    expect(RAW_STRINGIFY_SINK.test('{{ __html: serializeJsonLd(s) }}')).toBe(false); // safe
  });

  // Whole-`src` synchronous scan: inherently IO-heavy (hundreds of files), so
  // it can exceed the 5s default when the full suite runs in parallel. Uses
  // Dirent (withFileTypes) to skip a statSync per entry, and gets a generous
  // timeout so contention — not a real offender — never reddens CI.
  it('no raw JSON.stringify is injected into a <script> via dangerouslySetInnerHTML', () => {
    // Every ld+json script must route through serializeJsonLd (which escapes
    // `<`). This guard catches any file — JsonLd.tsx, the blog page, or a
    // future sink — that reintroduces a raw `JSON.stringify` in a script.
    const walk = (dir: string): string[] => {
      const out: string[] = [];
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === 'node_modules' || entry.name === '__tests__') continue;
        const full = join(dir, entry.name);
        if (entry.isDirectory()) {
          out.push(...walk(full));
        } else if (/\.(tsx?|jsx?)$/.test(entry.name)) {
          out.push(full);
        }
      }
      return out;
    };

    const offenders = walk(join(process.cwd(), 'src')).filter(file =>
      RAW_STRINGIFY_SINK.test(readFileSync(file, 'utf-8'))
    );

    expect(offenders).toEqual([]);
  }, 30000);
});
