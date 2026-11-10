'use client';

import { Children, useContext, type ComponentPropsWithoutRef } from 'react';
import type { ExtraProps } from 'react-markdown';
import { IconStyleContext } from '@/lib/icon-style-context';
import { MarkdownClassificationSpan } from './ClassificationBadges';
import { MATERIAL_SYMBOL_ICONS } from './material-symbol-icons';

const SYMBOL_CLASS = 'material-symbols-outlined';
// Font variation settings cannot fill an SVG. These legacy names encode a
// state, so their semantic body needs the original fill explicitly.
const FILLED_SYMBOLS = new Set(['star', 'star_half', 'favorite']);

/**
 * Enhance a legacy ligature with trusted artwork from the application catalogue.
 *
 * The HTML remains a text marker in stored answers. Only this already-sanitized
 * component chooses an SVG; neither markup nor an SVG URL is accepted as artwork.
 * Unknown historical names keep their glyph and use the selected color palette.
 */
export function MaterialSymbol({
  name,
  className,
  ...props
}: Omit<ComponentPropsWithoutRef<'span'>, 'children'> & { name: string }) {
  const iconStyle = useContext(IconStyleContext);
  const Icon = Object.hasOwn(MATERIAL_SYMBOL_ICONS, name) ? MATERIAL_SYMBOL_ICONS[name] : null;
  const classes = className?.split(/\s+/) ?? [];
  if (!classes.includes(SYMBOL_CLASS)) classes.push(SYMBOL_CLASS);
  if (Icon) classes.push('lia-symbol-icon');
  else if (iconStyle !== 'lucide') classes.push('lia-symbol-legacy-color');
  return (
    <span
      aria-hidden={props['aria-label'] ? undefined : true}
      {...props}
      className={classes.join(' ')}
      data-icon-style={Icon ? undefined : iconStyle}
    >
      {Icon ? (
        <Icon
          size="1em"
          fill={FILLED_SYMBOLS.has(name) ? 'currentColor' : 'none'}
          // Split's connected arrow branches left; mirror the right maneuver.
          style={name === 'fork_right' ? { transform: 'scaleX(-1)' } : undefined}
          aria-hidden="true"
        />
      ) : (
        name
      )}
    </span>
  );
}

/** The shared span boundary preserves classification behavior for ordinary text. */
export function MarkdownIconSpan({
  children,
  node: _node,
  ...props
}: ComponentPropsWithoutRef<'span'> & ExtraProps) {
  const parts = Children.toArray(children);
  if (
    props.className?.split(/\s+/).includes(SYMBOL_CLASS) &&
    parts.length > 0 &&
    parts.every(part => typeof part === 'string')
  ) {
    return <MaterialSymbol {...props} name={parts.join('').trim()} />;
  }
  return <MarkdownClassificationSpan {...props}>{children}</MarkdownClassificationSpan>;
}
