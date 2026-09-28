/**
 * Character references read as the chat reads them — the browser's twin of
 * `read_as_markdown` (ADR-323 review 14).
 *
 * The voice projection corpus pins the twins to each other through
 * `flattenForVoice`; these cases pin the reader alone, with the flatteners a
 * surface hands it: a reference is its character outside code and typed text
 * inside it, what it spells never reaches the flattener, an `&` that opens no
 * reference is an `&`, and the reading is one-to-one.
 */

import { describe, expect, it } from 'vitest';

import { decodeReference, readAsMarkdown } from '../markdown-references';

const REPLACEMENT = String.fromCodePoint(0xfffd);

describe('readAsMarkdown', () => {
  it.each([
    ['numeric', 'tape &#233; ici', 'tape é ici'],
    ['hexadecimal and single pass', '&#x2F;&amp;lt;', '/&lt;'],
    ['invalid', '&#0; &#xD800; &#1114112;', `${REPLACEMENT} ${REPLACEMENT} ${REPLACEMENT}`],
    ['not references', '&unknownname; &copy=2 &', '&unknownname; &copy=2 &'],
    ['card values', 'Réunion &#60;lundi&#62; &#91;v2&#93;', 'Réunion <lundi> [v2]'],
  ])('reads references as the chat does (%s)', (_, text, read) => {
    expect(readAsMarkdown(text)).toBe(read);
  });

  it('keeps a named reference outside its six as typed — the documented divergence', () => {
    expect(readAsMarkdown('&eacute; &nbsp;')).toBe(`&eacute; ${String.fromCodePoint(0xa0)}`);
  });

  it('keeps a reference in code as typed', () => {
    const text = 'tape `&#91;` et\n```\n&#42;x&#42; &lt;\n```\npuis &#42;';

    expect(readAsMarkdown(text)).toBe('tape `&#91;` et\n```\n&#42;x&#42; &lt;\n```\npuis *');
  });

  it('keeps an unclosed fence as typed to the end of the text', () => {
    expect(readAsMarkdown('avant &#42;\n~~~\n&#42; reste')).toBe('avant *\n~~~\n&#42; reste');
  });

  it('never hands the flattener what the references spell', () => {
    const seen: string[] = [];
    const flatten = (text: string): string => {
      seen.push(text);
      return text.replace(/<[^>]+>/g, '').replaceAll('**', '');
    };

    const read = readAsMarkdown('<p>Réunion &#60;lundi&#62; &#42;&#42;x&#42;&#42;</p>', flatten);

    expect(read).toBe('Réunion <lundi> **x**');
    expect(seen[0]).not.toMatch(/&|<lundi>|\*\*/);
  });

  it('never hands an HTML decoder a bare ampersand', () => {
    const htmlDecoder = (text: string): string => text.replaceAll('&copy', '©');

    expect(readAsMarkdown('<p>x</p> ?id=7&copy=2&not=1', htmlDecoder)).toBe(
      '<p>x</p> ?id=7&copy=2&not=1'
    );
  });

  it('keeps the marks of a bare URL', () => {
    const flatten = (text: string): string => text.replace(/[*_~]/g, '');

    expect(readAsMarkdown('voir https://a.example/x_y*z* et *gras*', flatten)).toBe(
      'voir https://a.example/x_y*z* et gras'
    );
  });

  it('writes what it kept back through the surface', () => {
    const escapeHtml = (char: string): string =>
      ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' })[char] ?? char;

    expect(readAsMarkdown('a &#60;b&#62; & c', text => text, escapeHtml)).toBe(
      'a &lt;b&gt; &amp; c'
    );
  });

  it('reads one-to-one, the reserved block included', () => {
    const raw = [0xf003c, 0xf003e, 0xf0080, 0xf0100]
      .map(code => String.fromCodePoint(code))
      .join(' ');

    expect(readAsMarkdown(raw)).toBe(raw);
    expect(readAsMarkdown('&#983100;')).toBe(String.fromCodePoint(0xf003c));
  });
});

describe('decodeReference', () => {
  type Parts = [
    decimal: string | undefined,
    hexadecimal: string | undefined,
    name: string | undefined,
  ];
  const cases: [Parts, string | null][] = [
    [['36', undefined, undefined], '$'],
    [[undefined, '24', undefined], '$'],
    [[undefined, undefined, 'amp'], '&'],
    [[undefined, undefined, 'eacute'], null],
    [['0', undefined, undefined], REPLACEMENT],
    [[undefined, 'D800', undefined], REPLACEMENT],
    [['1114112', undefined, undefined], REPLACEMENT],
  ];

  it.each(cases)('decodes %j as %j', ([decimal, hexadecimal, name], expected) => {
    expect(decodeReference(decimal, hexadecimal, name)).toBe(expected);
  });
});
