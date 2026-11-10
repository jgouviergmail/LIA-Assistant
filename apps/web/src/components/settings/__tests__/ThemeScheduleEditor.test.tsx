import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ThemeScheduleEditor } from '../ThemeScheduleEditor';

vi.mock('@/i18n/client', async () => {
  const { createInstance } = await import('i18next');
  const en = await import('../../../../locales/en/translation.json');
  const fr = await import('../../../../locales/fr/translation.json');
  const instance = createInstance();
  await instance.init({
    resources: { en: { translation: en.default }, fr: { translation: fr.default } },
    fallbackLng: 'en',
  });
  return { useTranslation: (lng: string) => ({ t: instance.getFixedT(lng) }) };
});

const schedule = { lightStartMinute: 420, darkStartMinute: 1200, timezone: 'Europe/Paris' };

describe('the automatic schedule form', () => {
  it.each([
    ['en', 'Light mode starts', 'Absolute black starts'],
    ['fr', 'Début du mode clair', 'Début du noir absolu'],
  ] as const)(
    'names both fields in %s and saves the pair together',
    async (lng, lightName, darkName) => {
      const save = vi.fn().mockResolvedValue(undefined);
      render(
        <ThemeScheduleEditor lng={lng} schedule={schedule} setSchedule={save} saving={false} />
      );
      const light = screen.getByLabelText(lightName);
      const dark = screen.getByLabelText(darkName);
      fireEvent.change(light, { target: { value: '20:00' } });
      await userEvent.click(screen.getByRole('button'));
      expect(save).not.toHaveBeenCalled();
      expect(screen.getByRole('alert')).toBeVisible();
      fireEvent.change(dark, { target: { value: '07:00' } });
      await userEvent.click(screen.getByRole('button'));
      expect(save).toHaveBeenCalledExactlyOnceWith({
        lightStartMinute: 1200,
        darkStartMinute: 420,
      });
    }
  );

  it('keeps typed values and focus through an unrelated rerender', () => {
    const save = vi.fn();
    const { rerender } = render(
      <ThemeScheduleEditor lng="en" schedule={schedule} setSchedule={save} saving={false} />
    );
    const light = screen.getByLabelText('Light mode starts');
    light.focus();
    fireEvent.change(light, { target: { value: '08:15' } });
    rerender(
      <ThemeScheduleEditor lng="en" schedule={{ ...schedule }} setSchedule={save} saving={false} />
    );
    expect(light).toHaveFocus();
    expect(light).toHaveValue('08:15');
  });
});
