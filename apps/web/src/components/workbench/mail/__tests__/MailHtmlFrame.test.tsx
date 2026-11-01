/**
 * An e-mail as its author laid it out, isolated (ADR-369, D3, spec §7).
 *
 * The sender's HTML is the `srcdoc` of a frame sandboxed with no permission at
 * all, and the document opens on a policy that refuses every resource but
 * inline styles — the policy comes BEFORE the sender's first byte, so nothing
 * they wrote can be read before it.
 */

import { describe, expect, it } from 'vitest';

import { renderWithProviders, screen } from '@/__tests__/test-utils';

import { MailHtmlFrame } from '../MailHtmlFrame';

const POLICY =
  '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">';
const SENDER = '<p style="color:#123456">Hello</p><img src="https://tracker.example/p.gif">';

function frame(): HTMLIFrameElement {
  renderWithProviders(<MailHtmlFrame lng="en" html={SENDER} />);
  const element = screen.getByTitle('workbench.mail.html_frame_title');
  if (!(element instanceof HTMLIFrameElement)) throw new Error('not a frame');
  return element;
}

describe('MailHtmlFrame', () => {
  it.each([
    '<a href="https://www.google.com/mail-link-probe" target="_self">Open</a>',
    '<a HREF="https://www.google.com/mail-link-probe" TARGET="_parent">Open</a>',
    '<area href="https://www.google.com/mail-link-probe" target="_top">',
    '<svg><a xlink:href="https://www.google.com/mail-link-probe" target="_self">Open</a></svg>',
    '<noscript><a href="https://www.google.com/mail-link-probe" target="_self">Open</a></noscript>',
  ])('removes navigation even when the sender supplies an explicit target: %s', html => {
    renderWithProviders(<MailHtmlFrame lng="en" html={html} />);
    const element = screen.getByTitle('workbench.mail.html_frame_title');
    const document = new DOMParser().parseFromString(
      element.getAttribute('srcdoc') ?? '',
      'text/html'
    );
    const links = Array.from(document.querySelectorAll('a, area'));

    expect(links).not.toHaveLength(0);
    for (const link of links) {
      expect(link.hasAttribute('href')).toBe(false);
      expect(link.hasAttribute('xlink:href')).toBe(false);
    }
  });

  it('disables links inside nested templates before a declarative shadow root could use them', () => {
    renderWithProviders(
      <MailHtmlFrame
        lng="en"
        html={
          '<div><template shadowrootmode="open">' +
          '<template><a href="https://www.google.com/mail-link-probe">Open</a></template>' +
          '</template></div>'
        }
      />
    );
    const element = screen.getByTitle('workbench.mail.html_frame_title');
    const document = new DOMParser().parseFromString(
      element.getAttribute('srcdoc') ?? '',
      'text/html'
    );
    const link = document
      .querySelector('template')
      ?.content.querySelector('template')
      ?.content.querySelector('a');

    expect(link?.textContent).toBe('Open');
    expect(link?.hasAttribute('href')).toBe(false);
  });

  it('removes a sender’s base and refresh while keeping their layout and readable text', () => {
    const html =
      '<html><head><style>p{padding:1em}</style><base href="https://www.google.com/">' +
      '<meta http-equiv="refresh" content="0;url=https://www.google.com/mail-link-probe"></head>' +
      '<body><p>Readable original</p><table><tr><td>Amount</td></tr></table></body></html>';
    renderWithProviders(<MailHtmlFrame lng="en" html={html} />);
    const element = screen.getByTitle('workbench.mail.html_frame_title');
    const document = new DOMParser().parseFromString(
      element.getAttribute('srcdoc') ?? '',
      'text/html'
    );

    expect(document.querySelector('base[href]')).toBeNull();
    expect(document.querySelector('meta[http-equiv="refresh"]')).toBeNull();
    expect(document.querySelector('style')?.textContent).toContain('color-scheme:light');
    expect(document.head.textContent).toContain('p{padding:1em}');
    expect(document.body.textContent).toContain('Readable original');
    expect(document.querySelector('td')?.textContent).toBe('Amount');
  });

  it('is sandboxed with no permission at all and sends no referrer', () => {
    const element = frame();

    expect(element.getAttribute('sandbox')).toBe('');
    expect(element.getAttribute('referrerpolicy')).toBe('no-referrer');
    expect(element.outerHTML).not.toMatch(/allow-/);
  });

  it('opens the document on the policy, before anything the sender wrote', () => {
    const document = frame().getAttribute('srcdoc') ?? '';

    expect(document.startsWith('<!doctype html><html><head><meta charset="utf-8">')).toBe(true);
    expect(document).toContain(POLICY);
    expect(document.indexOf(POLICY)).toBeLessThan(document.indexOf(SENDER));
    expect(document).toContain(SENDER);
  });

  it('keeps a safe default target and sends no referrer from inside', () => {
    const preamble = (frame().getAttribute('srcdoc') ?? '').split(SENDER)[0];

    expect(preamble).toContain('<base target="_blank">');
    expect(preamble).toContain('<meta name="referrer" content="no-referrer">');
  });

  it('keeps a light paper in every theme through the light scheme, never a literal colour', () => {
    const preamble = (frame().getAttribute('srcdoc') ?? '').split(SENDER)[0];

    expect(preamble).toContain('<meta name="color-scheme" content="light">');
    expect(preamble).toContain('html{color-scheme:light;background:Canvas;color:CanvasText}');
    expect(preamble).not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(|white|black/i);
  });
});
