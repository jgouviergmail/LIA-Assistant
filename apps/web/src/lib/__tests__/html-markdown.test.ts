/**
 * html-markdown — an assistant HTML fragment written as Markdown for a file.
 *
 * The `.md` a person downloads or sends by e-mail must keep the layout they
 * read in the chat: headings, emphasis, links, lists, tables, code, quotes —
 * and the LIA components drawn as their Markdown equivalents. What only makes
 * sense on screen (icons, buttons, folds' « see more », widget placeholders)
 * never reaches the file. Every input below is either the real corpus
 * (`fixtures/assistant-html-corpus.ts`) or the smallest markup showing one rule.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { htmlToMarkdown } from '../html-markdown';
import {
  ARCHIVED_HTML_ANSWER,
  CONTACT_CARD,
  DIRECTIVE_COMPONENTS,
  EMAIL_CARD,
  EVENT_CARD,
  ROUTE_CARD,
  WEATHER_CARD,
} from './fixtures/assistant-html-corpus';

/** French label punctuation: a no-break space before the colon. */
const FR = { labelSeparator: '\u00a0: ' };

/** The Markdown of one paragraph of markup. */
function md(html: string): string {
  return htmlToMarkdown(html, FR);
}

describe('an archived lia-response answer', () => {
  const out = md(ARCHIVED_HTML_ANSWER);

  it('keeps every heading at its level', () => {
    expect(out).toContain('\n# Synthèse des dernières actualités de Next.js\n');
    expect(out).toContain('\n## 1. Versions récentes et cycle de publication\n');
    expect(out).toContain('\n### Confirmées (Next.js 15.x)\n');
  });

  it('keeps emphasis, inline code and a deliberate line break', () => {
    expect(out).toContain('ton fichier `package.json`.');
    expect(out).toContain('**Next.js 15 (stable) — octobre 2024**  \nDernière version majeure');
    expect(out).toContain('le *Pages Router*.');
  });

  it('writes a tight bulleted list, code and emphasis inside the items', () => {
    expect(out).toContain(
      '- **React 19 support natif** : Actions serveur (`"use server"`), hooks comme `use()` pour les promesses.\n' +
        "- **`next/after`** : API pour exécuter du code après l'envoi de la réponse."
    );
  });

  it('writes the table as a GFM table with its header row', () => {
    expect(out).toContain(
      [
        '| Tendance | Direction observée |',
        '| --- | --- |',
        '| **Server-first** | Next.js pousse résolument vers le serveur (Server Components, Server Actions, PPR). |',
        '| **Rust dans la toolchain** | Turbopack (Rust), SWC (Rust) pour la compilation. |',
      ].join('\n')
    );
  });

  it('keeps the quote, the rule and the link target', () => {
    expect(out).toContain("> **L'œil de LIA :** En gros, Vercel continue");
    expect(out).toContain('\n---\n');
    expect(out).toContain(
      '- 🔍 [Consulter directement les dernières releases sur GitHub](https://github.com/vercel/next.js/releases) pour voir'
    );
  });

  it('leaks no markup and no blank-line run', () => {
    expect(out).not.toMatch(/<\/?[a-z]/i);
    expect(out).not.toMatch(/\n{3,}/);
    expect(out).toBe(out.trim());
  });
});

describe('the lia-response components of the HTML directive', () => {
  const out = md(DIRECTIVE_COMPONENTS);

  it('draws the stat tiles as a table: labels over values', () => {
    expect(out).toContain(
      '| p99 latency | records synced | regressions |\n| --- | --- | --- |\n| 4.2 ms | 1.8M | 0 |'
    );
  });

  it('draws the key-value list with the reader’s label punctuation, chip icons dropped', () => {
    expect(out).toContain('- **Status**\u00a0: Active\n- **Region**\u00a0: **eu-west-1**');
    expect(out).not.toContain('check_circle');
  });

  it('numbers the steps', () => {
    expect(out).toContain(
      '1. Place the primary instance into read-only replication mode.\n2. Promote the hot-standby replica'
    );
  });

  it('fences the code with its language, entities decoded, indentation kept', () => {
    expect(out).toContain(
      '```python\nif current_replicas < target_replicas and health_status == "OK":\n    scale_cluster(target_replicas)\n```'
    );
  });

  it('keeps an authored fold: its summary as a bold line above its body', () => {
    expect(out).toContain('**Rollback plan**\n\nRe-point DNS to the *legacy* primary.');
  });

  it('draws a callout as a GFM alert of its severity, title first', () => {
    expect(out).toContain(
      '> [!WARNING]\n> **Connection drain latency**\n>\n> Allow at least **30 seconds** after DNS propagation'
    );
  });

  it('maps each callout severity to its alert', () => {
    const alert = (variant: string) =>
      md(`<div class="lia-callout lia-callout-${variant}"><p>x</p></div>`).split('\n')[0];

    expect(alert('info')).toBe('> [!NOTE]');
    expect(alert('success')).toBe('> [!TIP]');
    expect(alert('warning')).toBe('> [!WARNING]');
    expect(alert('error')).toBe('> [!CAUTION]');
    expect(md('<div class="lia-callout"><p>x</p></div>').split('\n')[0]).toBe('> [!NOTE]');
  });
});

describe('the data cards', () => {
  it('opens an event card on its linked title, chips on one line, no screen-only text', () => {
    const out = md(EVENT_CARD);

    expect(out.startsWith('### [Revue de sprint](https://calendar.google.com/x)\n\n')).toBe(true);
    expect(out).toContain('lundi 28 septembre · 12:00 - 13:00 · 1h');
    expect(out).toContain('Ordre du jour : démo, rétro');
    expect(out).toContain('- Organisé par [Alice](mailto:alice@example.com) alice@example.com');
    expect(out).toContain('**Participants**\n\n- [Bob](mailto:bob@example.com) bob@example.com');
    // Icons, the fold's trigger, the avatar initial and the action buttons are screen-only.
    for (const screenOnly of ['calendar_month', 'schedule', 'expand_more', 'Voir', 'Itinéraire']) {
      expect(out).not.toContain(screenOnly);
    }
    expect(out).not.toMatch(/^- B$/m);
  });

  it('keeps a title with no target as plain text, and joins a detail to its type', () => {
    const out = md(CONTACT_CARD);

    expect(out.startsWith('### Marie Curie\n\nInstitut Radium · Directrice\n\n')).toBe(true);
    expect(out).toContain(
      '- [marie@example.com](mailto:marie@example.com) · Travail\n- [01.23.45.67.89](tel:+33123456789) · Mobile'
    );
    expect(out).not.toContain('[Marie Curie]');
  });

  it('drops an e-mail card’s buttons and status icons, keeps its subject and attachment', () => {
    const out = md(EMAIL_CARD);

    expect(out.startsWith('### [Compta](mailto:compta@example.com)\n\n')).toBe(true);
    // A bare count means « attachments » only beside its paperclip.
    expect(out).toContain('\n📎 1\n');
    expect(out).toContain('[Facture septembre](https://mail.google.com/mail/u/0/#all/m1)');
    expect(out).toContain('Veuillez trouver ci-joint la facture');
    expect(out).toContain('- facture.pdf (12.1KB)');
    for (const screenOnly of ['Rép.', 'Transf.', 'Supp.', 'mark_email_unread', 'pièce jointe']) {
      expect(out).not.toContain(screenOnly);
    }
  });

  it('puts the weather card’s city first, and labels each measure', () => {
    const out = md(WEATHER_CARD);

    expect(out.startsWith('### Paris\n\n')).toBe(true);
    expect(out).toContain("Aujourd'hui");
    expect(out).toContain('- Ressenti\u00a0: 10°C\n- Humidité\u00a0: 45%');
    expect(out).not.toContain('Prévisions');
  });

  it('labels a route’s endpoints and keeps its steps', () => {
    const out = md(ROUTE_CARD);

    expect(out).toContain('Modéré · 18 min · 4.2 km');
    expect(out).toContain('- Départ\u00a0: Bastille\n- Arrivée\u00a0: Gare de Lyon');
    expect(out).toContain('- 1 Prendre la rue de Lyon');
    expect(out).not.toContain('Ouvrir dans Maps');
  });

  it('separates two cards by ONE rule, and opens and closes on none', () => {
    const out = md(EVENT_CARD + CONTACT_CARD);

    expect(out.match(/^---$/gm)).toHaveLength(1);
    expect(out).toMatch(/1 participant[\s\S]*\n\n---\n\n### Marie Curie/);
    expect(out.startsWith('---')).toBe(false);
    expect(out.endsWith('---')).toBe(false);
  });
});

describe('lists', () => {
  it('indents a nested list under its item, tightly', () => {
    expect(md('<ul><li>A<ul><li>A1</li><li>A2</li></ul></li><li>B</li></ul>')).toBe(
      '- A\n  - A1\n  - A2\n- B'
    );
  });

  it('indents under an ordered marker by the marker’s width', () => {
    expect(md('<ol><li>Un<ul><li>détail</li></ul></li></ol>')).toBe('1. Un\n   - détail');
  });

  it('keeps a hard break inside an item, the continuation indented under it', () => {
    expect(md('<ul><li>Adresse<br>Paris</li><li>Suite</li></ul>')).toBe(
      '- Adresse  \n  Paris\n- Suite'
    );
  });

  it('keeps a list a model nested outside its item, under the item before it', () => {
    expect(md('<ol><li>Un</li><ul><li>détail</li></ul><li>Deux</li></ol>')).toBe(
      '1. Un\n   - détail\n2. Deux'
    );
  });

  it('continues from the start the list declares', () => {
    expect(md('<ol start="3"><li>c</li><li>d</li></ol>')).toBe('3. c\n4. d');
  });

  it('keeps several paragraphs of one item inside that item', () => {
    expect(md('<ul><li><p>Premier</p><p>Suite</p></li><li>Second</li></ul>')).toBe(
      '- Premier\n\n  Suite\n- Second'
    );
  });
});

describe('text written as Markdown stays the text it was', () => {
  it('escapes what would start a Markdown block', () => {
    expect(md('<p># pas un titre</p>')).toBe('\\# pas un titre');
    expect(md('<p>1. pas une liste</p>')).toBe('1\\. pas une liste');
    expect(md('<p>- pas une puce</p>')).toBe('\\- pas une puce');
    expect(md('<p>&gt; pas une citation</p>')).toBe('\\> pas une citation');
  });

  it('escapes a line that would underline the one above it, or open a code fence', () => {
    expect(md('<p>Titre ?<br>-</p>')).toBe('Titre ?  \n\\-');
    expect(md('<p>Titre ?<br>==</p>')).toBe('Titre ?  \n\\==');
    expect(md('<p>~~~ pas du code</p>')).toBe('\\~~~ pas du code');
  });

  it('escapes a quoted tag, so a viewer shows it instead of parsing it', () => {
    expect(md('<p>La balise &lt;div&gt; ouvre un bloc</p>')).toBe(
      'La balise \\<div> ouvre un bloc'
    );
  });

  it('escapes literal emphasis marks, and leaves arithmetic and math alone', () => {
    expect(md('<p>un *vrai* mot, 2 * 3 et $a*b_1$</p>')).toBe(
      'un \\*vrai\\* mot, 2 * 3 et $a*b_1$'
    );
  });

  it('keeps an underscore inside a word, escapes one that could open emphasis', () => {
    expect(md('<p>snake_case et _souligné_</p>')).toBe('snake_case et \\_souligné\\_');
  });

  it('escapes a pipe inside a table cell and turns a break into <br>', () => {
    expect(
      md('<table><tr><th>A</th></tr><tr><td>x | y<br>z</td></tr></table>').split('\n')[2]
    ).toBe('| x \\| y<br>z |');
  });

  it('never joins a chip across a line break', () => {
    expect(
      md('<p><span class="lia-chip">Lundi</span><br><span class="lia-chip">Mardi</span></p>')
    ).toBe('Lundi  \nMardi');
  });

  it('keeps a no-break space (French typography) where HTML put one', () => {
    expect(md('<p>Prix&nbsp;: 5&nbsp;€</p>')).toBe('Prix\u00a0: 5\u00a0€');
  });

  it('moves the spaces inside an emphasis outside its marks', () => {
    expect(md('<p><strong>Gras </strong>suite et <em> fin</em></p>')).toBe(
      '**Gras** suite et *fin*'
    );
  });

  it('drops an emphasis around nothing', () => {
    expect(md('<p>a<strong> </strong>b</p>')).toBe('a b');
  });
});

describe('tables and definition lists at their edges', () => {
  it('keeps the columns aligned under a spanning cell, and titles the table by its caption', () => {
    expect(
      md(
        '<table><caption>Budget</caption><thead><tr><th>Poste</th><th>T1</th><th>T2</th></tr></thead>' +
          '<tbody><tr><td colspan="2">Total</td><td>9</td></tr><tr><td>Seul</td></tr></tbody></table>'
      )
    ).toBe(
      '**Budget**\n\n| Poste | T1 | T2 |\n| --- | --- | --- |\n| Total |  | 9 |\n| Seul |  |  |'
    );
  });

  it('reads a malformed colspan as one cell', () => {
    expect(md('<table><tr><th colspan="x">A</th><th>B</th></tr></table>').split('\n')[0]).toBe(
      '| A | B |'
    );
  });

  it('keeps a pipe in a cell link from ending the cell', () => {
    expect(
      md('<table><tr><th>A</th></tr><tr><td><a href="https://a.fr/?q=a|b">q</a></td></tr></table>')
    ).toContain('| [q](https://a.fr/?q=a%7Cb) |');
  });

  it('reads the terms a div groups with their values', () => {
    expect(
      md('<dl><div><dt>Lieu</dt><dd>B</dd></div><div><dt>Heure</dt><dd>14 h</dd></div></dl>')
    ).toBe('- **Lieu**\u00a0: B\n- **Heure**\u00a0: 14 h');
  });

  it('writes nothing for a table without a single cell', () => {
    expect(md('<p>Avant</p><table><tr></tr></table><p>Après</p>')).toBe('Avant\n\nAprès');
  });

  it('keeps a term without its value, and a value without its term', () => {
    expect(md('<dl><dt>Seul</dt><dt>Terme</dt><dd>valeur</dd><dd>1. autre</dd></dl>')).toBe(
      '- **Seul**\n- **Terme**\u00a0: valeur\n- 1\\. autre'
    );
  });
});

describe('links and code', () => {
  it('writes struck-through text with GFM tildes', () => {
    expect(md('<p><del>ancien</del> <s>prix</s></p>')).toBe('~~ancien~~ ~~prix~~');
  });

  it('keeps only a link a file can follow', () => {
    expect(md('<p><a href="javascript:alert(1)">x</a></p>')).toBe('x');
    expect(md('<p><a href="/api/v1/attachments/1">fichier</a></p>')).toBe('fichier');
    expect(md('<p><a href="#top">haut</a></p>')).toBe('haut');
    expect(md('<p><a href="https://a.fr/p">page</a></p>')).toBe('[page](https://a.fr/p)');
  });

  it('writes a bare URL as an autolink, and brackets a target with a space', () => {
    expect(md('<p><a href="https://x.fr">https://x.fr</a></p>')).toBe('<https://x.fr>');
    expect(md('<p><a href="https://a.fr/c d">t</a></p>')).toBe('[t](<https://a.fr/c d>)');
  });

  it('escapes brackets in a link text, and nowhere else', () => {
    expect(md('<p><a href="https://a.fr">[1] note</a></p>')).toBe('[\\[1\\] note](https://a.fr)');
    expect(md('<p>voir [1]</p>')).toBe('voir [1]');
    expect(md('<p><a href="#top">[1] haut</a></p>')).toBe('[1] haut');
  });

  it('escapes a backslash where Markdown would read it, and keeps a path', () => {
    // A backslash before a mark used to reach the file as written: Markdown
    // read it as the escape of the mark, and both vanished from the render.
    expect(md('<p>a\\*b</p>')).toBe('a\\\\\\*b');
    expect(md('<p>C:\\Users\\jo</p>')).toBe('C:\\Users\\jo');
    // In a link, `a\]b` used to become `a\\]b`: a literal backslash, then the
    // bracket ending the text (CodeQL js/incomplete-sanitization).
    expect(md('<p><a href="https://a.fr">a\\]b</a></p>')).toBe('[a\\\\\\]b](https://a.fr)');
  });

  it('drops a link with no text', () => {
    expect(md('<p>avant<a href="https://a.fr"><img src="x.png"></a> après</p>')).toBe(
      'avant après'
    );
  });

  it('fences inline code around the backticks it holds', () => {
    expect(md('<p><code>a`b</code></p>')).toBe('``a`b``');
    expect(md('<p><code>`x</code></p>')).toBe('`` `x ``');
  });

  it('opens a code block with a longer fence than any it contains', () => {
    expect(md('<pre><code>```\nx\n```</code></pre>')).toBe('````\n```\nx\n```\n````');
  });

  it('fences a bare pre without a language', () => {
    expect(md('<pre>  indenté\nligne</pre>')).toBe('```\n  indenté\nligne\n```');
  });
});

describe('what never reaches a file', () => {
  it('drops images, scripts, styles and form controls', () => {
    expect(
      md(
        '<p>Texte<img src="https://x/y.png" alt="photo"></p><style>.a{}</style><script>alert(1)</script><button>OK</button>'
      )
    ).toBe('Texte');
  });

  it('answers an empty string for markup that holds nothing', () => {
    expect(
      md('<div class="lia-response"><span class="material-symbols-outlined">event</span></div>')
    ).toBe('');
  });
});

describe('where no DOM parser exists', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('falls back to the plain-text flattening rather than throwing', () => {
    vi.stubGlobal('DOMParser', undefined);

    expect(md('<div class="lia-response"><h2>Titre</h2><p>Corps</p></div>')).toBe('Titre\n\nCorps');
  });
});
