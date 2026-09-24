/**
 * The living maps' data, per language — SERVER side only.
 *
 * Imports every file of `src/data/maps/`: the language-neutral structure, the
 * generated `facts.json`, and the words of the three maps in the six languages.
 * Only the pages import this module; their client components receive a VIEW
 * built from it (`model.ts`), so the browser never downloads five languages it
 * will not display. `lib/maps/__tests__/data.test.ts` pins that no client
 * component imports it.
 *
 * The files are written and checked by `scripts/audit/doc_maps.py`: French is
 * the source, every other language carries the fingerprint of the French it
 * translates, and `task lint:docs` fails on a missing or stale translation.
 */

import type { Language } from '@/i18n/settings';

import facts from '@/data/maps/facts.json';
import functional from '@/data/maps/functional.json';
import history from '@/data/maps/history.json';
import technical from '@/data/maps/technical.json';
import functionalDe from '@/data/maps/text/functional.de.json';
import functionalEn from '@/data/maps/text/functional.en.json';
import functionalEs from '@/data/maps/text/functional.es.json';
import functionalFr from '@/data/maps/text/functional.fr.json';
import functionalIt from '@/data/maps/text/functional.it.json';
import functionalZh from '@/data/maps/text/functional.zh.json';
import historyDe from '@/data/maps/text/history.de.json';
import historyEn from '@/data/maps/text/history.en.json';
import historyEs from '@/data/maps/text/history.es.json';
import historyFr from '@/data/maps/text/history.fr.json';
import historyIt from '@/data/maps/text/history.it.json';
import historyZh from '@/data/maps/text/history.zh.json';
import technicalDe from '@/data/maps/text/technical.de.json';
import technicalEn from '@/data/maps/text/technical.en.json';
import technicalEs from '@/data/maps/text/technical.es.json';
import technicalFr from '@/data/maps/text/technical.fr.json';
import technicalIt from '@/data/maps/text/technical.it.json';
import technicalZh from '@/data/maps/text/technical.zh.json';

import type {
  FunctionalStructure,
  HistoryStructure,
  MapsData,
  MapsFactsData,
  MapsText,
  TechnicalStructure,
} from './types';

const TEXTS: Record<Language, MapsText> = {
  fr: { functional: functionalFr, technical: technicalFr, history: historyFr },
  en: { functional: functionalEn, technical: technicalEn, history: historyEn },
  de: { functional: functionalDe, technical: technicalDe, history: historyDe },
  es: { functional: functionalEs, technical: technicalEs, history: historyEs },
  it: { functional: functionalIt, technical: technicalIt, history: historyIt },
  zh: { functional: functionalZh, technical: technicalZh, history: historyZh },
};

const FUNCTIONAL: FunctionalStructure = functional;
const TECHNICAL: TechnicalStructure = technical;
const HISTORY: HistoryStructure = history;
const FACTS: MapsFactsData = facts;

/** Structure, facts and the words of one language. */
export function mapsData(lng: Language): MapsData {
  return {
    functional: FUNCTIONAL,
    technical: TECHNICAL,
    history: HISTORY,
    text: TEXTS[lng],
    facts: FACTS,
  };
}
