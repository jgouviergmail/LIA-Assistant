import { createRef } from 'react';
import { fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Calendar, Circle, Heart, Home, MessageSquare, Pin, Square, Star } from '@/lib/icons';
import * as applicationIcons from '@/lib/icons';
import { IconStyleContext } from '@/lib/icon-style-context';
import { ICON_STYLES, scopeIconArtwork } from '@/lib/icon-style';

afterEach(() => vi.unstubAllGlobals());

const STATE_ICONS = { Star, Heart, Pin, Circle, Square };

describe('shared icon rendering', () => {
  it.each(ICON_STYLES)('keeps an omitted state fill empty in %s', style => {
    const { getByLabelText } = render(
      <IconStyleContext.Provider value={style}>
        <Star aria-label="Unselected star" fill={undefined} />
      </IconStyleContext.Provider>
    );
    expect(getByLabelText('Unselected star')).toHaveAttribute('fill', 'none');
  });

  it.each(['fluent', 'flex'] as const)(
    'renders the whole catalogue in %s without monochrome fallbacks',
    style => {
      const icons = Object.entries(applicationIcons);
      const { container } = render(
        <IconStyleContext.Provider value={style}>
          {icons.map(([name, Icon]) => (
            <Icon key={name} aria-label={name} />
          ))}
        </IconStyleContext.Provider>
      );
      expect(container.querySelectorAll('svg')).toHaveLength(icons.length);
      expect(container.querySelector('[data-icon-style="lucide"]')).toBeNull();
      expect(container.querySelectorAll(`[data-icon-style="${style}"]`)).toHaveLength(icons.length);
    }
  );

  it('preserves the original SVG classes, including numeric names and aliases', () => {
    const icons = Object.entries(applicationIcons);
    const content = icons.map(([name, Icon]) => <Icon key={name} aria-label={name} />);
    const { container, rerender } = render(
      <IconStyleContext.Provider value="lucide">{content}</IconStyleContext.Provider>
    );
    const originalClasses = [...container.querySelectorAll('svg')].map(svg => ({
      name: svg.getAttribute('aria-label'),
      classes: [...svg.classList],
    }));
    for (const style of ['fluent', 'flex'] as const) {
      rerender(<IconStyleContext.Provider value={style}>{content}</IconStyleContext.Provider>);
      const rendered = [...container.querySelectorAll('svg')];
      expect(rendered).toHaveLength(originalClasses.length);
      originalClasses.forEach(({ name, classes }, index) => {
        expect(rendered[index]).toHaveAttribute('aria-label', name);
        expect(rendered[index]).toHaveClass(...classes);
      });
    }
  });

  it.each(ICON_STYLES)('preserves filled and outline control states in %s', style => {
    const { getByLabelText, rerender } = render(
      <IconStyleContext.Provider value={style}>
        {Object.entries(STATE_ICONS).map(([name, Icon]) => (
          <Icon key={name} aria-label={name} fill="none" />
        ))}
      </IconStyleContext.Provider>
    );
    for (const label of Object.keys(STATE_ICONS)) {
      const icon = getByLabelText(label);
      expect(icon).toHaveAttribute('fill', 'none');
      // The state layer inherits the effective SVG fill, including a class
      // applied by a parent button; accents retain their own colours.
      if (style === 'lucide') expect(icon.querySelector('[fill]')).toBeNull();
      else expect(icon.querySelector('[fill="inherit"]')).not.toBeNull();
    }
    rerender(
      <IconStyleContext.Provider value={style}>
        {Object.entries(STATE_ICONS).map(([name, Icon]) => (
          <Icon key={name} aria-label={name} fill="currentColor" />
        ))}
      </IconStyleContext.Provider>
    );
    for (const label of Object.keys(STATE_ICONS)) {
      expect(getByLabelText(label)).toHaveAttribute('fill', 'currentColor');
      if (style === 'lucide') expect(getByLabelText(label).querySelector('[fill]')).toBeNull();
      else expect(getByLabelText(label).querySelector('[fill="inherit"]')).not.toBeNull();
    }
  });
  it('uses system-coloured Lucide geometry in forced-colour environments', () => {
    const query = window.matchMedia('(forced-colors: active)');
    vi.stubGlobal('matchMedia', () => ({ ...query, matches: true }));
    const { getByLabelText } = render(<Calendar aria-label="Calendar" />);
    expect(getByLabelText('Calendar')).toHaveAttribute('data-icon-style', 'lucide');
    expect(getByLabelText('Calendar').querySelector('linearGradient')).toBeNull();
  });
  it.each(ICON_STYLES)(
    'renders %s with SVG size, accessible label, ref and events intact',
    style => {
      const ref = createRef<SVGSVGElement>();
      const onClick = vi.fn();
      const { getByLabelText } = render(
        <IconStyleContext.Provider value={style}>
          <Calendar
            size={18}
            ref={ref}
            aria-label="Calendar"
            onClick={onClick}
            className="test-icon"
          />
        </IconStyleContext.Provider>
      );
      const svg = getByLabelText('Calendar');
      expect(svg).toHaveAttribute('data-icon-style', style);
      expect(svg).toHaveAttribute('width', '18');
      expect(ref.current).toBe(svg);
      expect(svg).toHaveClass('test-icon');
      fireEvent.click(svg);
      expect(onClick).toHaveBeenCalledOnce();
    }
  );

  it('switches existing icons and keeps every gradient reference local to its SVG', () => {
    const content = (
      <>
        <Home />
        <Home />
        <MessageSquare />
      </>
    );
    const { container, rerender } = render(
      <IconStyleContext.Provider value="fluent">{content}</IconStyleContext.Provider>
    );
    const ids = Array.from(container.querySelectorAll('[id]')).map(node => node.id);
    expect(ids.length).toBeGreaterThan(0);
    expect(new Set(ids).size).toBe(ids.length);
    for (const svg of container.querySelectorAll('svg')) {
      const ownIds = new Set(Array.from(svg.querySelectorAll('[id]')).map(node => node.id));
      for (const match of svg.innerHTML.matchAll(/url\(#([^)]+)\)/g))
        expect(ownIds.has(match[1])).toBe(true);
    }
    rerender(<IconStyleContext.Provider value="flex">{content}</IconStyleContext.Provider>);
    expect(container.querySelectorAll('[data-icon-style="flex"]')).toHaveLength(3);
    rerender(<IconStyleContext.Provider value="lucide">{content}</IconStyleContext.Provider>);
    expect(container.querySelectorAll('[data-icon-style="lucide"]')).toHaveLength(3);
  });

  it('namespaces SVG definitions and both reference forms', () => {
    expect(
      scopeIconArtwork(
        '<g id="paint"/><use href="#paint"/><use xlink:href="#paint"/><path fill="url(#paint)"/>',
        'instance'
      )
    ).toBe(
      '<g id="instance-paint"/><use href="#instance-paint"/><use xlink:href="#instance-paint"/><path fill="url(#instance-paint)"/>'
    );
  });
});
