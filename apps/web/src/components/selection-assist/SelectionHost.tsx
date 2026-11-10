'use client';
/** Render in the owning modal's React tree, with the interactive layer portalled to the viewport. */
import { useContext, useSyncExternalStore } from 'react';
import dynamic from 'next/dynamic';
import { SelectionContext, type SelectionContextValue } from './context';
const SelectionSession = dynamic(
  () => import('./SelectionSession').then(module => module.SelectionSession),
  { ssr: false }
);
const FieldDictation = dynamic(
  () => import('./FieldDictation').then(module => module.FieldDictation),
  { ssr: false }
);
const empty = () => null;

export function SelectionHost({ id }: { id: string | null }) {
  const context = useContext(SelectionContext);
  return context ? <OwnedHost context={context} id={id} /> : null;
}
function OwnedHost({ context, id }: { context: SelectionContextValue; id: string | null }) {
  const target = useSyncExternalStore(context.store.subscribe, context.store.getSnapshot, empty);
  if (!target || target.host !== id) return null;
  if (target.mode === 'edit' && !target.text)
    return context.dictates ? (
      <FieldDictation key={target.id} context={context} target={target} />
    ) : null;
  if (!context.offer) return null;
  return (
    <SelectionSession key={target.id} context={context} offer={context.offer} target={target} />
  );
}
