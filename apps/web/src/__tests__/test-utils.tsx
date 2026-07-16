/**
 * Shared React Testing Library harness for component tests.
 *
 * `renderWithProviders` wraps the UI in the context providers that either throw
 * when absent (`ColorThemeProvider`, `FontProvider`) or are commonly required by
 * UI primitives (`next-themes`, Radix `TooltipProvider`, TanStack Query). i18n is
 * mocked globally in `src/__tests__/setup.ts` (both `react-i18next` and
 * `@/i18n/client` — `t` echoes the key), and the data hooks
 * (`useApiQuery` / `useApiMutation` / `useAuth`) are mocked per test — so this
 * helper deliberately provides **no** auth context and **no** real API layer.
 *
 * The file re-exports the whole RTL surface plus `userEvent`, so a test imports
 * only from here:
 *
 * ```ts
 * import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
 *
 * it('does the thing', async () => {
 *   const { user } = renderWithProviders(<MyComponent />);
 *   await user.click(screen.getByRole('button', { name: 'settings.save' }));
 * });
 * ```
 *
 * `userEvent` is the standard for new interaction tests (more faithful than
 * `fireEvent`). The pre-existing `fireEvent`-based tests are left untouched.
 */

import { type ReactElement, type ReactNode } from 'react';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ColorThemeProvider } from '@/lib/theme-context';
import { FontProvider } from '@/lib/font-context';
import { TooltipProvider } from '@/components/ui/tooltip';

/**
 * A `QueryClient` with retries and caching disabled so query/mutation behaviour
 * is deterministic and does not leak between tests. Most tests mock the
 * `useApiQuery` / `useApiMutation` hooks directly and never touch this client;
 * it exists for the minority of components that call TanStack Query directly.
 */
export function makeTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
        refetchOnMount: false,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
}

export interface RenderWithProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  /** Supply a custom `QueryClient` (default: a fresh non-retrying test client). */
  queryClient?: QueryClient;
}

function AllProviders({
  children,
  queryClient,
}: {
  children: ReactNode;
  queryClient: QueryClient;
}): ReactElement {
  // next-themes is mocked to a passthrough in the test setup, so the theme is
  // supplied via the global `useTheme` mock rather than a provider here.
  return (
    <QueryClientProvider client={queryClient}>
      <ColorThemeProvider>
        <FontProvider>
          <TooltipProvider delayDuration={0}>{children}</TooltipProvider>
        </FontProvider>
      </ColorThemeProvider>
    </QueryClientProvider>
  );
}

/** The extra handle `renderWithProviders` returns on top of RTL's `RenderResult`. */
export interface RenderWithProvidersResult extends RenderResult {
  /** A `userEvent` session bound to this render (already `setup()`-ed). */
  user: ReturnType<typeof userEvent.setup>;
  /** The `QueryClient` used for this render (custom or the generated test one). */
  queryClient: QueryClient;
}

/**
 * Render `ui` inside the standard provider stack and return the RTL result
 * augmented with a ready `user` session and the active `queryClient`.
 */
export function renderWithProviders(
  ui: ReactElement,
  options: RenderWithProvidersOptions = {}
): RenderWithProvidersResult {
  const { queryClient = makeTestQueryClient(), ...rtlOptions } = options;
  const result = render(ui, {
    wrapper: ({ children }) => <AllProviders queryClient={queryClient}>{children}</AllProviders>,
    ...rtlOptions,
  });
  return { user: userEvent.setup(), queryClient, ...result };
}

// Re-export the RTL surface + userEvent so tests import everything from here.
export * from '@testing-library/react';
export { userEvent };
