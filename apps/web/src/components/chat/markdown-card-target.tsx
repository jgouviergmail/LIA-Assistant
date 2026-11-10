'use client';

import {
  createContext,
  Children,
  isValidElement,
  useContext,
  useMemo,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from 'react';
import type { ExtraProps } from 'react-markdown';
import { useTranslation } from 'react-i18next';
import { useCardToolTarget } from '@/hooks/useCardToolTarget';
import { AppConfigSeedContext } from '@/hooks/useAppConfig';
import { workbenchAvailable } from '@/lib/workbench/availability';
import {
  cardTargetPresentation,
  isCardSourceLink,
  type CardTargetPresentation,
} from '@/lib/markdown-card-target';
import { cn } from '@/lib/utils';

interface Navigation {
  presentation: CardTargetPresentation;
  state: ReturnType<typeof useCardToolTarget>['state'];
  open: () => Promise<void>;
  offered: boolean;
}
const CardTarget = createContext<Navigation | null>(null);

/** The binding clears inherited identity, including unknown nested bindings. */
export function CardToolBoundary({
  node,
  binding,
  children,
}: ExtraProps & { binding: boolean; children: ReactNode }) {
  const parent = useContext(CardTarget);
  const presentation = useMemo(() => cardTargetPresentation(node, binding), [node, binding]);
  if (!binding && parent) return children;
  if (!presentation.kind) return <CardTarget.Provider value={null}>{children}</CardTarget.Provider>;
  return <CardToolNavigation presentation={presentation}>{children}</CardToolNavigation>;
}

function CardToolNavigation({
  presentation,
  children,
}: {
  presentation: CardTargetPresentation;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const offered = workbenchAvailable(useContext(AppConfigSeedContext));
  const navigation = useCardToolTarget(presentation.token, presentation.kind!, offered);
  const { state, open, openTool } = navigation;
  const value = useMemo(
    () => ({ presentation, state, open, offered }),
    [presentation, state, open, offered]
  );
  const pending = state === 'opening';
  const failed = state !== 'idle' && !pending;
  return (
    <CardTarget.Provider value={value}>
      {children}
      {offered && !presentation.hasTitleLink && (
        <button
          type="button"
          className="lia-action-btn"
          aria-disabled={pending}
          onClick={() => void open()}
        >
          {t('card_tools.open_item')}
        </button>
      )}
      {offered && state !== 'idle' && (
        <div className="my-2 flex flex-wrap items-center gap-2 text-sm">
          <p role="status">{t(`card_tools.${state}`)}</p>
          {failed && state === 'error' && (
            <button type="button" className="underline" onClick={() => void open()}>
              {t('card_tools.retry')}
            </button>
          )}
          {failed && (
            <button type="button" className="underline" onClick={openTool}>
              {t('card_tools.open_tool')}
            </button>
          )}
        </div>
      )}
    </CardTarget.Provider>
  );
}

type LinkProps = ComponentPropsWithoutRef<'a'> & ExtraProps & { isUser?: boolean };

/** Retain the source's visual/accessible content, without any anchor navigation attribute. */
function CardSourceButton({
  className,
  children,
  navigation,
  ...props
}: LinkProps & { navigation: Navigation }) {
  const { t } = useTranslation();
  const action = className?.split(/\s+/).includes('lia-action-btn');
  const preview = className?.split(/\s+/).includes('lia-file__preview');
  if (!navigation.offered) {
    return action ? null : (
      <span
        className={className}
        style={props.style}
        title={props.title}
        aria-label={props['aria-label']}
      >
        {children}
      </span>
    );
  }
  const icons = Children.toArray(children).filter(
    child =>
      isValidElement<{ className?: string }>(child) &&
      child.props.className?.split(/\s+/).includes('lia-action-btn__icon')
  );
  return (
    <button
      type="button"
      className={className}
      id={props.id}
      style={{ textAlign: 'inherit', ...props.style }}
      title={action && props.title ? t('card_tools.open_item') : props.title}
      aria-label={action || preview ? t('card_tools.open_item') : props['aria-label']}
      aria-describedby={props['aria-describedby']}
      lang={props.lang}
      dir={props.dir}
      aria-disabled={navigation.state === 'opening'}
      aria-busy={navigation.state === 'opening'}
      onClick={() => void navigation.open()}
    >
      {action ? (
        <>
          {icons}
          {t('card_tools.open_item')}
        </>
      ) : (
        children
      )}
    </button>
  );
}

/** Source anchors become buttons: even modified clicks cannot open the former provider. */
export function MarkdownLink({
  node,
  href,
  className,
  children,
  isUser = false,
  ...props
}: LinkProps) {
  const navigation = useContext(CardTarget);
  if (navigation && isCardSourceLink(node, navigation.presentation)) {
    return (
      <CardSourceButton {...props} className={className} navigation={navigation}>
        {children}
      </CardSourceButton>
    );
  }
  const protocol = href?.startsWith('tel:') || href?.startsWith('mailto:');
  return (
    <a
      href={href}
      {...(!protocol && { target: '_blank', rel: 'noopener noreferrer' })}
      className={
        className?.startsWith('lia-')
          ? className
          : cn(
              'underline decoration-primary/40 hover:decoration-primary transition-colors',
              isUser ? 'text-primary-foreground' : 'text-primary'
            )
      }
      {...props}
    >
      {children}
    </a>
  );
}
