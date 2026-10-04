import type { ExtraProps } from 'react-markdown';
import { SEARCH_MARK_CLASS } from '@/lib/rehype-search-highlight';

export function hasSearchMatch(node: ExtraProps['node']): boolean {
  const pending = node ? [node] : [];
  while (pending.length) {
    const element = pending.pop();
    if (!element) continue;
    const classes = element.properties.className;
    if (
      element.tagName === 'mark' &&
      Array.isArray(classes) &&
      classes.includes(SEARCH_MARK_CLASS)
    ) {
      return true;
    }
    for (const child of element.children) {
      if (child.type === 'element') pending.push(child);
    }
  }
  return false;
}
