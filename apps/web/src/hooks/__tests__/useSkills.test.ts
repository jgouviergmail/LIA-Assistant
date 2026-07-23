/**
 * useSkills — the skills catalogue, for the user panel and the admin one.
 *
 * Three rules deserve their own oracle:
 *  - **importing the same skill twice replaces it** instead of duplicating the
 *    row (skills are keyed by name, not by id);
 *  - the personal toggle writes `enabled_for_user` while the admin toggle
 *    writes `admin_enabled` — two different fields on the same row, the kind of
 *    pair that gets crossed in a refactor;
 *  - downloading builds a temporary anchor, clicks it and **cleans up after
 *    itself** (element removed, Object URL revoked).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderHook, act } from '@/__tests__/test-utils';
import {
  mutateSpy,
  mutationResult,
  queryResult,
  setDataSpy,
  takeUpdater,
} from '@/__tests__/api-mocks';

const { useApiQuery } = vi.hoisted(() => ({ useApiQuery: vi.fn() }));
vi.mock('@/hooks/useApiQuery', () => ({ useApiQuery }));
const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));

import { useSkills } from '../useSkills';
import type { Skill, SkillListResponse } from '@/hooks/useSkills';

const ENDPOINT = '/skills';

function skill(over: Partial<Skill> = {}): Skill {
  return {
    name: 'weather-report',
    description: 'Daily weather digest',
    descriptions: null,
    scope: 'user',
    category: 'productivity',
    priority: 10,
    always_loaded: false,
    has_scripts: false,
    has_plan_template: false,
    enabled_for_user: true,
    ...over,
  };
}

/** The eight mutations, in the order the hook declares them. */
const mutate = {
  remove: mutateSpy(),
  reload: mutateSpy(),
  toggle: mutateSpy(),
  systemToggle: mutateSpy(),
  importFromUrl: mutateSpy(),
  translate: mutateSpy(),
  describe: mutateSpy(),
  removeAdmin: mutateSpy(),
};
const ORDER = [
  mutate.remove,
  mutate.reload,
  mutate.toggle,
  mutate.systemToggle,
  mutate.importFromUrl,
  mutate.translate,
  mutate.describe,
  mutate.removeAdmin,
];

const setData = setDataSpy<SkillListResponse>();
const refetch = vi.fn();
const fetchMock = vi.fn();
const createObjectURL = vi.fn(() => 'blob:archive');
const revokeObjectURL = vi.fn();

function cache(over: Partial<SkillListResponse> = {}): SkillListResponse {
  return { skills: [skill()], total: 1, ...over };
}

function setupWith(data: SkillListResponse | undefined, adminView = false) {
  useApiQuery.mockReturnValue(queryResult<SkillListResponse>({ data, setData, refetch }));
  return renderHook(() => useSkills(adminView));
}

const setup = (data: SkillListResponse = cache(), adminView = false) => setupWith(data, adminView);

function applyUpdater(previous: SkillListResponse | undefined) {
  return takeUpdater<SkillListResponse>(setData)(previous);
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  let cursor = 0;
  useApiMutation.mockImplementation(() =>
    mutationResult({ mutate: ORDER[cursor++ % ORDER.length] })
  );
  Object.values(mutate).forEach(m => m.mockResolvedValue(undefined));
  fetchMock.mockResolvedValue(jsonResponse(skill()));
  vi.stubGlobal('fetch', fetchMock);
  Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
  Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
});

afterEach(() => vi.unstubAllGlobals());

describe('useSkills — reading', () => {
  it('reads the user catalogue by default', () => {
    const { result } = setup();

    expect(useApiQuery).toHaveBeenCalledWith(ENDPOINT, expect.objectContaining({}));
    expect(result.current.skills).toHaveLength(1);
    expect(result.current.total).toBe(1);
  });

  it('reads the admin catalogue in admin view', () => {
    setup(cache(), true);

    expect(useApiQuery).toHaveBeenCalledWith(`${ENDPOINT}/admin/list`, expect.objectContaining({}));
  });

  it('degrades to an empty catalogue on a missing payload', () => {
    const { result } = setupWith(undefined);

    expect(result.current.skills).toEqual([]);
    expect(result.current.total).toBe(0);
  });
});

describe('useSkills — importing', () => {
  const archive = () => new File(['x'], 'weather.zip', { type: 'application/zip' });

  it('uploads to the user directory with the session cookie', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.importSkill(archive());
    });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(`${ENDPOINT}/import`);
    expect(init).toMatchObject({ method: 'POST', credentials: 'include' });
    expect(init.body).toBeInstanceOf(FormData);
  });

  it('uploads to the system directory for an admin import', async () => {
    const { result } = setup(cache(), true);

    await act(async () => {
      await result.current.importAdminSkill(archive());
    });

    expect(String(fetchMock.mock.calls[0][0])).toContain(`${ENDPOINT}/admin/import`);
  });

  it('adds a brand-new skill to the catalogue', async () => {
    const imported = skill({ name: 'traffic-report' });
    fetchMock.mockResolvedValue(jsonResponse(imported));
    const { result } = setup();

    await act(async () => {
      await result.current.importSkill(archive());
    });

    expect(applyUpdater(cache())).toEqual({ skills: [skill(), imported], total: 2 });
  });

  it('replaces a skill re-imported under the same name, without counting it twice', async () => {
    const reimported = skill({ description: 'Updated digest' });
    fetchMock.mockResolvedValue(jsonResponse(reimported));
    const { result } = setup();

    await act(async () => {
      await result.current.importSkill(archive());
    });

    expect(applyUpdater(cache())).toEqual({ skills: [reimported], total: 1 });
  });

  it('surfaces the reason the server refused the archive', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'SKILL.md manquant' }, 422));
    const { result } = setup();

    await expect(result.current.importSkill(archive())).rejects.toThrow('SKILL.md manquant');
    expect(setData).not.toHaveBeenCalled();
  });

  it('falls back to the status when the refusal has no readable body', async () => {
    fetchMock.mockResolvedValue(new Response('boom', { status: 500 }));
    const { result } = setup();

    await expect(result.current.importSkill(archive())).rejects.toThrow('Import failed (500)');
  });

  it('imports from an https URL through the dedicated endpoint (UXR Lot 10)', async () => {
    const imported = skill({ name: 'net-skill' });
    mutate.importFromUrl.mockResolvedValue(imported);
    const { result } = setup();

    await act(async () => {
      await result.current.importFromUrl('https://example.com/net-skill.zip');
    });

    expect(mutate.importFromUrl).toHaveBeenCalledWith(`${ENDPOINT}/import-from-url`, {
      url: 'https://example.com/net-skill.zip',
    });
    expect(applyUpdater(cache())).toEqual({ skills: [skill(), imported], total: 2 });
  });
});

describe('useSkills — toggles', () => {
  it('writes the personal preference only', async () => {
    mutate.toggle.mockResolvedValue({ skill_name: 'weather-report', enabled_for_user: false });
    const { result } = setup();

    await act(async () => {
      await result.current.toggleSkill('weather-report');
    });

    expect(mutate.toggle).toHaveBeenCalledWith(`${ENDPOINT}/weather-report/toggle`);
    const next = applyUpdater(cache({ skills: [skill({ admin_enabled: true })] }));
    expect(next?.skills[0]).toMatchObject({ enabled_for_user: false, admin_enabled: true });
  });

  it('writes the system-level flag only', async () => {
    mutate.systemToggle.mockResolvedValue({ skill_name: 'weather-report', admin_enabled: false });
    const { result } = setup(cache(), true);

    await act(async () => {
      await result.current.adminSystemToggleSkill('weather-report');
    });

    expect(mutate.systemToggle).toHaveBeenCalledWith(
      `${ENDPOINT}/admin/weather-report/system-toggle`
    );
    const next = applyUpdater(cache({ skills: [skill({ admin_enabled: true })] }));
    expect(next?.skills[0]).toMatchObject({ admin_enabled: false, enabled_for_user: true });
  });

  it('leaves the catalogue alone when a toggle is refused', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.toggleSkill('weather-report');
    });

    expect(setData).not.toHaveBeenCalled();
  });
});

describe('useSkills — removing', () => {
  it('deletes a user skill and decrements the count', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.deleteSkill('weather-report');
    });

    expect(mutate.remove).toHaveBeenCalledWith(`${ENDPOINT}/weather-report`);
    expect(applyUpdater(cache({ skills: [skill(), skill({ name: 'other' })], total: 2 }))).toEqual({
      skills: [skill({ name: 'other' })],
      total: 1,
    });
  });

  it('deletes a system skill through the admin route', async () => {
    const { result } = setup(cache(), true);

    await act(async () => {
      await result.current.deleteAdminSkill('weather-report');
    });

    expect(mutate.removeAdmin).toHaveBeenCalledWith(`${ENDPOINT}/admin/weather-report`);
    expect(applyUpdater(cache())).toEqual({ skills: [], total: 0 });
  });
});

describe('useSkills — reloading the catalogue', () => {
  it('refetches once the server confirms the reload', async () => {
    mutate.reload.mockResolvedValue({ count: 7 });
    const { result } = setup();

    await act(async () => {
      await result.current.reloadSkills();
    });

    expect(mutate.reload).toHaveBeenCalledWith(`${ENDPOINT}/reload`);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('does not refetch when the reload failed', async () => {
    const { result } = setup();

    await act(async () => {
      await result.current.reloadSkills();
    });

    expect(refetch).not.toHaveBeenCalled();
  });
});

describe('useSkills — descriptions', () => {
  const descriptions = { fr: 'Météo du jour', en: 'Daily weather' };

  it('stores the translations the server generated', async () => {
    mutate.translate.mockResolvedValue({ skill_name: 'weather-report', descriptions });
    const { result } = setup(cache(), true);

    await act(async () => {
      await result.current.translateSkillDescription('weather-report');
    });

    expect(mutate.translate).toHaveBeenCalledWith(
      `${ENDPOINT}/admin/weather-report/translate-description`
    );
    expect(applyUpdater(cache())?.skills[0].descriptions).toEqual(descriptions);
  });

  it('sends the edited description with its source language', async () => {
    mutate.describe.mockResolvedValue({ skill_name: 'weather-report', descriptions });
    const { result } = setup(cache(), true);

    await act(async () => {
      await result.current.updateAdminSkillDescription('weather-report', 'Météo du jour', 'fr');
    });

    expect(mutate.describe).toHaveBeenCalledWith(`${ENDPOINT}/admin/weather-report/description`, {
      description: 'Météo du jour',
      source_language: 'fr',
    });
    expect(applyUpdater(cache())?.skills[0].descriptions).toEqual(descriptions);
  });
});

describe('useSkills — downloading', () => {
  it('downloads the archive and cleans up after itself', async () => {
    fetchMock.mockResolvedValue(new Response('zip-bytes', { status: 200 }));
    const { result } = setup();
    const appended: string[] = [];
    const clicked = vi.fn();
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const element = realCreate(tag);
      if (tag === 'a') {
        element.addEventListener('click', event => {
          event.preventDefault();
          clicked();
        });
      }
      return element;
    });
    const appendSpy = vi.spyOn(document.body, 'appendChild');
    const removeSpy = vi.spyOn(document.body, 'removeChild');

    await act(async () => {
      await result.current.downloadSkill('weather-report');
    });

    const anchor = appendSpy.mock.calls[0][0] as HTMLAnchorElement;
    appended.push(anchor.download);
    expect(String(fetchMock.mock.calls[0][0])).toContain(`${ENDPOINT}/weather-report/download`);
    expect(anchor.href).toContain('blob:archive');
    expect(appended).toEqual(['weather-report.zip']);
    expect(clicked).toHaveBeenCalledTimes(1);
    // No orphan node, no leaked Object URL.
    expect(removeSpy).toHaveBeenCalledWith(anchor);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:archive');
  });

  it('uses the admin route for a system skill', async () => {
    fetchMock.mockResolvedValue(new Response('zip-bytes', { status: 200 }));
    const { result } = setup(cache(), true);

    await act(async () => {
      await result.current.downloadSkill('weather-report', true);
    });

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      `${ENDPOINT}/admin/weather-report/download`
    );
  });

  it('refuses to build a file out of an error response', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 404 }));
    const { result } = setup();

    await expect(result.current.downloadSkill('ghost')).rejects.toThrow('Download failed (404)');
    expect(createObjectURL).not.toHaveBeenCalled();
  });
});

describe('useSkills — updaters on an empty cache', () => {
  it.each([
    ['delete', (h: ReturnType<typeof useSkills>) => h.deleteSkill('weather-report')],
    ['delete-admin', (h: ReturnType<typeof useSkills>) => h.deleteAdminSkill('weather-report')],
    ['toggle', (h: ReturnType<typeof useSkills>) => h.toggleSkill('weather-report')],
    [
      'system-toggle',
      (h: ReturnType<typeof useSkills>) => h.adminSystemToggleSkill('weather-report'),
    ],
    [
      'translate',
      (h: ReturnType<typeof useSkills>) => h.translateSkillDescription('weather-report'),
    ],
  ])('%s leaves an empty cache untouched', async (_label, run) => {
    Object.values(mutate).forEach(m =>
      m.mockResolvedValue({
        skill_name: 'weather-report',
        enabled_for_user: false,
        admin_enabled: false,
        descriptions: {},
      })
    );
    const { result } = setup();

    await act(async () => {
      await run(result.current);
    });

    expect(applyUpdater(undefined)).toBeUndefined();
  });
});
