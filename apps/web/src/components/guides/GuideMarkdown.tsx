import { Children, isValidElement } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import type { Components } from 'react-markdown';
import type { LucideIcon } from 'lucide-react';
import { MermaidDiagram } from './MermaidDiagram';

interface GuideMarkdownProps {
  content: string;
  sectionIds?: string[];
  sectionIcons?: LucideIcon[];
}

export function GuideMarkdown({ content, sectionIds = [], sectionIcons = [] }: GuideMarkdownProps) {
  // Strip front matter and ToC — find the first numbered section (## 1. ...)
  const match = content.match(/\n## \d+\./);
  const body = match?.index != null ? content.substring(match.index) : content;

  // Build custom components that inject TOC anchor ids and icons on h2 elements
  let h2Counter = 0;
  const ids = sectionIds;
  const icons = sectionIcons;
  const components: Components = {
    h2({ children, ...props }) {
      const idx = h2Counter++;
      const id = idx < ids.length ? ids[idx] : undefined;
      const Icon = idx < icons.length ? icons[idx] : undefined;
      return (
        <h2 id={id} {...props} className="flex items-center gap-3">
          {Icon && (
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 shrink-0">
              <Icon className="w-4 h-4 text-primary" />
            </span>
          )}
          <span>{children}</span>
        </h2>
      );
    },
    // Intercept ```mermaid fenced blocks and render them via MermaidDiagram
    // (client-only). Other code blocks fall through to the default <pre><code>.
    pre({ children, ...rest }) {
      const codeChild = Children.toArray(children).find(
        (c): c is React.ReactElement<{ className?: string; children?: React.ReactNode }> =>
          isValidElement(c) && c.type === 'code'
      );
      const className = codeChild?.props.className ?? '';
      if (/\blanguage-mermaid\b/.test(className)) {
        const source = String(codeChild?.props.children ?? '');
        return <MermaidDiagram chart={source} />;
      }
      return <pre {...rest}>{children}</pre>;
    },
  };

  return (
    <div
      className="guide-body prose dark:prose-invert max-w-none
        prose-headings:font-semibold prose-headings:tracking-tight prose-headings:text-foreground
        prose-h2:text-xl prose-h2:mt-12 prose-h2:mb-4 prose-h2:pb-3 prose-h2:border-b prose-h2:border-border/50 prose-h2:scroll-mt-24
        prose-h3:text-base prose-h3:mt-8 prose-h3:mb-3
        prose-p:text-[0.938rem] prose-p:leading-relaxed prose-p:text-muted-foreground prose-p:mb-4
        prose-li:text-[0.938rem] prose-li:leading-relaxed prose-li:text-muted-foreground
        prose-ul:my-3 prose-ol:my-3
        prose-strong:text-foreground prose-strong:font-semibold
        prose-blockquote:border-l-primary/30 prose-blockquote:bg-muted/30 prose-blockquote:rounded-r-lg prose-blockquote:py-2 prose-blockquote:italic
        prose-table:text-sm
        prose-th:text-left prose-th:font-semibold prose-th:text-foreground prose-th:py-2 prose-th:px-3
        prose-td:py-2 prose-td:px-3 prose-td:text-muted-foreground
        prose-tr:border-b prose-tr:border-border/50
        prose-thead:border-b-2 prose-thead:border-border
        prose-pre:bg-zinc-100 prose-pre:text-zinc-800 dark:prose-pre:bg-zinc-900 dark:prose-pre:text-zinc-200 prose-pre:border prose-pre:border-border/50 prose-pre:text-xs
        prose-code:text-xs prose-code:bg-zinc-100 prose-code:text-zinc-800 dark:prose-code:bg-zinc-800 dark:prose-code:text-zinc-200 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
        prose-a:text-primary prose-a:no-underline hover:prose-a:underline
        prose-hr:border-border/50 prose-hr:my-8"
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={components}
      >
        {body}
      </ReactMarkdown>
    </div>
  );
}
