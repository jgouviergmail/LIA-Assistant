/**
 * Location phrase detection utilities.
 *
 * Detects location-related phrases in user messages to determine
 * if geolocation should be requested. Mirrors the backend i18n_location.py
 * for consistency.
 *
 * IMPORTANT: Patterns are defined directly in code (not i18n) for reliability.
 * This ensures detection works even if i18n is not fully loaded.
 */

/**
 * Supported languages for location detection.
 */
export type SupportedLanguage = 'fr' | 'en' | 'es' | 'de' | 'it' | 'zh';

/**
 * Location type detected in user message.
 * Mirrors backend LocationType enum.
 */
export type LocationType = 'home' | 'current' | 'explicit' | 'none';

/**
 * Phrases indicating CURRENT position (dynamic, from browser geolocation).
 * User wants info related to their current GPS position.
 *
 * Synced with backend: apps/api/src/domains/agents/utils/i18n_location.py
 */
const CURRENT_PHRASES: Record<SupportedLanguage, string[]> = {
  fr: [
    'à proximité',
    'autour de moi',
    'dans le coin',
    'par ici',
    "près d'ici",
    'à côté',
    'dans les environs',
    'tout près',
    'ici',
    'dans ma zone',
  ],
  en: [
    'nearby',
    'around me',
    'around here',
    'close by',
    'near me',
    'in the area',
    'close to me',
    'in my vicinity',
    'right here',
    'near here',
  ],
  es: [
    'cerca de aquí',
    'a mi alrededor',
    'por aquí',
    'en los alrededores',
    'cerca de mí',
    'en esta zona',
    'aquí cerca',
    'por esta zona',
  ],
  de: [
    'in der nähe',
    'um mich herum',
    'hier in der gegend',
    'in meiner umgebung',
    'nah bei mir',
    'hier',
    'in dieser gegend',
    'ganz in der nähe',
  ],
  it: [
    'nelle vicinanze',
    'intorno a me',
    'qui vicino',
    'nei dintorni',
    'vicino a me',
    'in questa zona',
    'qui intorno',
    'da queste parti',
  ],
  zh: ['附近', '我周围', '这附近', '在我附近', '这里', '周边', '这一带', '我这里'],
};

/**
 * Phrases indicating HOME location (static, from database).
 * User wants info related to their configured home address.
 *
 * Synced with backend: apps/api/src/domains/agents/utils/i18n_location.py
 */
const HOME_PHRASES: Record<SupportedLanguage, string[]> = {
  fr: [
    'chez moi',
    'près de chez moi',
    'à la maison',
    'dans mon quartier',
    'mon domicile',
    'autour de chez moi',
    'proche de chez moi',
    'vers chez moi',
    'à côté de chez moi',
    'mon adresse',
  ],
  en: [
    'at home',
    'near home',
    'close to home',
    'in my neighborhood',
    'my place',
    'around my house',
    'my home',
    'near my place',
    'close to my place',
    'my address',
  ],
  es: [
    'en mi casa',
    'cerca de casa',
    'en mi barrio',
    'mi domicilio',
    'alrededor de mi casa',
    'cerca de mi casa',
    'mi hogar',
    'en mi vecindario',
  ],
  de: [
    'bei mir zuhause',
    'in meiner nähe von zuhause',
    'in meinem viertel',
    'mein zuhause',
    'um mein haus',
    'nahe meines hauses',
    'bei mir',
    'zu hause',
  ],
  it: [
    'a casa mia',
    'vicino a casa',
    'nel mio quartiere',
    'il mio domicilio',
    'intorno a casa mia',
    'casa mia',
    'dalle mie parti',
    'nel mio vicinato',
  ],
  zh: [
    '在我家',
    '我家附近',
    '我家周围',
    '我的住处',
    '家附近',
    '靠近我家',
    '我住的地方',
    '我的地址',
  ],
};

/**
 * Normalize text for comparison:
 * - Remove accents (é -> e, ü -> u, etc.)
 * - Convert to lowercase
 * - Normalize whitespace
 */
function normalizeText(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // Remove accents
    .replace(/\s+/g, ' ') // Normalize whitespace
    .trim();
}

/**
 * Normalize language code to supported format.
 */
function normalizeLanguage(language: string): SupportedLanguage {
  const langLower = language.toLowerCase().replace('_', '-');

  // Handle Chinese variants
  if (langLower.startsWith('zh')) {
    return 'zh';
  }

  // Extract base language code
  const baseLang = langLower.split('-')[0];

  // Return if supported, otherwise default to French
  if (['fr', 'en', 'es', 'de', 'it'].includes(baseLang)) {
    return baseLang as SupportedLanguage;
  }

  return 'fr';
}

/**
 * Detect location type from user message.
 *
 * @param message - User message to analyze
 * @param language - Language code (fr, en, es, de, it, zh)
 * @returns LocationType indicating what kind of location reference was detected
 */
export function detectLocationType(message: string, language: string = 'fr'): LocationType {
  const messageLower = normalizeText(message);
  const lang = normalizeLanguage(language);

  console.log('[location-detection] detectLocationType called:', {
    originalMessage: message.substring(0, 50),
    normalizedMessage: messageLower.substring(0, 50),
    language: lang,
  });

  // Check home phrases first (more specific)
  const homePhrases = HOME_PHRASES[lang] || HOME_PHRASES.fr;
  for (const phrase of homePhrases) {
    if (messageLower.includes(normalizeText(phrase))) {
      console.log('[location-detection] ✅ HOME phrase matched:', phrase);
      return 'home';
    }
  }

  // Check current position phrases
  const currentPhrases = CURRENT_PHRASES[lang] || CURRENT_PHRASES.fr;
  for (const phrase of currentPhrases) {
    if (messageLower.includes(normalizeText(phrase))) {
      console.log('[location-detection] ✅ CURRENT phrase matched:', phrase);
      return 'current';
    }
  }

  console.log('[location-detection] No location phrase detected');
  return 'none';
}

/**
 * Check if a message requires geolocation (current or home location reference).
 *
 * @param message - User message to check
 * @param language - Language code
 * @returns true if message contains location phrases requiring geolocation
 */
export function messageRequiresGeolocation(message: string, language: string = 'fr'): boolean {
  const locationType = detectLocationType(message, language);
  return locationType === 'current' || locationType === 'home';
}

/**
 * Check if message contains current location reference specifically.
 *
 * @param message - User message to check
 * @param language - Language code
 * @returns true if message references current position
 */
export function containsCurrentLocationPhrase(message: string, language: string = 'fr'): boolean {
  return detectLocationType(message, language) === 'current';
}

/**
 * Check if message contains home location reference specifically.
 *
 * @param message - User message to check
 * @param language - Language code
 * @returns true if message references home
 */
export function containsHomeLocationPhrase(message: string, language: string = 'fr'): boolean {
  return detectLocationType(message, language) === 'home';
}
