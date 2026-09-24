'use client';

import * as DialogPrimitive from '@radix-ui/react-dialog';
import {
  ArrowRight,
  Boxes,
  CornerDownRight,
  FileCode,
  Info,
  Layers,
  Monitor,
  Play,
  Route,
  ScrollText,
  Share2,
  X,
} from 'lucide-react';
import { useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { MapIcon } from './map-icons';
import { BrickChip, MapLink } from './MapLink';
import type { Language } from '@/i18n/settings';
import { mapsFormat } from '@/lib/maps/format';
import { brickDecisionsHref, decisionHref, domainUrl, repoUrl } from '@/lib/maps/links';
import { adrLabel } from '@/lib/maps/timeline';
import type { BrickMapView, BrickView } from '@/lib/maps/types';

/** A titled block of the drawer. */
function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Info;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="lm-dsec">
      <h3>
        <Icon aria-hidden="true" width={14} height={14} />
        {title}
      </h3>
      {children}
    </section>
  );
}

/** Chips of bricks, or a sentence saying there are none. */
function BrickChips({
  ids,
  map,
  lng,
  empty,
}: {
  ids: readonly string[];
  map: BrickMapView;
  lng: Language;
  empty: string;
}) {
  const bricks = ids.flatMap(id => (map.refs[id] ? [map.refs[id]] : []));
  if (!bricks.length) return <p className="lm-empty">{empty}</p>;
  return (
    <ul className="lm-chips">
      {bricks.map(brick => (
        <li key={brick.id}>
          <BrickChip brick={brick} from={map.kind} lng={lng} />
        </li>
      ))}
    </ul>
  );
}

/** Links out to the repository, one chip each. */
function RepoChips({ items }: { items: ReadonlyArray<{ label: string; href: string }> }) {
  const { t } = useTranslation();
  return (
    <ul className="lm-chips">
      {items.map(item => (
        <li key={item.href}>
          <a className="lm-chip is-mono" href={item.href} target="_blank" rel="noopener noreferrer">
            {item.label}
            <span className="sr-only"> {t('maps.new_tab')}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

function DrawerBody({
  brick,
  map,
  lng,
  onPlayFlow,
}: {
  brick: BrickView;
  map: BrickMapView;
  lng: Language;
  onPlayFlow: (id: string) => void;
}) {
  const { t } = useTranslation();
  const format = useMemo(() => mapsFormat(lng), [lng]);
  const flows = map.flows.filter(flow => brick.flows.includes(flow.id));
  const otherSide = brick.kind === 'functional' ? 'related_technical' : 'related_functional';
  return (
    <div className="lm-drawer-body">
      <Section icon={Info} title={t('maps.drawer.role')}>
        <p>{brick.role}</p>
      </Section>
      {brick.goal && <p className="lm-goal">{brick.goal}</p>}
      {brick.stack.length > 0 && (
        <Section icon={Layers} title={t('maps.drawer.stack')}>
          <ul className="lm-chips">
            {brick.stack.map(item => (
              <li key={item} className="lm-chip is-plain">
                {item}
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Section icon={ArrowRight} title={t('maps.drawer.depends_on')}>
        <BrickChips
          ids={brick.deps}
          map={map}
          lng={lng}
          empty={t('maps.drawer.depends_on_empty')}
        />
      </Section>
      <Section icon={CornerDownRight} title={t('maps.drawer.used_by')}>
        <BrickChips ids={brick.usedBy} map={map} lng={lng} empty={t('maps.drawer.used_by_empty')} />
      </Section>
      {flows.length > 0 && (
        <Section icon={Route} title={t('maps.drawer.flows')}>
          <ul className="lm-chips">
            {flows.map(flow => (
              <li key={flow.id}>
                <button type="button" className="lm-chip" onClick={() => onPlayFlow(flow.id)}>
                  <Play aria-hidden="true" width={14} height={14} className="lm-ic" />
                  {flow.name}
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {brick.domains.length > 0 && (
        <Section icon={Boxes} title={t('maps.drawer.domains')}>
          <RepoChips items={brick.domains.map(d => ({ label: d, href: domainUrl(map.repo, d) }))} />
        </Section>
      )}
      {brick.surfaces.length > 0 && (
        <Section icon={Monitor} title={t('maps.drawer.surfaces')}>
          <ul className="lm-chips">
            {brick.surfaces.map(surface => (
              <li key={surface} className="lm-chip is-mono is-plain">
                {surface}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {brick.paths.length > 0 && (
        <Section icon={FileCode} title={t('maps.drawer.paths')}>
          <RepoChips items={brick.paths.map(p => ({ label: p, href: repoUrl(map.repo, p) }))} />
        </Section>
      )}
      {brick.related.length > 0 && (
        <Section icon={Share2} title={t(`maps.drawer.${otherSide}`)}>
          <BrickChips ids={brick.related} map={map} lng={lng} empty="" />
        </Section>
      )}
      <Section icon={ScrollText} title={t('maps.drawer.decisions', { total: brick.decisionCount })}>
        {brick.decisions.length ? (
          <>
            <ul className="lm-adr-list">
              {brick.decisions.map(decision => (
                <li key={decision.adr}>
                  <MapLink
                    href={decisionHref(decision.adr, brick.kind, lng)}
                    data-tone={decision.tone}
                  >
                    <span className="lm-no">{adrLabel(decision.adr)}</span>
                    <span className="lm-tt">{decision.title}</span>
                    <span className="lm-dt">{format.dayShort(decision.date)}</span>
                  </MapLink>
                </li>
              ))}
            </ul>
            {brick.decisionCount > brick.decisions.length && (
              <p>
                <MapLink href={brickDecisionsHref(brick.id, lng)}>
                  {t('maps.drawer.decisions_all', { total: brick.decisionCount })}
                </MapLink>
              </p>
            )}
          </>
        ) : (
          <p className="lm-empty">{t('maps.drawer.decisions_empty')}</p>
        )}
      </Section>
    </div>
  );
}

/**
 * A brick's detail: role, dependencies both ways, journeys, code, the other
 * map's bricks and the decisions that shaped it. A modal side sheet on the
 * Radix dialog — focus moves in, Escape and the scrim close it, and focus goes
 * back to the node or button that opened it. It is portaled out of the page,
 * so it carries the section's scope class itself.
 */
export function BrickDrawer({
  map,
  brick,
  lng,
  onClose,
  onPlayFlow,
}: {
  map: BrickMapView;
  brick: BrickView | null;
  lng: Language;
  onClose: () => void;
  onPlayFlow: (id: string) => void;
}) {
  const { t } = useTranslation();
  const closeRef = useRef<HTMLButtonElement>(null);
  // Radix hands focus back to its Trigger on close; the drawer has none (a node,
  // a row, a chip or the address opens it), so it remembers who had focus.
  const returnFocusRef = useRef<HTMLElement | SVGElement | null>(null);
  const family = map.families.find(f => f.id === brick?.family);
  const familyLabel = map.kind === 'functional' ? t('maps.drawer.family') : t('maps.drawer.layer');
  return (
    <DialogPrimitive.Root
      open={brick !== null}
      onOpenChange={open => {
        if (!open) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="lia-maps lm-scrim" />
        <DialogPrimitive.Content
          className="lia-maps lm-drawer"
          onOpenAutoFocus={event => {
            event.preventDefault();
            const active = document.activeElement;
            returnFocusRef.current =
              active instanceof HTMLElement || active instanceof SVGElement ? active : null;
            closeRef.current?.focus();
          }}
          onCloseAutoFocus={event => {
            event.preventDefault();
            returnFocusRef.current?.focus();
            returnFocusRef.current = null;
          }}
        >
          {brick && (
            <>
              <div className="lm-drawer-head">
                <div className="lm-drawer-title">
                  <span className="lm-badge-ic" data-tone={brick.tone}>
                    <MapIcon name={brick.icon} size={20} />
                  </span>
                  <div>
                    <DialogPrimitive.Title asChild>
                      <h2>{brick.name}</h2>
                    </DialogPrimitive.Title>
                    <DialogPrimitive.Description asChild>
                      <p>{`${familyLabel} · ${family?.name ?? ''}`}</p>
                    </DialogPrimitive.Description>
                  </div>
                </div>
                <DialogPrimitive.Close
                  ref={closeRef}
                  className="lm-icon-btn"
                  aria-label={t('maps.drawer.close')}
                >
                  <X aria-hidden="true" width={18} height={18} />
                </DialogPrimitive.Close>
              </div>
              {/* keyed: a new brick opens its detail scrolled to the top */}
              <DrawerBody
                key={brick.id}
                brick={brick}
                map={map}
                lng={lng}
                onPlayFlow={onPlayFlow}
              />
            </>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
