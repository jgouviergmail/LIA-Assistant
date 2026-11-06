/**
 * What a message becomes before the Markdown parser reads it.
 *
 * A `lia-response` answer is HTML, and CommonMark ends an HTML block at its
 * first blank line: a blank line inside a `<pre>` cut the code in two
 * (measured 2026-11-04: 24 of the 48 code blocks stored in production).
 */
import { describe, expect, it } from 'vitest';

import { prepareMarkdownSource } from '../markdown-source';

const answer = (code: string) =>
  `<div class="lia-response">\n<p>Voici.</p>\n<pre><code class="language-js">${code}</code></pre>\n<p>Fin.</p>\n</div>`;

describe('prepareMarkdownSource — an answer', () => {
  it('leaves no blank line inside a <pre>, so CommonMark cannot end the block there', () => {
    const prepared = prepareMarkdownSource(answer('a();\n\n  b();\n\nc();\n'), false);
    expect(prepared).toContain('a();&#10;&#10;  b();&#10;&#10;c();&#10;');
    expect(prepared).not.toMatch(/<pre[^]*\n[^]*<\/pre>/);
  });

  it('protects every <pre> of the answer', () => {
    const two = `<div class="lia-response">\n<pre><code>a\n\nb</code></pre>\n<p>x</p>\n<pre><code>c\n\nd</code></pre>\n</div>`;
    const prepared = prepareMarkdownSource(two, false);
    expect(prepared).toContain('a&#10;&#10;b');
    expect(prepared).toContain('c&#10;&#10;d');
  });

  it('protects a <pre> still being streamed, with no closing tag yet', () => {
    const streamed = '<div class="lia-response">\n<pre><code class="language-js">a();\n\nb();';
    expect(prepareMarkdownSource(streamed, false)).toContain('a();&#10;&#10;b();');
  });

  it('keeps the structure around the block on its own lines', () => {
    const prepared = prepareMarkdownSource(answer('a\n\nb'), false);
    expect(prepared).toContain('<p>Voici.</p>\n<pre>');
    expect(prepared).toContain('</pre>\n<p>Fin.</p>');
  });

  it('accepts an uppercase tag and a tag carrying attributes', () => {
    const prepared = prepareMarkdownSource(
      '<div class="lia-response">\n<PRE class="x"><code>a\n\nb</code></PRE>\n</div>',
      false
    );
    expect(prepared).toContain('a&#10;&#10;b');
  });

  it('leaves the attributes of a tag written over several lines alone', () => {
    const prepared = prepareMarkdownSource(
      '<div class="lia-response">\n<pre\n  class="x"><code>a\n\nb</code></pre>\n</div>',
      false
    );
    expect(prepared).toContain('<pre\n  class="x"><code>a&#10;&#10;b');
  });

  it('never rewrites a fence that quotes a <pre>, even inside an HTML answer', () => {
    const quoted = '<p>Exemple :</p>\n\n```html\n<pre>\n\nligne\n</pre>\n```\n';
    expect(prepareMarkdownSource(quoted, false)).toContain('<pre>\n\nligne\n</pre>');
  });

  it('never rewrites a Markdown answer: only an HTML answer carries this risk', () => {
    const markdown = 'Texte\n\n<pre>\n\nligne\n</pre>\n';
    expect(prepareMarkdownSource(markdown, false)).toBe(markdown);
  });

  it('still de-indents the structural lines of a pretty-printed answer', () => {
    const indented = '<div class="lia-response">\n\n    <h2>Titre</h2>\n</div>';
    expect(prepareMarkdownSource(indented, false)).toContain('\n<h2>Titre</h2>');
  });

  it('keeps the indentation of a multi-line inline code span', () => {
    const inline = '<div class="lia-response">\n<p><code>a\n    b</code></p>\n</div>';
    expect(prepareMarkdownSource(inline, false)).toContain('a\n    b');
  });

  it('still repairs a tag glued to an emoji', () => {
    expect(prepareMarkdownSource('<ul><li📧 class="x">a</li></ul>', false)).toContain(
      '<li class="x">📧a'
    );
  });
});

describe('prepareMarkdownSource — mathematics', () => {
  it('still normalizes the math notations of prose', () => {
    expect(prepareMarkdownSource('Soit \\(x\\) et \\[y\\].', false)).toBe('Soit $x$ et $$y$$.');
  });

  it('never turns a regex of a <pre> into a formula', () => {
    const prepared = prepareMarkdownSource(
      answer('const r = /\\(a\\)/;\nconst t = /\\[b\\]/;'),
      false
    );
    expect(prepared).toContain('/\\(a\\)/');
    expect(prepared).toContain('/\\[b\\]/');
  });

  it('never turns the content of an inline <code> into a formula', () => {
    const prepared = prepareMarkdownSource(
      '<div class="lia-response">\n<p>Échappez <code>\\(</code> puis <code>\\)</code>.</p>\n</div>',
      false
    );
    expect(prepared).toContain('<code>\\(</code>');
    expect(prepared).toContain('<code>\\)</code>');
  });

  it('still converts the prose beside a code block', () => {
    const prepared = prepareMarkdownSource(
      '<div class="lia-response">\n<p>Soit \\(x\\).</p>\n<pre><code>\\(y\\)</code></pre>\n</div>',
      false
    );
    expect(prepared).toContain('Soit $x$.');
    expect(prepared).toContain('\\(y\\)');
  });
});

describe('prepareMarkdownSource — what a person typed', () => {
  it('reaches the parser as typed: no block tag at its start is structure', () => {
    const typed = '<div>\n\n    <p>mon code</p>\n</div>';
    expect(prepareMarkdownSource(typed, true)).toBe(typed);
  });

  it('never repairs a tag it did not write', () => {
    const typed = 'la balise <li📧> est cassée';
    expect(prepareMarkdownSource(typed, true)).toBe(typed);
  });

  it('never rewrites a <pre> a person pasted', () => {
    const typed = '<div>\n<pre>\n\na\n</pre>\n</div>';
    expect(prepareMarkdownSource(typed, true)).toBe(typed);
  });

  it('keeps the math notations a person types', () => {
    expect(prepareMarkdownSource('Soit \\(x\\).', true)).toBe('Soit $x$.');
  });
});
