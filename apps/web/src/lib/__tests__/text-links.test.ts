import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { linkSegments, linksOf, WRITTEN_LINK_LABEL } from '../text-links';

const link = (text: string, href: string) => ({ kind: 'link', text, href });
const plain = (text: string) => ({ kind: 'text', text });

describe('linkSegments', () => {
  it('leaves a text with no address whole', () => {
    expect(linkSegments('Nothing here, not even a dot.')).toEqual([
      plain('Nothing here, not even a dot.'),
    ]);
  });

  it('answers nothing for an empty text', () => {
    expect(linkSegments('')).toEqual([]);
  });

  describe('a link the API wrote', () => {
    it('is drawn by its host, never as its markup', () => {
      expect(linkSegments('Read this [link](https://click.example.org/a?b=1) now')).toEqual([
        plain('Read this '),
        link('click.example.org', 'https://click.example.org/a?b=1'),
        plain(' now'),
      ]);
    });

    it('keeps the parentheses of its address', () => {
      expect(linkSegments('[link](https://example.org/wiki/A_(b))')).toEqual([
        link('example.org', 'https://example.org/wiki/A_(b)'),
      ]);
    });

    it('names a mail address and a phone number by themselves', () => {
      expect(linkSegments('[link](mailto:ana@example.org) [link](tel:+33123456789)')).toEqual([
        link('ana@example.org', 'mailto:ana@example.org'),
        plain(' '),
        link('+33123456789', 'tel:+33123456789'),
      ]);
    });

    it.each([
      'javascript:alert(1)',
      'data:text/html,x',
      'file:///etc/passwd',
      'https://bank.example@evil.example/',
      'https://user:secret@example.org/',
    ])('is removed when its address may not be followed: %s', address => {
      expect(linkSegments(`Before [link](${address}) after`)).toEqual([
        plain('Before '),
        plain(' after'),
      ]);
    });

    it('stays words when it never closes', () => {
      const text = 'See [link](https://example.org and more';

      expect(linkSegments(text)).toEqual([plain(text)]);
    });

    it('holds a word of the API, the one that writes it', () => {
      const constants = readFileSync(
        resolve(__dirname, '../../../../api/src/core/constants.py'),
        'utf8'
      );

      expect(constants).toContain(`HTML_TEXT_LINK_LABEL: str = "${WRITTEN_LINK_LABEL}"`);
    });
  });

  describe('an address as a person wrote it', () => {
    it('keeps its words', () => {
      expect(linkSegments('See https://example.org/docs/page now')).toEqual([
        plain('See '),
        link('https://example.org/docs/page', 'https://example.org/docs/page'),
        plain(' now'),
      ]);
    });

    it('reads a www address as https', () => {
      expect(linkSegments('www.example.org')).toEqual([
        link('www.example.org', 'https://www.example.org/'),
      ]);
    });

    it('links a mailto and a tel address', () => {
      expect(linkSegments('mailto:ana@example.org tel:+33123456789')).toEqual([
        link('mailto:ana@example.org', 'mailto:ana@example.org'),
        plain(' '),
        link('tel:+33123456789', 'tel:+33123456789'),
      ]);
    });

    it.each(['.', ',', ';', ':', '!', '?', '»', '"'])('leaves out a closing %s', mark => {
      expect(linkSegments(`https://example.org/a${mark}`)).toEqual([
        link('https://example.org/a', 'https://example.org/a'),
        plain(mark),
      ]);
    });

    it('leaves out a parenthesis that closes the sentence', () => {
      expect(linkSegments('(see https://example.org/a).')).toEqual([
        plain('(see '),
        link('https://example.org/a', 'https://example.org/a'),
        plain(').'),
      ]);
    });

    it('keeps a parenthesis that belongs to it', () => {
      expect(linkSegments('https://example.org/wiki/A_(b)')).toEqual([
        link('https://example.org/wiki/A_(b)', 'https://example.org/wiki/A_(b)'),
      ]);
    });

    it('stops at a markup character', () => {
      expect(linkSegments('<https://example.org/a>')).toEqual([
        plain('<'),
        link('https://example.org/a', 'https://example.org/a'),
        plain('>'),
      ]);
    });

    it('finds several, in order', () => {
      expect(linksOf('https://a.example.org then www.b.example.org').map(item => item.href)).toEqual(
        ['https://a.example.org/', 'https://www.b.example.org/']
      );
    });
  });

  describe('what is not an address', () => {
    it.each([
      'javascript:alert(1)',
      'ftp://example.org/a',
      'https://bank.example@evil.example/',
      'awww.example.org',
      'xhttps://example.org',
      'foo.www.example.org',
      'ana@www.example.org',
      'www.',
      'www.example',
      'https://',
      'hotel:1234',
      'Tel: 01 23 45 67 89',
      'mailto:nobody',
    ])('stays words: %s', text => {
      expect(linksOf(text)).toEqual([]);
      expect(
        linkSegments(text)
          .map(segment => segment.text)
          .join('')
      ).toBe(text);
    });
  });
});
