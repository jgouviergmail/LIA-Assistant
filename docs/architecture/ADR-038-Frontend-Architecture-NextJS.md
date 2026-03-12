# ADR-038: Frontend Architecture (Next.js App Router)

**Status**: ✅ IMPLEMENTED (2025-12-21)
**Deciders**: Équipe architecture LIA
**Technical Story**: Modern React frontend with Next.js 16 App Router
**Related Documentation**: `apps/web/README.md`

---

## Context and Problem Statement

Le frontend nécessitait une architecture moderne et performante :

1. **Server-Side Rendering** : SEO et performance initiale
2. **Streaming UI** : Réponses LLM en temps réel
3. **Internationalization** : Support 6 langues
4. **BFF Security** : HTTP-only cookies, pas de tokens exposés

**Question** : Comment construire un frontend React moderne, sécurisé et performant ?

---

## Decision Drivers

### Must-Have (Non-Negotiable):

1. **App Router** : Next.js 16 avec Server Components
2. **SSE Streaming** : Fetch API avec ReadableStream
3. **BFF Authentication** : HTTP-only cookies
4. **i18n Dynamic Routes** : `/[lng]/dashboard`

### Nice-to-Have:

- Radix UI design system
- React Query caching
- Custom hooks library

---

## Decision Outcome

**Chosen option**: "**Next.js 16 App Router + BFF + i18next + Radix UI**"

### Architecture Overview

```mermaid
graph TB
    subgraph "NEXT.JS APP ROUTER"
        RSC[Server Components<br/>Root Layout, i18n init]
        CLIENT[Client Components<br/>'use client' directive]
        PAGES[Pages<br/>/[lng]/dashboard/*]
    end

    subgraph "STATE MANAGEMENT"
        CONTEXT[React Context<br/>Auth, Theme, Logging]
        REDUCER[useReducer<br/>Chat FSM]
        QUERY[React Query<br/>Server state cache]
    end

    subgraph "DATA FETCHING"
        SSE[ChatSSEClient<br/>Fetch + ReadableStream]
        API[ApiClient<br/>credentials: include]
        HOOKS[Custom Hooks<br/>useApiQuery, useApiMutation]
    end

    subgraph "UI LAYER"
        RADIX[Radix UI Primitives]
        TAILWIND[Tailwind CSS]
        CVA[class-variance-authority]
    end

    RSC --> CLIENT
    CLIENT --> CONTEXT
    CLIENT --> REDUCER
    CONTEXT --> QUERY
    SSE --> REDUCER
    API --> HOOKS
    RADIX --> TAILWIND
    TAILWIND --> CVA

    style RSC fill:#4CAF50,stroke:#2E7D32,color:#fff
    style SSE fill:#2196F3,stroke:#1565C0,color:#fff
    style CONTEXT fill:#FF9800,stroke:#F57C00,color:#fff
```

### Technology Stack

```typescript
// package.json
{
  "next": "15.3.4",
  "react": "18.3.1",
  "@tanstack/react-query": "^5",
  "i18next": "^24",
  "@radix-ui/react-*": "latest",
  "tailwindcss": "^3.4"
}
```

### App Router Structure

```
apps/web/src/
├── app/[lng]/                    # Dynamic language routing
│   ├── layout.tsx                # RSC: i18n init, providers
│   ├── (auth)/                   # Public auth routes
│   │   ├── login/page.tsx
│   │   ├── register/page.tsx
│   │   └── oauth-callback/page.tsx
│   └── dashboard/                # Protected routes
│       ├── layout.tsx            # Client: auth check
│       ├── chat/page.tsx
│       └── settings/page.tsx
├── components/
│   ├── ui/                       # Shadcn-style primitives
│   ├── chat/                     # Chat feature
│   └── settings/                 # Settings feature
├── hooks/                        # Custom React hooks
├── lib/
│   ├── api-client.ts             # Fetch wrapper
│   ├── api/chat.ts               # SSE client
│   ├── auth.tsx                  # Auth context
│   └── query-client.tsx          # React Query config
└── i18n/                         # i18next setup
```

### Server vs Client Components

```typescript
// apps/web/src/app/[lng]/layout.tsx (Server Component)
export default async function RootLayout({ children, params }) {
  const { lng } = await params;
  const i18n = await initI18next(lng);
  const resources = i18n.options.resources;

  return (
    <html lang={lng}>
      <body>
        <TranslationsProvider lng={lng} resources={resources}>
          <QueryClientProvider>
            <AuthProvider>
              {children}
            </AuthProvider>
          </QueryClientProvider>
        </TranslationsProvider>
      </body>
    </html>
  );
}

// apps/web/src/app/[lng]/dashboard/layout.tsx (Client Component)
'use client';

export default function DashboardLayout({ children }) {
  const { user, isLoading } = useAuth();

  if (isLoading) return <LoadingSpinner />;
  if (!user) return redirect('/login');

  return <DashboardShell>{children}</DashboardShell>;
}
```

### SSE Streaming Client

```typescript
// apps/web/src/lib/api/chat.ts

export class ChatSSEClient {
  private abortController: AbortController | null = null;

  async sendMessage(
    conversationId: string,
    message: string,
    callbacks: StreamCallbacks,
  ) {
    this.cancel(); // Prevent double-counting
    this.abortController = new AbortController();

    const response = await fetch('/api/v1/agents/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include', // BFF pattern
      body: JSON.stringify({ message }),
      signal: this.abortController.signal,
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) {
          const event = JSON.parse(line.slice(6));
          this.handleEvent(event, callbacks);
        }
      }
    }
  }

  private handleEvent(event: SSEEvent, callbacks: StreamCallbacks) {
    switch (event.type) {
      case 'token':
        callbacks.onToken(event.content);
        break;
      case 'done':
        callbacks.onDone(event.metadata);
        break;
      case 'registry_update':
        callbacks.onRegistryUpdate(event.items);
        break;
      case 'error':
        callbacks.onError(event.message);
        break;
    }
  }

  cancel() {
    this.abortController?.abort();
    this.abortController = null;
  }
}
```

### Chat State Machine (useReducer)

```typescript
// apps/web/src/reducers/chat-reducer.ts

type ChatState = {
  status: 'idle' | 'sending' | 'streaming' | 'error';
  messages: Message[];
  streamBuffer: string;
  registry: Record<string, RegistryItem>;
};

type ChatAction =
  | { type: 'SEND_MESSAGE'; payload: string }
  | { type: 'STREAM_TOKEN'; payload: string }
  | { type: 'STREAM_DONE'; payload: MessageMetadata }
  | { type: 'STREAM_ERROR'; payload: string }
  | { type: 'REGISTRY_UPDATE'; payload: RegistryItem[] };

function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'SEND_MESSAGE':
      return {
        ...state,
        status: 'sending',
        messages: [...state.messages, { role: 'user', content: action.payload }],
      };

    case 'STREAM_TOKEN':
      return {
        ...state,
        status: 'streaming',
        streamBuffer: state.streamBuffer + action.payload,
      };

    case 'STREAM_DONE':
      return {
        ...state,
        status: 'idle',
        messages: [...state.messages, {
          role: 'assistant',
          content: state.streamBuffer,
          metadata: action.payload,
        }],
        streamBuffer: '',
      };

    // ...
  }
}
```

### BFF Authentication

```typescript
// apps/web/src/lib/auth.tsx

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // On mount: check session via HTTP-only cookie
    apiClient.get<User>('/auth/me')
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const user = await apiClient.post<User>('/auth/login', { email, password });
    setUser(user);
  };

  const logout = async () => {
    await apiClient.post('/auth/logout');
    setUser(null);
  };

  // ...
}

// apps/web/src/lib/api-client.ts
class ApiClient {
  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(this.getUrl(endpoint), {
      ...options,
      credentials: 'include', // Always send HTTP-only cookies
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (response.status === 401) {
      // Session expired: redirect to login
      window.location.href = `/${getCurrentLang()}/login`;
      throw new Error('Session expired');
    }

    return response.json();
  }
}
```

### Internationalization (i18next)

```typescript
// apps/web/src/i18n/settings.ts

export const SUPPORTED_LANGUAGES = ['fr', 'en', 'es', 'de', 'it', 'zh'] as const;
export const FALLBACK_LANGUAGE = 'fr';

export const LOCALE_MAP: Record<string, string> = {
  fr: 'fr-FR',
  en: 'en-US',
  es: 'es-ES',
  de: 'de-DE',
  it: 'it-IT',
  zh: 'zh-CN',
};

// apps/web/src/i18n/client.ts (Client-side hook)
export function useTranslation(lng: string, ns: string = 'translation') {
  const [t, setT] = useState<TFunction>(() => (key) => key);

  useEffect(() => {
    i18next
      .use(initReactI18next)
      .init({
        lng,
        fallbackLng: FALLBACK_LANGUAGE,
        ns: [ns],
        resources: window.__I18N_RESOURCES__,
      })
      .then(() => setT(() => i18next.t));
  }, [lng]);

  return { t, i18n: i18next };
}

// apps/web/src/i18n/server.ts (Server-side)
export async function initI18next(lng: string) {
  const resources = await loadTranslations(lng);
  return i18next.createInstance().init({ lng, resources });
}
```

### Custom Hooks Library

```typescript
// apps/web/src/hooks/index.ts

export { useAuth } from './useAuth';
export { useChat } from './useChat';
export { useMemories } from './useMemories';
export { useConversation } from './useConversation';
export { usePersonality } from './usePersonality';
export { useGeolocation } from './useGeolocation';
export { useApiQuery, useApiMutation } from './useApi';
export { useDebounce } from './useDebounce';
export { useLocalizedRouter } from './useLocalizedRouter';

// apps/web/src/hooks/useApiQuery.ts
export function useApiQuery<T>(
  endpoint: string,
  options: UseApiQueryOptions<T> = {},
) {
  const [data, setData] = useState<T | null>(options.initialData ?? null);
  const [loading, setLoading] = useState(!options.initialData);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!options.enabled) return;

    const controller = new AbortController();

    apiClient
      .get<T>(endpoint, { signal: controller.signal, params: options.params })
      .then((result) => {
        setData(result);
        options.onSuccess?.(result);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setError(err);
          options.onError?.(err);
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [endpoint, ...options.deps]);

  return { data, loading, error, setData, refetch: () => { /* ... */ } };
}
```

### Design System (Radix + Tailwind + CVA)

```typescript
// apps/web/src/components/ui/button.tsx

import { cva, type VariantProps } from 'class-variance-authority';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md font-medium transition-colors',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        success: 'bg-success text-success-foreground hover:bg-success/90',
        destructive: 'bg-destructive text-destructive-foreground',
        outline: 'border border-input bg-background hover:bg-accent',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        default: 'h-10 px-4 py-2',
        lg: 'h-12 px-6 text-lg',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

export function Button({
  className,
  variant,
  size,
  isLoading,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={isLoading || props.disabled}
      {...props}
    >
      {isLoading ? <Spinner className="mr-2" /> : null}
      {children}
    </button>
  );
}
```

### React Query Configuration

```typescript
// apps/web/src/lib/query-client.tsx

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,      // 5 minutes
      gcTime: 10 * 60 * 1000,        // 10 minutes (formerly cacheTime)
      refetchOnWindowFocus: false,   // Prevent unnecessary API calls
      retry: 1,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    },
  },
});
```

### Consequences

**Positive**:
- ✅ **Next.js 16 App Router** : Server Components + streaming
- ✅ **BFF Security** : HTTP-only cookies, no exposed tokens
- ✅ **SSE Streaming** : Real-time LLM responses
- ✅ **i18n Dynamic Routes** : 6 languages with URL-based routing
- ✅ **Radix UI** : Accessible, customizable primitives
- ✅ **Custom Hooks** : Reusable data fetching patterns
- ✅ **Type Safety** : Full TypeScript with strict mode

**Negative**:
- ⚠️ No Zustand/Redux (Context API complexity for large state)
- ⚠️ No SSR for chat (client-only for streaming)

---

## Validation

**Acceptance Criteria**:
- [x] ✅ Next.js 16 App Router with [lng] dynamic routes
- [x] ✅ Server Components for i18n initialization
- [x] ✅ Client Components for interactive features
- [x] ✅ SSE streaming with Fetch + ReadableStream
- [x] ✅ BFF authentication (HTTP-only cookies)
- [x] ✅ React Query for server state caching
- [x] ✅ Radix UI + Tailwind design system
- [x] ✅ Custom hooks library (useApiQuery, useChat, etc.)

---

## References

### Source Code
- **App Router**: `apps/web/src/app/[lng]/`
- **Components**: `apps/web/src/components/`
- **Hooks**: `apps/web/src/hooks/`
- **API Client**: `apps/web/src/lib/api-client.ts`
- **SSE Client**: `apps/web/src/lib/api/chat.ts`
- **i18n**: `apps/web/src/i18n/`

---

**Fin de ADR-038** - Frontend Architecture Decision Record.
