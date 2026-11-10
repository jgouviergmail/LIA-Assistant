/** Centred framing for reviewed artwork with generous margins in its source viewBox. */
const compactControls = new Set(
  'ChevronDown ChevronLeft ChevronRight ChevronUp X ArrowDownLeft ArrowUpLeft ArrowUpRight Asterisk Minus Plus'.split(
    ' '
  )
);

const insetComplements = new Set(
  'ArrowDown ArrowLeft ArrowRight ArrowUp Bold Check CheckCheck ChevronsDownUp ChevronsUp Ellipsis Forward GripHorizontal GripVertical Heading Italic Library Menu MoreVertical MousePointer2 PersonStanding Redo2 Reply SpellCheck Terminal Underline Undo2'.split(
    ' '
  )
);

const insetVendor = {
  fluent: new Set(
    'alert alert_badge arrow_clockwise_dashes arrow_square_down board briefcase calendar checkbox code_block content_view data_bar_vertical_ascending data_scatter data_trending flag history image lock_closed number_symbol_square receipt share_android table text_bullet_list_square'.split(
      ' '
    )
  ),
  flex: new Set(['navigation-arrow-north-flat']),
};

/** Preserve the outer SVG size and keep the original drawing and paint coordinates. */
export function opticalViewBox(viewBox, style, source, name) {
  const compact = source === null && compactControls.has(name);
  const inset = source === null ? insetComplements.has(name) : insetVendor[style].has(source);
  if (!compact && !inset) return viewBox;
  const [x, y, width, height] = viewBox.split(' ').map(Number);
  const fraction = compact ? 0.14 : 0.0625;
  const framed = [
    x + width * fraction,
    y + height * fraction,
    width * (1 - 2 * fraction),
    height * (1 - 2 * fraction),
  ];
  return framed.map(value => Number(value.toFixed(3))).join(' ');
}
