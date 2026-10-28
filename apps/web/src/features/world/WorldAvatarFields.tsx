'use client';
import { useId } from 'react';
import { Check } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import {
  AVATAR_HAIR,
  AVATAR_HEADWEAR,
  AVATAR_OUTFITS,
  AVATAR_SKIN_IDS,
  AVATAR_COLOR_IDS,
  AVATAR_COLORS,
  type AvatarAppearance,
} from './avatar-catalogue';
import { avatarAppearanceSchema } from './avatar-protocol';
import { WorldAvatarPreview } from './WorldAvatarPreview';
import { WorldAvatarPresets } from './WorldAvatarPresets';

interface Props {
  lng: Language;
  appearance: AvatarAppearance;
  onChange(value: AvatarAppearance): void;
}
type Choice = 'hair' | 'skin' | 'outfit' | 'headwear';
export function WorldAvatarFields(props: Props) {
  const { lng, appearance, onChange } = props;
  const { t } = useTranslation(lng);
  const glasses = useId();
  const update = (field: keyof AvatarAppearance, value: unknown) => {
    const parsed = avatarAppearanceSchema.safeParse({ ...appearance, [field]: value });
    if (parsed.success) onChange(parsed.data);
  };
  return (
    <div className="world-avatar-fields">
      <WorldAvatarPreview lng={lng} appearance={appearance} />
      <div className="min-w-0 space-y-4">
        <WorldAvatarPresets {...props} />
        <ChoiceField {...props} field="skin" values={AVATAR_SKIN_IDS} />
        <Tabs defaultValue="hair">
          <TabsList className="grid min-h-11 w-full grid-cols-3">
            {(['hair', 'outfit', 'accessories'] as const).map(tab => (
              <TabsTrigger
                key={tab}
                value={tab}
                aria-label={t('world.avatar.tabs.' + tab)}
                className="min-h-11 min-w-0 truncate px-1 text-xs"
              >
                {t('world.avatar.tabs.' + tab)}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="hair" className="space-y-4 pt-2">
            <ChoiceField {...props} field="hair" values={AVATAR_HAIR} />
            <ColorField {...props} field="hair_color" />
          </TabsContent>
          <TabsContent value="outfit" className="space-y-4 pt-2">
            <ChoiceField {...props} field="outfit" values={AVATAR_OUTFITS} />
            <ColorField {...props} field="outfit_color" />
          </TabsContent>
          <TabsContent value="accessories" className="space-y-4 pt-2">
            <ChoiceField {...props} field="headwear" values={AVATAR_HEADWEAR} />
            {appearance.headwear !== 'none' && <ColorField {...props} field="headwear_color" />}
            <label htmlFor={glasses} className="flex min-h-11 items-center gap-3 text-sm">
              <input
                id={glasses}
                aria-label={t('world.avatar.glasses')}
                type="checkbox"
                className="size-5 accent-primary"
                checked={appearance.glasses}
                onChange={event => update('glasses', event.target.checked)}
              />
              {t('world.avatar.glasses')}
            </label>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
function ChoiceField({
  lng,
  appearance,
  onChange,
  field,
  values,
}: Props & { field: Choice; values: readonly string[] }) {
  const { t } = useTranslation(lng);
  const id = useId();
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {t('world.avatar.' + field)}
      </label>
      <select
        id={id}
        aria-label={t('world.avatar.' + field)}
        className="min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm"
        value={appearance[field]}
        onChange={event => {
          const parsed = avatarAppearanceSchema.safeParse({
            ...appearance,
            [field]: event.target.value,
          });
          if (parsed.success) onChange(parsed.data);
        }}
      >
        {values.map(value => (
          <option key={value} value={value}>
            {t('world.avatar.' + field + '_options.' + value)}
          </option>
        ))}
      </select>
    </div>
  );
}
function ColorField({
  lng,
  appearance,
  onChange,
  field,
}: Props & { field: 'hair_color' | 'outfit_color' | 'headwear_color' }) {
  const { t } = useTranslation(lng);
  const group = useId();
  return (
    <fieldset className="min-w-0">
      <legend className="mb-2 text-sm font-medium">{t('world.avatar.' + field)}</legend>
      <div className="world-avatar-colors">
        {AVATAR_COLOR_IDS.map(color => (
          <label
            key={color}
            htmlFor={group + color}
            className="relative grid size-11 cursor-pointer place-items-center"
            title={
              field === 'hair_color' && color === 'gold'
                ? t('world.avatar.blond')
                : t('world.avatar.colors.' + color)
            }
          >
            <input
              id={group + color}
              type="radio"
              className="peer absolute inset-0 z-10 size-full cursor-pointer opacity-0"
              name={group}
              value={color}
              checked={appearance[field] === color}
              aria-label={
                field === 'hair_color' && color === 'gold'
                  ? t('world.avatar.blond')
                  : t('world.avatar.colors.' + color)
              }
              onChange={() => onChange({ ...appearance, [field]: color })}
            />
            <span
              className="absolute inset-1 rounded-full border-2 border-background shadow-sm ring-1 ring-border peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary"
              style={{ backgroundColor: AVATAR_COLORS[color] }}
            />
            {appearance[field] === color && (
              <span
                className="relative grid size-5 place-items-center rounded-full bg-background text-foreground shadow-md"
                aria-hidden="true"
              >
                <Check className="size-3.5" />
              </span>
            )}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
