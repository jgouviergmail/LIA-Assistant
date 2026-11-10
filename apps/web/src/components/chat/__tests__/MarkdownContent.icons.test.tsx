import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SRC_ROOT } from '@/__tests__/source-scan';
import { IconStyleContext } from '@/lib/icon-style-context';
import * as archivedCards from '@/lib/__tests__/fixtures/assistant-html-corpus';
import { MarkdownContent } from '../MarkdownContent';
import { MaterialSymbol } from '../markdown-icon-span';
import { MATERIAL_SYMBOL_ICONS } from '../material-symbol-icons';

// Read at collection: this is the backend's declared vocabulary, not a copied
// list a new card could silently outgrow. Raw literal names are also exercised
// by the captured producer corpus below and by the public-font guard.
const iconSource = readFileSync(
  join(SRC_ROOT, '../../api/src/domains/agents/display/icons.py'),
  'utf8'
);

function declaredSymbols(source: string): string[] {
  const body = source.split('class Icons:')[1]?.split('\n# ====')[0] ?? '';
  return [...body.matchAll(/^    [A-Z_]+ = "([a-z0-9_]+)"/gm)].map(match => match[1]);
}

const marker = (name: string) => `<span class="material-symbols-outlined">${name}</span>`;

describe('account icon styles in archived HTML', () => {
  it('updates a memoized answer when the account changes style', () => {
    const content = `<p>${marker('mail')}A saved message</p>`;
    const show = (style: 'lucide' | 'fluent' | 'flex') => (
      <IconStyleContext.Provider value={style}>
        <MarkdownContent content={content} />
      </IconStyleContext.Provider>
    );
    const { container, rerender } = render(show('fluent'));
    for (const style of ['fluent', 'flex', 'lucide'] as const) {
      rerender(show(style));
      expect(screen.getByText('A saved message')).toBeInTheDocument();
      expect(container.querySelector('svg')).toHaveAttribute('data-icon-style', style);
      expect(container.querySelector('.material-symbols-outlined')?.textContent).toBe('');
      expect(container.querySelector('.material-symbols-outlined')).toHaveAttribute(
        'aria-hidden',
        'true'
      );
    }
  });

  it('covers every declared backend symbol and proves the census detects a new one', () => {
    const names = declaredSymbols(iconSource);
    expect(names).toContain('mail');
    expect(names).toContain('visibility');
    expect(names.filter(name => !Object.hasOwn(MATERIAL_SYMBOL_ICONS, name))).toEqual([]);
    expect(declaredSymbols('class Icons:\n    FUTURE = "new_symbol"\n# ====')).toEqual([
      'new_symbol',
    ]);
    expect(Object.hasOwn(MATERIAL_SYMBOL_ICONS, 'new_symbol')).toBe(false);
  });

  it('renders trusted SVG artwork for every mapped ligature', () => {
    const names = Object.keys(MATERIAL_SYMBOL_ICONS);
    const { container } = render(
      <MarkdownContent content={`<div>${names.map(marker).join('')}</div>`} />
    );
    expect(container.querySelectorAll('.lia-symbol-icon > svg')).toHaveLength(names.length);
    expect(container.textContent).toBe('');
  });

  it.each(['lucide', 'fluent', 'flex'] as const)(
    'preserves full, half and empty rating/favorite states in %s',
    style => {
      render(
        <IconStyleContext.Provider value={style}>
          {['star', 'star_half', 'star_outline', 'favorite', 'favorite_border'].map(name => (
            <MaterialSymbol key={name} name={name} title={name} />
          ))}
        </IconStyleContext.Provider>
      );
      for (const name of ['star', 'star_half', 'favorite']) {
        expect(screen.getByTitle(name).querySelector('svg')).toHaveAttribute(
          'fill',
          'currentColor'
        );
      }
      for (const name of ['star_outline', 'favorite_border']) {
        expect(screen.getByTitle(name).querySelector('svg')).toHaveAttribute('fill', 'none');
      }
      const full = screen.getByTitle('star').querySelector('path')?.getAttribute('d');
      const half = screen.getByTitle('star_half').querySelector('path')?.getAttribute('d');
      expect(full).toBeTruthy();
      expect(half).toBeTruthy();
      expect(half).not.toBe(full);
      // The semantic body must inherit the root's state; colored accents may
      // keep their own paint without turning an empty heart into a full one.
      const emptyHeart = screen.getByTitle('favorite_border').querySelector('svg');
      if (style === 'lucide') {
        expect(emptyHeart?.querySelector('path')).not.toHaveAttribute('fill');
      } else {
        expect(emptyHeart?.querySelector('[fill="inherit"]')).toBeInTheDocument();
      }
    }
  );

  it('covers the card symbols captured from real producers', () => {
    const names = new Set<string>();
    for (const html of Object.values(archivedCards)) {
      if (typeof html !== 'string') continue;
      for (const match of html.matchAll(/material-symbols-outlined[^>]*>\s*([a-z0-9_]+)\s*</g)) {
        names.add(match[1]);
      }
    }
    expect(names).toContain('directions_car');
    expect(names).toContain('thermostat');
    expect([...names].filter(name => !Object.hasOwn(MATERIAL_SYMBOL_ICONS, name))).toEqual([]);
  });

  it.each(['lucide', 'fluent', 'flex'] as const)(
    'keeps opposite fork directions distinct in %s',
    style => {
      render(
        <IconStyleContext.Provider value={style}>
          <MaterialSymbol name="fork_left" title="left fork" />
          <MaterialSymbol name="fork_right" title="right fork" />
        </IconStyleContext.Provider>
      );
      const left = screen.getByTitle('left fork').querySelector('svg');
      const right = screen.getByTitle('right fork').querySelector('svg');
      expect(left).toHaveAttribute('data-icon-name', 'Split');
      expect(right).toHaveAttribute('data-icon-name', 'Split');
      expect(left?.querySelector('path')).toBeTruthy();
      expect(right).toHaveStyle({ transform: 'scaleX(-1)' });
      expect(left).not.toHaveStyle({ transform: 'scaleX(-1)' });
    }
  );

  it.each(['unknown_archived_symbol', 'constructor', 'toString'])(
    'retains the historical font fallback for %s without treating object properties as icons',
    name => {
      const { container } = render(<MaterialSymbol name={name} />);
      expect(container).toHaveTextContent(name);
      expect(container.querySelector('svg')).toBeNull();
    }
  );

  it('repaints unknown historical glyphs without replacing their text or accepting artwork', () => {
    const show = (style: 'lucide' | 'fluent' | 'flex') => (
      <IconStyleContext.Provider value={style}>
        <MaterialSymbol name="unknown_archived_symbol" title="historical symbol" />
      </IconStyleContext.Provider>
    );
    const { rerender } = render(show('lucide'));
    for (const style of ['lucide', 'fluent', 'flex', 'lucide'] as const) {
      rerender(show(style));
      const symbol = screen.getByTitle('historical symbol');
      expect(symbol).toHaveTextContent('unknown_archived_symbol');
      expect(symbol).toHaveAttribute('data-icon-style', style);
      expect(symbol).toHaveAttribute('aria-hidden', 'true');
      expect(symbol.querySelector('svg')).toBeNull();
      expect(symbol.classList.contains('lia-symbol-legacy-color')).toBe(style !== 'lucide');
    }
  });

  it('never admits supplied SVG or executable markup through the enhancement', () => {
    const { container } = render(
      <MarkdownContent
        content={`<svg onload="alert(1)"><script>alert(2)</script></svg><span class="material-symbols-outlined" onclick="alert(3)">mail</span>`}
      />
    );
    expect(container.querySelectorAll('svg')).toHaveLength(1);
    expect(container.querySelector('script, [onclick], [onload]')).toBeNull();
    expect(container.querySelector('svg')).toHaveAttribute('data-icon-name', 'Mail');
  });

  it('keeps a person’s literal markup as text and ordinary spans intact', () => {
    const { container, rerender } = render(<MarkdownContent content={marker('mail')} isUser />);
    expect(container.querySelector('svg')).toBeNull();
    expect(container).toHaveTextContent(marker('mail'));
    rerender(<MarkdownContent content='<span class="lia-card-text">mail</span>' />);
    expect(container.querySelector('.lia-card-text')).toHaveTextContent('mail');
    expect(container.querySelector('svg')).toBeNull();
  });

  it('keeps nested content in a malformed icon marker rather than discarding it', () => {
    const { container } = render(
      <MarkdownContent content='<span class="material-symbols-outlined"><b>Important text</b></span>' />
    );
    expect(screen.getByText('Important text')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeNull();
  });
});
