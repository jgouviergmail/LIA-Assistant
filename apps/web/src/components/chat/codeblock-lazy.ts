/**
 * Lazy loaders for react-syntax-highlighter.
 *
 * Separated from CodeBlock.tsx so that the PrismAsyncLight bundle and each
 * language grammar are only fetched when a code block actually needs them.
 */

import { PrismAsyncLight } from 'react-syntax-highlighter';

export { PrismAsyncLight as SyntaxHighlighter };

// Opaque type for the prism style object (different themes have different keys)
export type PrismStyle = Record<string, React.CSSProperties>;

/**
 * Map of language keys (lowercase) to async loaders.
 * Add new languages here — each one is an individual dynamic import so
 * webpack/rspack code-splits them into their own chunks.
 */
export const LANGUAGE_LOADERS: Record<string, () => Promise<{ default: unknown }>> = {
  javascript: () => import('react-syntax-highlighter/dist/esm/languages/prism/javascript'),
  js: () => import('react-syntax-highlighter/dist/esm/languages/prism/javascript'),
  typescript: () => import('react-syntax-highlighter/dist/esm/languages/prism/typescript'),
  ts: () => import('react-syntax-highlighter/dist/esm/languages/prism/typescript'),
  tsx: () => import('react-syntax-highlighter/dist/esm/languages/prism/tsx'),
  jsx: () => import('react-syntax-highlighter/dist/esm/languages/prism/jsx'),
  python: () => import('react-syntax-highlighter/dist/esm/languages/prism/python'),
  py: () => import('react-syntax-highlighter/dist/esm/languages/prism/python'),
  bash: () => import('react-syntax-highlighter/dist/esm/languages/prism/bash'),
  sh: () => import('react-syntax-highlighter/dist/esm/languages/prism/bash'),
  shell: () => import('react-syntax-highlighter/dist/esm/languages/prism/bash'),
  json: () => import('react-syntax-highlighter/dist/esm/languages/prism/json'),
  yaml: () => import('react-syntax-highlighter/dist/esm/languages/prism/yaml'),
  yml: () => import('react-syntax-highlighter/dist/esm/languages/prism/yaml'),
  markdown: () => import('react-syntax-highlighter/dist/esm/languages/prism/markdown'),
  md: () => import('react-syntax-highlighter/dist/esm/languages/prism/markdown'),
  html: () => import('react-syntax-highlighter/dist/esm/languages/prism/markup'),
  xml: () => import('react-syntax-highlighter/dist/esm/languages/prism/markup'),
  css: () => import('react-syntax-highlighter/dist/esm/languages/prism/css'),
  rust: () => import('react-syntax-highlighter/dist/esm/languages/prism/rust'),
  go: () => import('react-syntax-highlighter/dist/esm/languages/prism/go'),
  sql: () => import('react-syntax-highlighter/dist/esm/languages/prism/sql'),
  java: () => import('react-syntax-highlighter/dist/esm/languages/prism/java'),
  c: () => import('react-syntax-highlighter/dist/esm/languages/prism/c'),
  cpp: () => import('react-syntax-highlighter/dist/esm/languages/prism/cpp'),
};

/**
 * Load the Prism one-dark / one-light theme lazily based on the resolved theme.
 */
export const loadStyle = async (isDark: boolean): Promise<PrismStyle> => {
  const mod = isDark
    ? await import('react-syntax-highlighter/dist/esm/styles/prism/one-dark')
    : await import('react-syntax-highlighter/dist/esm/styles/prism/one-light');
  return mod.default as PrismStyle;
};
