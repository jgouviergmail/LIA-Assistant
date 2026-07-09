/**
 * MarkdownContent — XSS sanitization boundary (rehype-sanitize).
 *
 * The LLM can relay verbatim third-party content (email bodies, fetched web
 * pages, MCP tool output) in HTML mode; rehype-raw parses it. These tests pin
 * the sanitize schema: attack vectors are stripped while every category of
 * legitimate markup (cards, callouts, action buttons, sentinels, KaTeX,
 * collapsibles, tel: links) survives.
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';

import { MarkdownContent } from '../MarkdownContent';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe('MarkdownContent — XSS vectors stripped', () => {
  it('strips <script> tags including their content', () => {
    const { container } = render(
      <MarkdownContent content={'before <script>window.hacked = true;</script> after'} />
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).not.toContain('window.hacked');
    expect(container.textContent).toContain('before');
    expect(container.textContent).toContain('after');
  });

  it('strips <iframe> (incl. srcdoc payloads)', () => {
    const { container } = render(
      <MarkdownContent content={'<iframe srcdoc="<script>x()</script>"></iframe>'} />
    );
    expect(container.querySelector('iframe')).toBeNull();
  });

  it('drops inline event handlers', () => {
    const { container } = render(
      <MarkdownContent content={'<img src="https://example.com/a.png" onerror="alert(1)">'} />
    );
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('onerror')).toBeNull();
  });

  it('drops javascript: URLs (schema + urlTransform double layer)', () => {
    const { container } = render(
      <MarkdownContent content={'<a href="javascript:alert(1)">x</a>'} />
    );
    const link = container.querySelector('a');
    expect(link?.getAttribute('href') || '').not.toContain('javascript');
  });

  it('strips <form> elements', () => {
    const { container } = render(
      <MarkdownContent content={'<form action="https://evil.example"><input name="q"></form>'} />
    );
    expect(container.querySelector('form')).toBeNull();
  });

  it('strips legacy inline <style> blocks without leaking CSS as text', () => {
    // Messages predating the externalized .lia-response CSS carry this block.
    const { container } = render(
      <MarkdownContent content={'<style>.lia-response h2 { color: red; }</style><p>hello</p>'} />
    );
    expect(container.querySelector('style')).toBeNull();
    expect(container.textContent).not.toContain('color: red');
    expect(container.textContent).toContain('hello');
  });
});

describe('MarkdownContent — legitimate markup survives', () => {
  it('keeps rich-HTML response structure with classes', () => {
    const { container } = render(
      <MarkdownContent
        content={'<div class="lia-response"><h2>Titre</h2><p class="lia-callout">note</p></div>'}
      />
    );
    expect(container.querySelector('.lia-response')).not.toBeNull();
    expect(container.querySelector('.lia-callout')).not.toBeNull();
  });

  it('keeps card title link classes (defaultSchema constrains a.className)', () => {
    // Regression: defaultSchema allows a.className ONLY as data-footnote-backref,
    // which stripped .lia-card__title and rendered the title as a blue link.
    const { container } = render(
      <MarkdownContent
        content={'<a href="/x" class="lia-card__title lia-title-underline">Titre</a>'}
      />
    );
    const link = container.querySelector('a');
    expect(link).not.toBeNull();
    expect(link?.className).toContain('lia-card__title');
  });

  it('keeps card action buttons with data-action', () => {
    const { container } = render(
      <MarkdownContent
        content={'<button type="button" class="lia-btn" data-action="confirm">OK</button>'}
      />
    );
    const button = container.querySelector('button');
    expect(button).not.toBeNull();
    expect(button?.getAttribute('data-action')).toBe('confirm');
  });

  it('keeps the MCP app sentinel div with data-registry-id', () => {
    // The components mapping intercepts this AFTER the rehype pipeline —
    // the sentinel and its registry id must survive sanitization.
    const { container } = render(
      <MarkdownContent content={'<div class="lia-mcp-app" data-registry-id="reg_1">…</div>'} />
    );
    // Interception replaces the div with the widget placeholder (Suspense
    // fallback in tests) — presence of the placeholder proves survival.
    expect(container.textContent).toContain('mcp_apps.loading');
  });

  it('keeps collapsible details/summary with open attribute', () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<details class="lia-collapsible" open><summary>plus</summary><p>corps</p></details>'
        }
      />
    );
    const details = container.querySelector('details');
    expect(details).not.toBeNull();
    expect(details?.hasAttribute('open')).toBe(true);
  });

  it('keeps tel: links (click-to-call)', () => {
    // Note: formatPhonesInText (existing behaviour) may reformat the number —
    // what matters here is that the tel: protocol survives sanitization.
    const { container } = render(
      <MarkdownContent content={'<a href="tel:+33612345678">tel</a>'} />
    );
    expect(container.querySelector('a')?.getAttribute('href')).toMatch(/^tel:/);
  });

  it('keeps inline style attributes used by cards', () => {
    const { container } = render(
      <MarkdownContent content={'<span style="opacity:0.7">meta</span>'} />
    );
    expect(container.querySelector('span')?.getAttribute('style')).toContain('opacity');
  });

  it('KaTeX still renders after sanitization (plugin order)', () => {
    const { container } = render(<MarkdownContent content={'$$a + b$$'} />);
    expect(container.querySelector('.katex')).not.toBeNull();
  });
});
