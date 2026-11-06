/**
 * An e-mail as its author laid it out, isolated (ADR-369, D3, spec §7, A1).
 *
 * The sender's HTML is the `srcdoc` of a sandboxed frame: no script, no form, no
 * same origin, and the one permission of opening a new tab. The document opens on a
 * policy that refuses every resource but inline styles and embedded images — the
 * policy comes BEFORE the sender's first byte, so nothing they wrote can be read
 * before it. A link survives only as a web or mail address, in a new tab. Remote
 * images load on the person's click alone, and the page says what that tells the
 * sender.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { fireEvent, renderWithProviders, screen } from '@/__tests__/test-utils';

import { AuthoredHtmlFrame } from '../AuthoredHtmlFrame';

const { scheme } = vi.hoisted(() => ({ scheme: { resolved: 'light' } }));
vi.mock('next-themes', async importOriginal => ({
  ...(await importOriginal<typeof import('next-themes')>()),
  useTheme: () => ({ resolvedTheme: scheme.resolved }),
}));

afterEach(() => {
  scheme.resolved = 'light';
});

const POLICY =
  '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:">';
const POLICY_WITH_IMAGES =
  '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src https: data:">';
const SENDER = '<p style="color:#123456">Hello</p><img src="https://tracker.example/p.gif">';
const SHOW = 'workbench.mail.show_images';
const ABOUT_THE_IMAGES = /workbench\.mail\.images_/;

function draw(
  html: string,
  images = false,
  onShowImages = vi.fn(),
  inline: readonly { cid: string; data_url: string }[] = []
) {
  renderWithProviders(
    <AuthoredHtmlFrame
      lng="en"
      html={html}
      title="The frame"
      images={images}
      onShowImages={onShowImages}
      inline={inline}
    />
  );
  const element = screen.getByTitle('The frame');
  if (!(element instanceof HTMLIFrameElement)) throw new Error('not a frame');
  return element;
}

describe('a document that offers no remote image', () => {
  it('never asks, whatever its HTML holds', () => {
    renderWithProviders(<AuthoredHtmlFrame lng="en" html={SENDER} title="The file" />);

    expect(screen.queryByRole('button', { name: SHOW })).toBeNull();
    expect(screen.getByTitle('The file').getAttribute('srcdoc')).not.toContain('https: data:');
  });
});

function frame(): HTMLIFrameElement {
  return draw(SENDER);
}

function parsed(element: HTMLIFrameElement): Document {
  return new DOMParser().parseFromString(element.getAttribute('srcdoc') ?? '', 'text/html');
}

describe('AuthoredHtmlFrame', () => {
  describe('its links', () => {
    it.each([
      [
        '<a href="https://www.example.org/a?b=1" target="_self">Open</a>',
        'https://www.example.org/a?b=1',
      ],
      ['<a HREF="http://www.example.org/a" TARGET="_parent">Open</a>', 'http://www.example.org/a'],
      ['<area href="https://www.example.org/a" target="_top">', 'https://www.example.org/a'],
      ['<a href="mailto:ana@example.org">Write</a>', 'mailto:ana@example.org'],
      [
        '<noscript><a href="https://www.example.org/a" target="_self">Open</a></noscript>',
        'https://www.example.org/a',
      ],
    ])('keeps %s, in a new tab that cannot reach back', (html, href) => {
      const links = Array.from(parsed(draw(html)).querySelectorAll('a, area'));

      expect(links).not.toHaveLength(0);
      for (const link of links) {
        expect(link.getAttribute('href')).toBe(href);
        expect(link.getAttribute('target')).toBe('_blank');
        expect(link.getAttribute('rel')).toBe('noopener noreferrer');
      }
    });

    it.each([
      'javascript:alert(1)',
      ' JaVaScRiPt:alert(1)',
      'vbscript:msgbox(1)',
      'data:text/html,<script>alert(1)</script>',
      'file:///etc/passwd',
      'tel:+33123456789',
      'blob:https://www.example.org/1',
      '/account/delete',
      '#top',
      'https://bank.example@evil.example/',
    ])('takes the address off a link to %s, and keeps its words', address => {
      const shown = parsed(draw(`<a href="${address}" target="_self">Words</a>`));
      const link = shown.querySelector('a');

      expect(link?.hasAttribute('href')).toBe(false);
      expect(link?.hasAttribute('target')).toBe(false);
      expect(link?.textContent).toBe('Words');
    });

    it('never lets an SVG link keep its old-style address', () => {
      const shown = parsed(
        draw('<svg><a xlink:href="https://www.example.org/a" target="_self">Open</a></svg>')
      );

      for (const link of Array.from(shown.querySelectorAll('a'))) {
        expect(link.hasAttribute('xlink:href')).toBe(false);
        expect(link.hasAttribute('href')).toBe(false);
      }
    });

    it('takes off what a link could do besides opening', () => {
      const shown = parsed(
        draw(
          '<a href="https://www.example.org/a" ping="https://tracker.example/p" download referrerpolicy="unsafe-url">Open</a>'
        )
      );
      const link = shown.querySelector('a');

      expect(link?.hasAttribute('ping')).toBe(false);
      expect(link?.hasAttribute('download')).toBe(false);
      expect(link?.hasAttribute('referrerpolicy')).toBe(false);
    });

    it('treats the links inside nested templates the same, before a shadow root could use them', () => {
      const shown = parsed(
        draw(
          '<div><template shadowrootmode="open">' +
            '<template><a href="javascript:alert(1)">Bad</a>' +
            '<a href="https://www.example.org/a" target="_top">Good</a></template>' +
            '</template></div>'
        )
      );
      const inner = shown.querySelector('template')?.content.querySelector('template')?.content;
      const [bad, good] = Array.from(inner?.querySelectorAll('a') ?? []);

      expect(bad?.hasAttribute('href')).toBe(false);
      expect(good?.getAttribute('target')).toBe('_blank');
    });
  });

  describe('its images', () => {
    it('loads nothing remote until the person asks, and offers just that', () => {
      const element = draw(SENDER);

      expect(element.getAttribute('srcdoc')).toContain(POLICY);
      expect(screen.getByRole('button', { name: SHOW })).toBeVisible();
      expect(screen.queryByText(ABOUT_THE_IMAGES)).toBeNull();
    });

    it('asks once clicked, and takes the focus to the message the images come to', () => {
      const onShowImages = vi.fn();
      const element = draw(SENDER, false, onShowImages);

      fireEvent.click(screen.getByRole('button', { name: SHOW }));

      expect(onShowImages).toHaveBeenCalledOnce();
      expect(document.activeElement).toBe(element);
    });

    it('lets https and embedded images in once asked, with nothing left to say', () => {
      const element = draw(SENDER, true);

      expect(element.getAttribute('srcdoc')).toContain(POLICY_WITH_IMAGES);
      expect(screen.queryByRole('button', { name: SHOW })).toBeNull();
      expect(screen.queryByText(ABOUT_THE_IMAGES)).toBeNull();
    });

    it.each([
      '<img src="https://www.example.org/a.png">',
      '<picture><source srcset="https://www.example.org/a.webp"></picture>',
      '<table background="https://www.example.org/a.png"><tr><td>x</td></tr></table>',
      '<div style="background:url(https://www.example.org/a.png)">x</div>',
      '<style>body{background:url(https://www.example.org/a.png)}</style>',
      '<template><img src="https://www.example.org/a.png"></template>',
    ])('offers the images of %s', html => {
      draw(html);

      expect(screen.getByRole('button', { name: SHOW })).toBeVisible();
    });

    it.each([
      '<p>Words alone</p>',
      '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">',
      '<img src="cid:logo@example.org">',
    ])('offers nothing where nothing remote is held: %s', html => {
      draw(html);

      expect(screen.queryByRole('button', { name: SHOW })).toBeNull();
    });
  });

  describe('the images it carries', () => {
    const PNG = 'data:image/png;base64,iVBORw0KGgo=';
    const inline = (cid: string, data_url = PNG) => [{ cid, data_url }];

    it('draws an image of its own, as its HTML names it', () => {
      const element = draw('<img src="cid:logo@x">', false, vi.fn(), inline('logo@x'));

      expect(parsed(element).querySelector('img')?.getAttribute('src')).toBe(PNG);
    });

    it('reads a name its HTML percent-encodes', () => {
      const element = draw('<img src="cid:logo%40x">', false, vi.fn(), inline('logo@x'));

      expect(parsed(element).querySelector('img')?.getAttribute('src')).toBe(PNG);
    });

    it('leaves a name nobody answered, which loads nothing', () => {
      const element = draw('<img src="cid:other">', false, vi.fn(), inline('logo@x'));

      expect(parsed(element).querySelector('img')?.getAttribute('src')).toBe('cid:other');
    });

    it('draws nothing but an image, whatever the answer says', () => {
      const element = draw(
        '<img src="cid:logo@x">',
        false,
        vi.fn(),
        inline('logo@x', 'data:text/html;base64,PHNjcmlwdD4=')
      );

      expect(parsed(element).querySelector('img')?.getAttribute('src')).toBe('cid:logo@x');
    });

    it('draws one named as a table’s background, asking for no click', () => {
      const element = draw(
        '<table background="cid:logo@x"></table>',
        false,
        vi.fn(),
        inline('logo@x')
      );

      expect(parsed(element).querySelector('table')?.getAttribute('background')).toBe(PNG);
      expect(screen.queryByRole('button', { name: SHOW })).toBeNull();
    });

    it('asks for no click: they tell a sender nothing', () => {
      draw('<img src="cid:logo@x">', false, vi.fn(), inline('logo@x'));

      expect(screen.queryByRole('button', { name: SHOW })).toBeNull();
    });
  });

  it('removes a sender’s base and refresh while keeping their layout and readable text', () => {
    const html =
      '<html><head><style>p{padding:1em}</style><base href="https://www.google.com/">' +
      '<meta http-equiv="refresh" content="0;url=https://www.google.com/mail-link-probe"></head>' +
      '<body><p>Readable original</p><table><tr><td>Amount</td></tr></table></body></html>';
    const document = parsed(draw(html));

    expect(document.querySelector('base[href]')).toBeNull();
    expect(document.querySelector('meta[http-equiv="refresh"]')).toBeNull();
    expect(document.querySelector('style')?.textContent).toContain('color-scheme:light');
    expect(document.head.textContent).toContain('p{padding:1em}');
    expect(document.body.textContent).toContain('Readable original');
    expect(document.querySelector('td')?.textContent).toBe('Amount');
  });

  it('may open a new tab and nothing else, and sends no referrer', () => {
    const element = frame();

    expect(element.getAttribute('sandbox')?.split(' ').sort()).toEqual([
      'allow-popups',
      'allow-popups-to-escape-sandbox',
    ]);
    expect(element.getAttribute('referrerpolicy')).toBe('no-referrer');
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

  it('lays a light paper through the light scheme, never a literal colour', () => {
    const preamble = (frame().getAttribute('srcdoc') ?? '').split(SENDER)[0];

    expect(preamble).toContain('<meta name="color-scheme" content="light">');
    expect(preamble).toContain('html{color-scheme:light;background:Canvas;color:CanvasText}');
    expect(preamble).not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(|white|black/i);
  });

  it('leaves a light theme to the sender, with nothing to choose', () => {
    const source = frame().getAttribute('srcdoc') ?? '';

    expect(source).not.toContain('invert(');
    expect(screen.queryByRole('button', { name: 'workbench.mail.colours_of_author' })).toBeNull();
  });

  it('turns the page down in a dark theme, its images keeping their colours', () => {
    scheme.resolved = 'dark';

    const preamble = (frame().getAttribute('srcdoc') ?? '').split(SENDER)[0];

    expect(preamble).toMatch(/html\{[^}]*filter:invert\(1\) hue-rotate\(180deg\)/);
    expect(preamble).toMatch(/img,[^{]*\{filter:invert\(1\) hue-rotate\(180deg\)\}/);
  });

  it('asks the frame for nothing more in a dark theme: its policy stays what it was', () => {
    scheme.resolved = 'dark';

    const source = frame().getAttribute('srcdoc') ?? '';

    expect(source).toContain(POLICY);
    expect(source.indexOf(POLICY)).toBeLessThan(source.indexOf('invert('));
  });

  it('gives the sender’s colours back on a click, and the theme on the next', () => {
    scheme.resolved = 'dark';
    const element = frame();

    fireEvent.click(screen.getByRole('button', { name: 'workbench.mail.colours_of_author' }));
    expect(element.getAttribute('srcdoc')).not.toContain('invert(');

    fireEvent.click(screen.getByRole('button', { name: 'workbench.mail.colours_of_theme' }));
    expect(element.getAttribute('srcdoc')).toContain('invert(');
  });
});
