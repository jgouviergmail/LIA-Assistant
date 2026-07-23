/**
 * AuthProvider — the session boundary of the whole app (BFF pattern: the
 * session lives in an HTTP-only cookie, never in JS).
 *
 * Four properties carry real consequences and are pinned explicitly:
 *  - the mount check is **skipped on the public auth pages**, with or without a
 *    locale prefix — calling `/auth/me` there would 401 and risk a redirect
 *    loop on the very page that is supposed to let the user in;
 *  - `logout` clears the session and leaves for the login page **even when the
 *    API call fails** — a user who clicked "log out" must never stay logged in
 *    because the network hiccupped;
 *  - `refreshUser` keeps the **same object reference** when the payload has not
 *    changed, so a poll cannot re-render every consumer of the context;
 *  - `refreshUser` never throws (it is called from background paths), while
 *    `login`, `register` and the OAuth start all propagate their failure to the
 *    form that must display it.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { act, waitFor, renderHook } from '@/__tests__/test-utils';
import { makeUser } from '@/__tests__/factories';
import { CHAT_DRAFT_STORAGE_KEY_PREFIX } from '@/lib/constants';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get, post } }));

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('@/hooks/useLocalizedRouter', () => ({
  useLocalizedRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

import { AuthProvider } from '../auth';
import { useAuth } from '@/hooks/useAuth';

/**
 * Renders the provider and hands back the context it exposes. `renderHook`
 * with a wrapper is used rather than a probe component: capturing the context
 * into a module variable during render would be a side effect in render
 * (`react-hooks/globals`), the very thing the codebase forbids in production.
 */
function renderAuth() {
  const rendered = renderHook(() => useAuth(), {
    wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
  });
  return { ...rendered, context: () => rendered.result.current };
}

/** Waits for the mount-time session check to settle. */
async function settled(rendered: ReturnType<typeof renderAuth>) {
  await waitFor(() => expect(rendered.result.current.isLoading).toBe(false));
  return rendered;
}

/** The signed-in identity the context currently exposes. */
const identity = (rendered: ReturnType<typeof renderAuth>) =>
  rendered.result.current.user?.email ?? 'anonymous';

/** Puts the browser on a given path for the mount-time check. */
function browseTo(pathname: string) {
  Object.defineProperty(window, 'location', {
    value: { pathname, href: '' },
    writable: true,
    configurable: true,
  });
}

let originalLocation: Location;

beforeEach(() => {
  vi.clearAllMocks();
  originalLocation = window.location;
  browseTo('/fr/dashboard');
  get.mockResolvedValue(makeUser({ email: 'user@test.dev' }));
  post.mockResolvedValue({ user: makeUser({ email: 'user@test.dev' }) });
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  Object.defineProperty(window, 'location', { value: originalLocation, configurable: true });
  vi.restoreAllMocks();
});

describe('AuthProvider — session check on mount', () => {
  it('loads the session on a protected page', async () => {
    const rendered = await settled(renderAuth());

    expect(get).toHaveBeenCalledWith('/auth/me');
    expect(identity(rendered)).toBe('user@test.dev');
  });

  it('settles as anonymous when there is no valid session', async () => {
    get.mockRejectedValue(new Error('401'));
    const rendered = await settled(renderAuth());

    expect(identity(rendered)).toBe('anonymous');
  });

  it.each([
    '/login',
    '/register',
    '/oauth-callback',
    '/fr/login',
    '/en/register',
    '/de/oauth-callback',
  ])('never calls the session endpoint on %s', async pathname => {
    browseTo(pathname);
    const rendered = await settled(renderAuth());

    // Asking for the session here would 401 and risk a redirect loop.
    expect(get).not.toHaveBeenCalled();
    expect(identity(rendered)).toBe('anonymous');
  });

  it.each([
    '/fr/dashboard/settings',
    '/blog/login-tips',
    // Guards against a prefix match: these only *start* with a skipped word.
    // (`/registration-success` is safe by luck — `register` and `registration`
    // diverge at the 7th character — but a `/register-*` route would not be.)
    '/fr/loginbrand',
    '/fr/registration-success',
    '/register-help',
  ])('still checks the session on %s', async pathname => {
    browseTo(pathname);
    renderAuth();

    await waitFor(() => expect(get).toHaveBeenCalledWith('/auth/me'));
  });

  it('still skips the check on a sub-path of an auth page', async () => {
    browseTo('/fr/login/reset');
    await settled(renderAuth());

    expect(get).not.toHaveBeenCalled();
  });
});

describe('AuthProvider — signing in', () => {
  it('sends the credentials with the session length the user asked for', async () => {
    const rendered = await settled(renderAuth());
    const { context } = rendered;

    await act(async () => {
      await context().login('user@test.dev', 'Sup3rSecret!!', true);
    });

    expect(post).toHaveBeenCalledWith('/auth/login', {
      email: 'user@test.dev',
      password: 'Sup3rSecret!!',
      remember_me: true,
    });
    expect(identity(rendered)).toBe('user@test.dev');
  });

  it('defaults to a short session', async () => {
    const rendered = await settled(renderAuth());
    const { context } = rendered;

    await act(async () => {
      await context().login('user@test.dev', 'Sup3rSecret!!');
    });

    expect(post).toHaveBeenCalledWith(
      '/auth/login',
      expect.objectContaining({ remember_me: false })
    );
  });

  it('propagates a refused login to the form', async () => {
    post.mockRejectedValue(new Error('Invalid credentials'));
    const rendered = await settled(renderAuth());
    const { context } = rendered;

    await expect(context().login('user@test.dev', 'wrong')).rejects.toThrow('Invalid credentials');
    expect(identity(rendered)).toBe('user@test.dev');
  });
});

describe('AuthProvider — registering', () => {
  it('sends the profile fields the account needs', async () => {
    const rendered = await settled(renderAuth());
    const { context } = rendered;

    await act(async () => {
      await context().register(
        'new@test.dev',
        'Sup3rSecret!!',
        'Jean Dupont',
        true,
        'Europe/Paris',
        'fr'
      );
    });

    expect(post).toHaveBeenCalledWith('/auth/register', {
      email: 'new@test.dev',
      password: 'Sup3rSecret!!',
      full_name: 'Jean Dupont',
      remember_me: true,
      timezone: 'Europe/Paris',
      language: 'fr',
    });
  });

  it('lets the optional fields through as undefined', async () => {
    const rendered = await settled(renderAuth());
    const { context } = rendered;

    await act(async () => {
      await context().register('new@test.dev', 'Sup3rSecret!!');
    });

    expect(post).toHaveBeenCalledWith('/auth/register', {
      email: 'new@test.dev',
      password: 'Sup3rSecret!!',
      full_name: undefined,
      remember_me: false,
      timezone: undefined,
      language: undefined,
    });
  });

  it('propagates a refused registration', async () => {
    post.mockRejectedValue(new Error('Email already used'));
    const rendered = await settled(renderAuth());
    const { context } = rendered;

    await expect(context().register('new@test.dev', 'x')).rejects.toThrow('Email already used');
  });
});

describe('AuthProvider — signing out', () => {
  it('ends the session and leaves for the login page', async () => {
    const rendered = await settled(renderAuth());
    const { context } = rendered;

    await act(async () => {
      await context().logout();
    });

    expect(post).toHaveBeenCalledWith('/auth/logout');
    expect(identity(rendered)).toBe('anonymous');
    expect(push).toHaveBeenCalledWith('/login');
  });

  it('logs the user out locally even when the server refuses', async () => {
    const rendered = await settled(renderAuth());
    const { context } = rendered;
    post.mockRejectedValue(new Error('gateway down'));

    await act(async () => {
      await context().logout();
    });

    // Staying logged in because the network hiccupped would be the real bug.
    expect(identity(rendered)).toBe('anonymous');
    expect(push).toHaveBeenCalledWith('/login');
  });

  it('purges the persisted chat draft of the departing account (UXR A7)', async () => {
    // A shared computer must not leak one account's draft to the next session.
    localStorage.setItem(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}u1`, 'brouillon privé');
    localStorage.setItem(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}other`, 'autre compte');
    const rendered = await settled(renderAuth());

    await act(async () => {
      await rendered.context().logout();
    });

    expect(localStorage.getItem(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}u1`)).toBeNull();
    expect(localStorage.getItem(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}other`)).toBe('autre compte');
  });

  it('has no draft to purge when signing out from an anonymous state', async () => {
    get.mockRejectedValue(new Error('401'));
    localStorage.setItem(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}u1`, 'reste intact');
    const rendered = await settled(renderAuth());

    await act(async () => {
      await rendered.context().logout();
    });

    // No signed-in user → nothing purged, navigation still happens.
    expect(localStorage.getItem(`${CHAT_DRAFT_STORAGE_KEY_PREFIX}u1`)).toBe('reste intact');
    expect(push).toHaveBeenCalledWith('/login');
  });
});

describe('AuthProvider — Google OAuth', () => {
  it('hands the browser over to the consent screen', async () => {
    get.mockImplementation((endpoint: string) =>
      endpoint === '/auth/google/login'
        ? Promise.resolve({ authorization_url: 'https://accounts.google.com/o/oauth2/auth' })
        : Promise.resolve(makeUser())
    );
    const rendered = await settled(renderAuth());
    const { context } = rendered;

    await act(async () => {
      await context().initiateGoogleOAuth();
    });

    expect(window.location.href).toBe('https://accounts.google.com/o/oauth2/auth');
  });

  it('propagates a failed OAuth start', async () => {
    const rendered = await settled(renderAuth());
    const { context } = rendered;
    get.mockRejectedValue(new Error('provider down'));

    await expect(context().initiateGoogleOAuth()).rejects.toThrow('provider down');
  });
});

describe('AuthProvider — refreshing the user', () => {
  it('picks up a profile change', async () => {
    const rendered = await settled(renderAuth());
    const { context } = rendered;
    get.mockResolvedValue(makeUser({ email: 'user@test.dev', full_name: 'Nouveau nom' }));

    await act(async () => {
      await context().refreshUser();
    });

    expect(context().user?.full_name).toBe('Nouveau nom');
  });

  it('keeps the very same object when nothing changed', async () => {
    const rendered = await settled(renderAuth());
    const { context } = rendered;
    const before = context().user;

    // The server answers with an equal — but not identical — payload.
    get.mockResolvedValue(makeUser({ email: 'user@test.dev' }));
    await act(async () => {
      await context().refreshUser();
    });

    // Reference equality is the point: a poll must not re-render every consumer.
    expect(context().user).toBe(before);
  });

  it('never throws, so a background refresh cannot break the page', async () => {
    const rendered = await settled(renderAuth());
    const { context } = rendered;
    get.mockRejectedValue(new Error('offline'));

    await expect(context().refreshUser()).resolves.toBeUndefined();
    expect(context().user?.email).toBe('user@test.dev');
  });
});

describe('useAuth', () => {
  it('refuses to be used outside the provider', () => {
    // The context default is `undefined` precisely so this is loud rather than
    // a silent `null` user that every consumer would misread as "logged out".
    expect(() => renderHook(() => useAuth())).toThrow(/must be used within an AuthProvider/);
  });
});
