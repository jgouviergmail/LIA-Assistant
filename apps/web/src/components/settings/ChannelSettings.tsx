'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { MessageCircle, Link2, Unlink, Copy, Check } from 'lucide-react';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  useChannelBindings,
  type ChannelBinding,
  type OTPGenerateResponse,
} from '@/hooks/useChannelBindings';
import { toast } from 'sonner';

interface ChannelSettingsProps {
  lng: Language;
}

export function ChannelSettings({ lng }: ChannelSettingsProps) {
  const { t } = useTranslation(lng);
  const {
    bindings,
    telegramBotUsername,
    loading,
    generateOtp,
    toggleBinding,
    unlinkBinding,
    generatingOtp,
    toggling,
    unlinking,
  } = useChannelBindings();

  // OTP dialog state
  const [showOtpDialog, setShowOtpDialog] = useState(false);
  const [otpData, setOtpData] = useState<OTPGenerateResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Unlink confirm state
  const [unlinkingBindingId, setUnlinkingBindingId] = useState<string | null>(null);

  // Find telegram binding (at most one per plan)
  const telegramBinding = bindings.find((b) => b.channel_type === 'telegram');

  // Countdown timer for OTP expiration
  useEffect(() => {
    if (countdown <= 0 && countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, [countdown]);

  // Generate OTP
  const handleGenerateOtp = useCallback(async () => {
    try {
      const result = await generateOtp('telegram');
      if (result) {
        setOtpData(result);
        setShowOtpDialog(true);
        setCopied(false);
        setCountdown(result.expires_in_seconds);
        // Start countdown
        if (countdownRef.current) clearInterval(countdownRef.current);
        countdownRef.current = setInterval(() => {
          setCountdown((prev) => {
            if (prev <= 1) {
              if (countdownRef.current) clearInterval(countdownRef.current);
              return 0;
            }
            return prev - 1;
          });
        }, 1000);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('common.error'));
    }
  }, [generateOtp, t]);

  // Copy /start command to clipboard
  const handleCopyCommand = useCallback(async () => {
    if (!otpData) return;
    try {
      await navigator.clipboard.writeText(`/start ${otpData.code}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  }, [otpData]);

  // Toggle binding active/inactive
  const handleToggle = useCallback(
    async (binding: ChannelBinding) => {
      try {
        await toggleBinding(binding.id);
        toast.success(t('settings.channels.toggle_success'));
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t('common.error'));
      }
    },
    [toggleBinding, t]
  );

  // Unlink binding
  const handleUnlink = useCallback(async () => {
    if (!unlinkingBindingId) return;
    try {
      await unlinkBinding(unlinkingBindingId);
      toast.success(t('settings.channels.unlink_success'));
      setUnlinkingBindingId(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('common.error'));
    }
  }, [unlinkingBindingId, unlinkBinding, t]);

  // Format countdown display
  const formatCountdown = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <SettingsSection
      value="channels"
      title={t('settings.channels.title')}
      description={t('settings.channels.description')}
      icon={MessageCircle}
    >
      {/* Loading */}
      {loading && bindings.length === 0 && (
        <div className="flex justify-center py-8">
          <LoadingSpinner className="h-6 w-6" />
        </div>
      )}

      {/* No Telegram binding yet — show link button */}
      {!loading && !telegramBinding && (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <MessageCircle className="h-10 w-10 text-muted-foreground/50 mb-3" />
          <p className="text-sm text-muted-foreground mb-4">
            {telegramBotUsername
              ? t('settings.channels.empty_with_bot', { bot: telegramBotUsername })
              : t('settings.channels.empty')}
          </p>
          {telegramBotUsername && (
            <a
              href={`https://t.me/${telegramBotUsername}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-primary underline hover:no-underline mb-4"
            >
              @{telegramBotUsername}
            </a>
          )}
          <Button onClick={handleGenerateOtp} disabled={generatingOtp}>
            {generatingOtp && <LoadingSpinner className="mr-2 h-4 w-4" />}
            <Link2 className="h-4 w-4 mr-1" />
            {t('settings.channels.link_button')}
          </Button>
        </div>
      )}

      {/* Telegram binding exists — show status */}
      {telegramBinding && (
        <div className="rounded-lg border bg-card p-4 space-y-3">
          {/* Row 1: Telegram label + status badge + toggle */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <span className="font-medium">Telegram</span>
              <Badge variant={telegramBinding.is_active ? 'default' : 'secondary'}>
                {telegramBinding.is_active
                  ? t('settings.channels.status_active')
                  : t('settings.channels.status_inactive')}
              </Badge>
            </div>
            <Switch
              checked={telegramBinding.is_active}
              onCheckedChange={() => handleToggle(telegramBinding)}
              disabled={toggling}
              aria-label={t('settings.channels.toggle_label')}
            />
          </div>

          {/* Linked account info */}
          {telegramBinding.channel_username && (
            <p className="text-sm text-muted-foreground">
              {t('settings.channels.linked_as', {
                username: telegramBinding.channel_username,
              })}
            </p>
          )}

          {/* Linked date */}
          <p className="text-xs text-muted-foreground">
            {t('settings.channels.linked_since', {
              date: new Date(telegramBinding.created_at).toLocaleDateString(),
            })}
          </p>

          {/* Unlink button */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setUnlinkingBindingId(telegramBinding.id)}
            className="text-destructive hover:text-destructive"
          >
            <Unlink className="h-3 w-3 mr-1" />
            {t('settings.channels.unlink_button')}
          </Button>
        </div>
      )}

      {/* OTP Dialog */}
      <Dialog
        open={showOtpDialog}
        onOpenChange={(open) => {
          if (!open) {
            setShowOtpDialog(false);
            if (countdownRef.current) clearInterval(countdownRef.current);
          }
        }}
      >
        <DialogContent className="sm:max-w-[440px]">
          <DialogHeader>
            <DialogTitle>{t('settings.channels.otp_dialog_title')}</DialogTitle>
            <DialogDescription>
              {t('settings.channels.otp_dialog_instructions')}
            </DialogDescription>
          </DialogHeader>

          {otpData && (
            <div className="space-y-4 py-4">
              {/* Step 1: Open bot */}
              <div className="space-y-1">
                <p className="text-sm font-medium">
                  {t('settings.channels.otp_dialog_step1')}
                </p>
                {otpData.bot_username && (
                  <a
                    href={`https://t.me/${otpData.bot_username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-primary underline hover:no-underline"
                  >
                    @{otpData.bot_username}
                  </a>
                )}
              </div>

              {/* Step 2: Send code */}
              <div className="space-y-2">
                <p className="text-sm font-medium">
                  {t('settings.channels.otp_dialog_step2')}
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded bg-muted px-3 py-2 text-center text-2xl font-mono tracking-widest">
                    {otpData.code}
                  </code>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={handleCopyCommand}
                    title={t('common.copy')}
                  >
                    {copied ? (
                      <Check className="h-4 w-4 text-green-500" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>

              {/* Countdown */}
              <p className="text-xs text-muted-foreground text-center">
                {countdown > 0
                  ? t('settings.channels.otp_dialog_expires', {
                      time: formatCountdown(countdown),
                    })
                  : t('settings.channels.otp_dialog_expired')}
              </p>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowOtpDialog(false)}>
              {t('common.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Unlink Confirmation */}
      <AlertDialog
        open={unlinkingBindingId !== null}
        onOpenChange={(open) => !open && setUnlinkingBindingId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.channels.unlink_confirm_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.channels.unlink_confirm_description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleUnlink}
              disabled={unlinking}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {unlinking && <LoadingSpinner className="mr-2 h-4 w-4" />}
              {t('settings.channels.unlink_button')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsSection>
  );
}
