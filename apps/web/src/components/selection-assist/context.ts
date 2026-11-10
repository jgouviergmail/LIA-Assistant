'use client';
import { createContext } from 'react';
import type { Language } from '@/i18n/settings';
import type { CreationProposal, SelectionOffer } from '@/lib/selection-assist/contracts';
import type { SelectionStore } from '@/lib/selection-assist/store';

export interface SelectionContextValue {
  lng: Language;
  store: SelectionStore;
  offer: SelectionOffer | null;
  dictates: boolean;
  onProposal?: (proposal: CreationProposal) => void;
}
export const SelectionContext = createContext<SelectionContextValue | null>(null);
