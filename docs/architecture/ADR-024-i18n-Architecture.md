# ADR-024: Internationalization (i18n) Architecture

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Multi-language support for global users
**Related Documentation**: `docs/technical/I18N.md`

---

## Context and Problem Statement

L'application devait supporter plusieurs langues :

1. **Frontend** : Interface utilisateur traduite
2. **Backend** : Messages d'erreur et API responses
3. **Fallback** : Gestion des traductions manquantes
4. **SEO** : URLs multilingues pour indexation

**Question** : Comment implémenter une architecture i18n cohérente entre frontend et backend ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **6 Langues** : FR (default), EN, ES, DE, IT, ZH
2. **Fallback Chain** : Langue demandée → Français
3. **URL-Based Routing** : `/en/dashboard` pour SEO
4. **Separate Systems** : i18next (React) + gettext (Python)

### Nice-to-Have:

- Language detection from Accept-Language header
- Cookie persistence for language preference
- Date/time localization

---

## Decision Outcome

**Chosen option**: "**i18next (Frontend) + gettext (Backend) avec French fallback**"

### Architecture Overview

```mermaid
graph TB
    subgraph "FRONTEND (Next.js)"
        MW[Middleware] --> DETECT[Language Detection<br/>URL > Cookie > Header]
        DETECT --> PARAM[[lng] param]
        PARAM --> I18N[i18next Instance]
        I18N --> JSON[(locales/{lng}/translation.json)]
        I18N --> PROV[TranslationsProvider]
        PROV --> COMP[React Components]
    end

    subgraph "BACKEND (FastAPI)"
        REQ[Request] --> HDR[Accept-Language Header]
        HDR --> PARSE[get_language_from_header]
        PARSE --> GT[gettext Translator]
        GT --> PO[(locales/{lng}/LC_MESSAGES/messages.mo)]
        GT --> RESP[API Response]
    end

    subgraph "FALLBACK CHAIN"
        LANG[Requested Language] --> CHECK{Available?}
        CHECK -->|Yes| USE[Use translation]
        CHECK -->|No| FR[Fallback to French]
    end

    COMP --> |t('key')| I18N
    RESP --> |_(msg, lang)| GT

    style I18N fill:#4CAF50,stroke:#2E7D32,color:#fff
    style GT fill:#2196F3,stroke:#1565C0,color:#fff
    style FR fill:#FF9800,stroke:#F57C00,color:#fff
```

### Supported Languages

| Code | Language | Notes |
|------|----------|-------|
| `fr` | French | Default/Fallback language |
| `en` | English | |
| `es` | Spanish | |
| `de` | German | |
| `it` | Italian | |
| `zh` | Chinese (Simplified) | Backend: `zh-CN` |

### Frontend: i18next Configuration

```typescript
// apps/web/src/i18n/settings.ts

export const fallbackLng = 'fr' as const;
export const languages = ['fr', 'en', 'es', 'de', 'it', 'zh'] as const;
export const defaultNS = 'translation' as const;
export const cookieName = 'NEXT_LOCALE';

export const LOCALE_MAP: Record<Language, string> = {
  fr: 'fr-FR',
  en: 'en-US',
  es: 'es-ES',
  de: 'de-DE',
  it: 'it-IT',
  zh: 'zh-CN',
};

export function getOptions(lng: Language = fallbackLng, ns: string = defaultNS) {
  return {
    supportedLngs: languages,
    fallbackLng,
    lng,
    fallbackNS: defaultNS,
    defaultNS,
    ns,
    interpolation: {
      escapeValue: false, // React handles escaping
    },
    returnObjects: true, // For arrays in translations
  };
}
```

### Frontend: Server-Side i18n

```typescript
// apps/web/src/i18n/index.ts

import translationFR from '../../locales/fr/translation.json';
import translationEN from '../../locales/en/translation.json';
// ... other imports

const translations = {
  fr: { translation: translationFR },
  en: { translation: translationEN },
  es: { translation: translationES },
  de: { translation: translationDE },
  it: { translation: translationIT },
  zh: { translation: translationZH },
};

// Caches i18n instances per language
const i18nInstances = new Map<string, I18nInstance>();

export async function initI18next(lng: Language, ns?: string) {
  const cacheKey = `${lng}-${ns || 'translation'}`;

  if (i18nInstances.has(cacheKey)) {
    return i18nInstances.get(cacheKey)!;
  }

  const i18nInstance = createInstance();
  await i18nInstance.use(initReactI18next).init({
    ...getOptions(lng, ns),
    resources: { [lng]: translations[lng] },
  });

  i18nInstances.set(cacheKey, i18nInstance);
  return i18nInstance;
}
```

### Frontend: Client-Side i18n

```typescript
// apps/web/src/i18n/client.ts
'use client';

export function useTranslation(lng: Language, ns?: string) {
  const [i18n, setI18n] = useState<I18nInstance | null>(null);

  useEffect(() => {
    const instance = initI18nextClient(lng, ns);
    setI18n(instance);
  }, [lng, ns]);

  return useTranslationOrg(ns);
}

function initI18nextClient(lng: Language, ns?: string) {
  const i18nInstance = createInstance();
  i18nInstance
    .use(initReactI18next)
    .use(
      resourcesToBackend(
        (language: string, namespace: string) =>
          import(`../../locales/${language}/${namespace}.json`)
      )
    )
    .init(getOptions(lng, ns));

  return i18nInstance;
}
```

### Frontend: Middleware for Language Detection

```typescript
// apps/web/src/middleware.ts

import { i18nRouter } from 'next-i18n-router';

export function middleware(request: NextRequest) {
  return i18nRouter(request, {
    locales: [...languages],
    defaultLocale: fallbackLng,  // 'fr'
    prefixDefault: false,         // /fr/dashboard → /dashboard
  });
}

// Language Detection Chain:
// 1. URL path (/en/dashboard → 'en')
// 2. Cookie (NEXT_LOCALE)
// 3. Accept-Language header
// 4. Fallback to 'fr' (French)
```

### Frontend: Root Layout Integration

```typescript
// apps/web/src/app/[lng]/layout.tsx

export default async function LanguageLayout({
  children,
  params,
}: LayoutProps) {
  const { lng } = await params;

  // Load translations server-side
  const i18n = await initI18next(lng);
  const resources = i18n.options.resources;

  return (
    <html lang={lng}>
      <body>
        <TranslationsProvider
          locale={lng}
          namespaces={['translation']}
          resources={resources || {}}
        >
          {children}
        </TranslationsProvider>
      </body>
    </html>
  );
}

export function generateStaticParams() {
  return languages.map(lng => ({ lng }));
}
```

### Backend: gettext Configuration

```python
# apps/api/src/core/i18n.py

import gettext
from functools import lru_cache

Language = Literal["fr", "en", "es", "de", "it", "zh-CN"]

SUPPORTED_LANGUAGES = ["fr", "en", "es", "de", "it", "zh-CN"]
DEFAULT_LANGUAGE = "fr"
LOCALE_DIR = Path(__file__).parent.parent.parent / "locales"

@lru_cache(maxsize=10)
def get_translator(language: Language) -> gettext.NullTranslations:
    """Get cached gettext translator for language."""
    try:
        return gettext.translation(
            "messages",
            localedir=str(LOCALE_DIR),
            languages=[language],
            fallback=False,
        )
    except FileNotFoundError:
        logger.warning(
            "translation_not_found_using_fallback",
            requested_language=language,
            fallback_language=DEFAULT_LANGUAGE,
        )
        return gettext.translation(
            "messages",
            localedir=str(LOCALE_DIR),
            languages=[DEFAULT_LANGUAGE],
            fallback=True,
        )


def _(text: str, language: Language = DEFAULT_LANGUAGE) -> str:
    """Translate text to target language."""
    translator = get_translator(language)
    return translator.gettext(text)


def _n(singular: str, plural: str, n: int, language: Language) -> str:
    """Translate with pluralization support."""
    translator = get_translator(language)
    return translator.ngettext(singular, plural, n)
```

### Backend: Language Detection from Headers

```python
def get_language_from_header(accept_language: str | None) -> Language:
    """
    Parse Accept-Language header and return best match.

    Examples:
    - "fr-FR,fr;q=0.9,en;q=0.8" → "fr"
    - "en-US,en;q=0.9" → "en"
    - "ja-JP" → "fr" (fallback)
    """
    if not accept_language:
        return DEFAULT_LANGUAGE

    for lang_code in accept_language.split(","):
        lang = lang_code.split(";")[0].strip()

        # Try exact match first (for zh-CN)
        if lang in SUPPORTED_LANGUAGES:
            return lang

        # Try with only first 2 chars (en-US → en)
        lang_short = lang[:2].lower()
        if lang_short in SUPPORTED_LANGUAGES:
            return lang_short

    return DEFAULT_LANGUAGE
```

### Backend: Date Localization

```python
# apps/api/src/core/i18n_dates.py

DAY_NAMES: dict[Language, list[str]] = {
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    "it": ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"],
    "zh-CN": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
}

MONTH_NAMES: dict[Language, list[str]] = {
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin",
           "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
    "en": ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"],
    # ... other languages
}
```

### Locale File Structure

```
apps/
├── web/
│   └── locales/
│       ├── en/translation.json    (1,278 lines)
│       ├── fr/translation.json    (1,283 lines)
│       ├── es/translation.json
│       ├── de/translation.json
│       ├── it/translation.json
│       └── zh/translation.json
│
└── api/
    └── locales/
        ├── messages.pot           (Template file)
        ├── fr/LC_MESSAGES/
        │   ├── messages.po        (French translations)
        │   └── messages.mo        (Compiled binary)
        ├── en/LC_MESSAGES/
        ├── es/LC_MESSAGES/
        ├── de/LC_MESSAGES/
        ├── it/LC_MESSAGES/
        └── zh-CN/LC_MESSAGES/
```

### Translation File Formats

**Frontend (JSON):**
```json
{
  "common": {
    "loading": "Loading...",
    "error": "Error"
  },
  "dashboard": {
    "title": "Dashboard",
    "welcome": "Welcome, {{name}}"
  }
}
```

**Backend (PO):**
```po
msgid "Invalid credentials"
msgstr "Identifiants invalides"

msgid "Account inactive"
msgstr "Compte inactif"
```

### Fallback Chain

**Frontend (i18next):**
1. Requested language & namespace
2. Same namespace, fallback language (French)
3. Returns key path as-is if not found

**Backend (gettext):**
1. Requested language MO file
2. French MO file (DEFAULT_LANGUAGE)
3. Original English text (fallback=True)

### Consequences

**Positive**:
- ✅ **6 Languages** : Complete coverage FR/EN/ES/DE/IT/ZH
- ✅ **URL-Based SEO** : `/en/dashboard` indexed separately
- ✅ **French Default** : Consistent fallback behavior
- ✅ **Caching** : Instance caching per language
- ✅ **Type Safety** : Language literal types

**Negative**:
- ⚠️ Dual systems (JSON + PO files)
- ⚠️ zh vs zh-CN mismatch between frontend/backend
- ⚠️ LLM prompts NOT translated (intentional)

---

## Validation

**Acceptance Criteria**:
- [x] ✅ 6 languages supported (FR, EN, ES, DE, IT, ZH)
- [x] ✅ i18next setup avec instance caching
- [x] ✅ gettext avec @lru_cache
- [x] ✅ URL-based routing avec [lng] parameter
- [x] ✅ Accept-Language header parsing
- [x] ✅ French fallback pour missing translations
- [x] ✅ Date/month localization

---

## Important Notes

1. **Asymmetric Language Codes**: Frontend uses `zh`, Backend uses `zh-CN`
2. **LLM Prompts NOT Translated**: Only UI messages are translated
3. **prefixDefault: false**: French URLs have no prefix (`/dashboard` vs `/en/dashboard`)

---

## References

### Source Code
- **Frontend Settings**: `apps/web/src/i18n/settings.ts`
- **Frontend Server**: `apps/web/src/i18n/index.ts`
- **Frontend Client**: `apps/web/src/i18n/client.ts`
- **Frontend Middleware**: `apps/web/src/middleware.ts`
- **Backend i18n**: `apps/api/src/core/i18n.py`
- **Backend Dates**: `apps/api/src/core/i18n_dates.py`
- **Backend Patterns**: `apps/api/src/core/i18n_patterns.py`

### External References
- **i18next**: https://www.i18next.com/
- **next-i18n-router**: https://github.com/i18nexus/next-i18n-router
- **gettext**: https://docs.python.org/3/library/gettext.html

---

**Fin de ADR-024** - Internationalization (i18n) Architecture Decision Record.
