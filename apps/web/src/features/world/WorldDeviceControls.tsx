'use client';
import { WorldSoundWidget } from './WorldSoundWidget';
import type { WorldSoundControl } from './useWorldSound';
import {
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type Ref,
  type RefObject,
  type ReactNode,
} from 'react';
import dynamic from 'next/dynamic';
import {
  Bell,
  CloudSun,
  MessageSquareText,
  Phone,
  Radio,
  Smartphone,
  ArrowLeft,
  PanelsTopLeft,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from '@/components/theme-toggle';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { useAuth } from '@/hooks/useAuth';
import type { Notification } from '@/hooks/useNotifications';
import { useSettingsAvailability } from '@/hooks/useSettingsAvailability';
import { useRadioCommand } from '@/components/radio/RadioControl';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { WorldPrivateActivity } from './WorldAccountGuard';
import type { DeviceNotice } from './device-inbox';
import type { SceneActivity } from './activity-catalogue';
import { useWorldPrivateSignals, type WorldPrivateSignalsControl } from './useWorldPrivateSignals';
import { WorldSignalActions } from './WorldSignalActions';
export interface WorldDeviceHandle {
  openNotice(key: string): boolean;
}
const WeatherPanel = dynamic(() => import('./WorldWeatherPanel').then(m => m.WorldWeatherPanel), {
  ssr: false,
});
const FocusedSms = dynamic(
  () => import('@/components/sms/SmsFocusedMessage').then(m => m.SmsFocusedMessage),
  { ssr: false }
);
interface Props {
  extras?: ReactNode;
  signals?: WorldPrivateSignalsControl;
  deviceRef?: Ref<WorldDeviceHandle>;
  onSignal?: (propId: string) => boolean;
  sound?: WorldSoundControl;
  lng: Language;
  ownerId: string;
  enabled: boolean;
  interactive: boolean;
  onOpen: (open: boolean) => void;
  onActivity: (activity: SceneActivity) => void;
  onProactive?(notice: Notification): void;
}
export function WorldDeviceControls(props: Props) {
  return props.signals ? (
    <OwnedWorldDeviceControls key={props.ownerId} {...props} signals={props.signals} />
  ) : (
    <ConnectedDeviceControls key={props.ownerId} {...props} />
  );
}
function ConnectedDeviceControls(props: Props) {
  const signals = useWorldPrivateSignals(props.ownerId, props.enabled, props.onProactive);
  return <OwnedWorldDeviceControls {...props} signals={signals} />;
}
function OwnedWorldDeviceControls({
  lng,
  ownerId,
  enabled,
  interactive,
  onOpen,
  onActivity,
  signals,
  onSignal,
  deviceRef,
  sound,
  extras,
}: Props & { signals: WorldPrivateSignalsControl }) {
  const { t } = useTranslation(lng),
    { user } = useAuth();
  const availability = useSettingsAvailability(),
    authorized =
      enabled &&
      user?.id === ownerId &&
      user.is_active &&
      signals.authorized &&
      signals.lifetime.ownerId === ownerId;
  const { entries, smsEnabled } = signals;
  const [open, setOpen] = useState(false);
  const [forecast, setForecast] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  useImperativeHandle(deviceRef, () => ({
    openNotice(key) {
      if (!authorized || !interactive || !signals.read(key)) return false;
      setSelected(key);
      setExpanded(false);
      setOpen(true);
      return true;
    },
  }));
  const radio = useRadioCommand(authorized && availability.radioEnabled);
  const visible = authorized && [open, forecast].some(Boolean);
  useEffect(() => {
    onOpen(visible);
    return () => onOpen(false);
  }, [visible, onOpen]);
  const sms = entries.filter(n => n.kind === 'sms' && !n.read).length,
    reminders = entries.filter(n => n.kind === 'reminder' && !n.read).length;
  const current = entries.find(n => n.key === selected);
  const activate = (activity: SceneActivity) => {
    setOpen(false);
    setForecast(false);
    setExpanded(false);
    onActivity(activity);
  };
  if (!authorized) return null;
  return (
    <>
      <DeviceToolbar
        extras={extras}
        connected={signals.connected}
        lng={lng}
        radio={radio}
        sound={sound}
        interactive={interactive}
        sms={sms}
        reminders={reminders}
        expanded={expanded}
        onExpanded={setExpanded}
        onPhone={() => {
          setSelected(null);
          setExpanded(false);
          setOpen(true);
        }}
        onWeather={() => {
          setExpanded(false);
          setForecast(true);
        }}
      />

      <WorldPrivateActivity>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent className="max-h-[85dvh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('world.device.title')}</DialogTitle>
              <DialogDescription>{t('world.device.private')}</DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-2">
              <Button
                className="min-h-11 whitespace-normal"
                onClick={() => activate({ kind: 'compose', id: 'call' })}
              >
                <Phone className="size-4" aria-hidden="true" />
                {t('world.activities.call')}
              </Button>
              {smsEnabled && (
                <Button
                  variant="outline"
                  className="min-h-11 whitespace-normal"
                  onClick={() => activate({ kind: 'workspace', id: 'sms' })}
                >
                  <MessageSquareText className="size-4" aria-hidden="true" />
                  {t('sms.archive')}
                </Button>
              )}
            </div>
            {entries.length === 0 && (
              <p className="text-sm text-muted-foreground">{t('world.device.no_notifications')}</p>
            )}
            <DeviceInboxContent
              lng={lng}
              current={current}
              entries={entries}
              smsEnabled={smsEnabled}
              onBack={() => setSelected(null)}
              activate={activate}
              onRead={key => {
                if (signals.read(key)) setSelected(key);
              }}
            />
            <WorldSignalActions
              lng={lng}
              signals={signals.signals}
              onSelect={
                onSignal
                  ? propId => {
                      if (!onSignal(propId)) return false;
                      setOpen(false);
                      return true;
                    }
                  : undefined
              }
            />
            {signals.remindersUncertain && (
              <p role="status" className="text-sm text-muted-foreground">
                {t('world.signals.reminders_gap')}
              </p>
            )}
          </DialogContent>
        </Dialog>
        <Dialog open={forecast} onOpenChange={setForecast}>
          <DialogContent className="max-h-[85dvh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{t('world.device.forecast')}</DialogTitle>
              <DialogDescription>{t('world.device.forecast_hint')}</DialogDescription>
            </DialogHeader>
            {forecast && (
              <WeatherPanel
                lng={lng}
                ownerId={ownerId}
                onAsk={() => activate({ kind: 'command', id: 'weather' })}
              />
            )}
          </DialogContent>
        </Dialog>
      </WorldPrivateActivity>
    </>
  );
}

function DeviceToolbar({
  extras,
  connected,
  sound,
  lng,
  radio,
  interactive,
  sms,
  reminders,
  onPhone,
  onWeather,
  expanded,
  onExpanded,
}: {
  extras?: ReactNode;
  connected: boolean;
  lng: Language;
  radio: ReturnType<typeof useRadioCommand>;
  sound?: WorldSoundControl;
  interactive: boolean;
  sms: number;
  reminders: number;
  onPhone(): void;
  onWeather(): void;
  expanded: boolean;
  onExpanded(value: boolean): void;
}) {
  const { t } = useTranslation(lng);
  const shell = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  useToolDismissal(expanded, onExpanded, shell, toggle);
  return (
    <div ref={shell} className="world-device-shell" data-expanded={expanded}>
      <Button
        ref={toggle}
        className="world-device-toggle min-h-11 min-w-11"
        size="icon"
        variant="outline"
        disabled={!interactive}
        aria-expanded={expanded}
        aria-label={t('world.device.tools')}
        onClick={() => onExpanded(!expanded)}
      >
        <PanelsTopLeft className="size-5" aria-hidden="true" />
      </Button>
      <div
        className="world-device-controls rounded-xl border bg-background/95 p-1 shadow-lg"
        data-notifications-connected={connected}
        role="group"
        aria-label={t('world.device.tools')}
      >
        {radio && (
          <Button
            size="icon"
            variant="ghost"
            className="min-h-11 min-w-11"
            disabled={!interactive || radio.busy}
            aria-pressed={radio.onAir}
            aria-label={t(radio.onAir ? 'radio.header.stop' : 'radio.header.start')}
            title={t(radio.onAir ? 'radio.header.stop' : 'radio.header.start')}
            onClick={radio.run}
          >
            <span className="world-device-icon world-radio-icon">
              <Radio aria-hidden="true" />
            </span>
            <span className="world-device-label">{t('world.device.radio_short')}</span>
          </Button>
        )}
        <Button
          size="icon"
          variant="ghost"
          className="relative min-h-11 min-w-11"
          disabled={!interactive}
          aria-label={t('world.device.phone', { sms, reminders })}
          title={t('world.device.phone_short')}
          onClick={onPhone}
        >
          <span className="world-device-icon world-phone-icon">
            <Smartphone aria-hidden="true" />
          </span>
          <span className="world-device-label">{t('world.device.phone_short')}</span>
          {sms > 0 && (
            <span
              className="absolute -left-1 -top-1 flex items-center rounded-full bg-primary px-1 text-[10px] text-primary-foreground motion-safe:animate-pulse"
              aria-hidden="true"
            >
              <MessageSquareText className="size-3" />
              {sms}
            </span>
          )}
          {reminders > 0 && (
            <span
              className="absolute -right-1 -top-1 flex items-center rounded-full bg-amber-600 px-1 text-[10px] text-white motion-safe:animate-pulse"
              aria-hidden="true"
            >
              <Bell className="size-3" />
              {reminders}
            </span>
          )}
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="min-h-11 min-w-11"
          disabled={!interactive}
          aria-label={t('world.device.forecast')}
          title={t('world.device.forecast')}
          onClick={onWeather}
        >
          <span className="world-device-icon world-weather-icon">
            <CloudSun aria-hidden="true" />
          </span>
          <span className="world-device-label">{t('world.device.weather_short')}</span>
        </Button>
        {sound && <WorldSoundWidget lng={lng} sound={sound} />}
        {extras}
        <ThemeToggle />
      </div>
    </div>
  );
}
function useToolDismissal(
  expanded: boolean,
  onExpanded: (value: boolean) => void,
  shell: RefObject<HTMLDivElement | null>,
  toggle: RefObject<HTMLButtonElement | null>
) {
  useEffect(() => {
    if (!expanded) return;
    const dismiss = (event: PointerEvent) => {
      if (
        event.target instanceof Element &&
        event.target.closest('[data-world-sound-panel], [data-world-native-panel]')
      )
        return;
      if (event.target instanceof Node && !shell.current?.contains(event.target)) onExpanded(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (
        event.key !== 'Escape' ||
        !(event.target instanceof Node) ||
        !shell.current?.contains(event.target)
      )
        return;
      event.stopPropagation();
      onExpanded(false);
      toggle.current?.focus();
    };
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', dismiss);
      document.removeEventListener('keydown', escape);
    };
  }, [expanded, onExpanded, shell, toggle]);
}
function DeviceInboxContent({
  lng,
  current,
  entries,
  smsEnabled,
  onBack,
  onRead,
  activate,
}: {
  lng: Language;
  current: DeviceNotice | undefined;
  entries: readonly DeviceNotice[];
  smsEnabled: boolean;
  onBack(): void;
  onRead(key: string): void;
  activate(activity: SceneActivity): void;
}) {
  const { t } = useTranslation(lng);
  return (
    <>
      {current ? (
        <>
          <Button variant="ghost" className="w-fit" onClick={onBack}>
            <ArrowLeft className="size-4" aria-hidden="true" />
            {t('common.back')}
          </Button>
          {current.kind === 'sms' && smsEnabled ? (
            <FocusedSms key={current.messageId} messageId={current.messageId} lng={lng} />
          ) : current.kind === 'reminder' ? (
            <p className="whitespace-pre-wrap break-words" dir="auto">
              {current.content}
            </p>
          ) : null}
          <Button
            variant="outline"
            onClick={() =>
              activate(
                current.kind === 'sms'
                  ? { kind: 'workspace', id: 'sms' }
                  : { kind: 'native', token: 'reminders' }
              )
            }
          >
            {t(current.kind === 'sms' ? 'sms.archive' : 'reminders.settings.title')}
          </Button>
        </>
      ) : (
        <ul className="space-y-2">
          {entries.map(n => (
            <li key={n.key}>
              <Button
                variant={n.read ? 'ghost' : 'outline'}
                className="min-h-11 w-full justify-start"
                onClick={() => onRead(n.key)}
              >
                {n.kind === 'sms' ? (
                  <MessageSquareText className="size-4 text-primary" aria-hidden="true" />
                ) : (
                  <Bell className="size-4 text-primary" aria-hidden="true" />
                )}
                {t(n.kind === 'sms' ? 'sms.new_received' : 'world.device.reminder')}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
