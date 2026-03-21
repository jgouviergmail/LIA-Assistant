'use client';

import { useState } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { apiClient } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import type { AdminUserUsageLimitResponse, UsageLimitUpdateRequest } from '@/types/usage-limits';

interface AdminUsageLimitsEditModalProps {
  user: AdminUserUsageLimitResponse;
  open: boolean;
  onClose: () => void;
  onSave: (updatedUser?: AdminUserUsageLimitResponse) => void;
}

/**
 * Modal for editing a user's usage limits.
 *
 * For each limit dimension (tokens, messages, cost):
 * - Toggle between unlimited and custom value
 * - Number input for custom value
 *
 * Also includes manual block toggle with reason textarea.
 */
export function AdminUsageLimitsEditModal({
  user,
  open,
  onClose,
  onSave,
}: AdminUsageLimitsEditModalProps) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);

  // Limit state
  const [tokenCycle, setTokenCycle] = useState<number | null>(user.token_limit_per_cycle);
  const [messageCycle, setMessageCycle] = useState<number | null>(user.message_limit_per_cycle);
  const [costCycle, setCostCycle] = useState<number | null>(user.cost_limit_per_cycle);
  const [tokenAbsolute, setTokenAbsolute] = useState<number | null>(user.token_limit_absolute);
  const [messageAbsolute, setMessageAbsolute] = useState<number | null>(
    user.message_limit_absolute
  );
  const [costAbsolute, setCostAbsolute] = useState<number | null>(user.cost_limit_absolute);

  // Block state
  const [blocked, setBlocked] = useState(user.is_usage_blocked);
  const [blockReason, setBlockReason] = useState(user.blocked_reason || '');

  const handleSave = async () => {
    setSaving(true);
    try {
      // Update limits
      const limitsPayload: UsageLimitUpdateRequest = {
        token_limit_per_cycle: tokenCycle,
        message_limit_per_cycle: messageCycle,
        cost_limit_per_cycle: costCycle,
        token_limit_absolute: tokenAbsolute,
        message_limit_absolute: messageAbsolute,
        cost_limit_absolute: costAbsolute,
      };

      let updatedUser = await apiClient.put<AdminUserUsageLimitResponse>(
        `/usage-limits/admin/users/${user.user_id}/limits`,
        limitsPayload
      );

      // Update block if changed
      if (blocked !== user.is_usage_blocked || blockReason !== (user.blocked_reason || '')) {
        updatedUser = await apiClient.put<AdminUserUsageLimitResponse>(
          `/usage-limits/admin/users/${user.user_id}/block`,
          {
            is_usage_blocked: blocked,
            blocked_reason: blocked ? blockReason || null : null,
          }
        );
      }

      onSave(updatedUser);
    } catch (err) {
      logger.error('Failed to update usage limits', err as Error, {
        component: 'AdminUsageLimitsEditModal',
        userId: user.user_id,
      });
      toast.error(t('usage_limits.edit.error'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={isOpen => !isOpen && onClose()}>
      <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('usage_limits.edit.title', { email: user.email })}</DialogTitle>
          <DialogDescription>{t('usage_limits.edit.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Per-Cycle Limits */}
          <div className="space-y-4">
            <h4 className="text-sm font-semibold">{t('usage_limits.edit.cycle_limits')}</h4>

            <LimitField
              label={t('usage_limits.edit.token_limit')}
              value={tokenCycle}
              onChange={setTokenCycle}
              currentUsage={user.cycle_tokens}
              t={t}
            />
            <LimitField
              label={t('usage_limits.edit.message_limit')}
              value={messageCycle}
              onChange={setMessageCycle}
              currentUsage={user.cycle_messages}
              t={t}
            />
            <LimitField
              label={t('usage_limits.edit.cost_limit')}
              value={costCycle}
              onChange={setCostCycle}
              currentUsage={user.cycle_cost}
              step={0.01}
              isCost
              t={t}
            />
          </div>

          {/* Global Limits */}
          <div className="space-y-4">
            <h4 className="text-sm font-semibold">{t('usage_limits.edit.absolute_limits')}</h4>

            <LimitField
              label={t('usage_limits.edit.token_limit')}
              value={tokenAbsolute}
              onChange={setTokenAbsolute}
              currentUsage={user.total_tokens}
              t={t}
            />
            <LimitField
              label={t('usage_limits.edit.message_limit')}
              value={messageAbsolute}
              onChange={setMessageAbsolute}
              currentUsage={user.total_messages}
              t={t}
            />
            <LimitField
              label={t('usage_limits.edit.cost_limit')}
              value={costAbsolute}
              onChange={setCostAbsolute}
              currentUsage={user.total_cost}
              step={0.01}
              isCost
              t={t}
            />
          </div>

          {/* Manual Block */}
          <div className="space-y-3 border-t pt-4">
            <h4 className="text-sm font-semibold">{t('usage_limits.edit.block_section')}</h4>
            <div className="flex items-center gap-3">
              <Switch checked={blocked} onCheckedChange={setBlocked} id="block-toggle" />
              <Label htmlFor="block-toggle" className="text-sm">
                {t('usage_limits.edit.block_user')}
              </Label>
            </div>
            {blocked && (
              <Textarea
                placeholder={t('usage_limits.edit.block_reason_placeholder')}
                value={blockReason}
                onChange={e => setBlockReason(e.target.value)}
                className="text-sm"
                rows={2}
              />
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            {t('usage_limits.edit.cancel')}
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? t('common.saving') : t('usage_limits.edit.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// Sub-component: single limit field with unlimited toggle
// ============================================================================

interface LimitFieldProps {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  currentUsage?: number;
  step?: number;
  isCost?: boolean;
  t: TFunction;
}

function LimitField({
  label,
  value,
  onChange,
  currentUsage,
  step = 1,
  isCost,
  t,
}: LimitFieldProps) {
  const isUnlimited = value === null;

  const formatUsage = (v: number | string) => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    if (isNaN(n)) return String(v);
    if (isCost) return `${n.toFixed(2)} €`;
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 100_000) return `${(n / 1_000).toFixed(0)}K`;
    return n.toLocaleString();
  };

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-3">
        <Label className="text-xs w-24 shrink-0">{label}</Label>
        <Switch checked={!isUnlimited} onCheckedChange={checked => onChange(checked ? 0 : null)} />
        {!isUnlimited && (
          <Input
            type="number"
            min={0}
            step={step}
            value={value}
            onChange={e => onChange(Number(e.target.value))}
            className="w-32 text-sm"
          />
        )}
        {isUnlimited && (
          <span className="text-xs text-muted-foreground">{t('usage_limits.unlimited')}</span>
        )}
      </div>
      {currentUsage !== undefined && (
        <div className="text-[10px] text-muted-foreground/70 ml-[6.5rem]">
          {t('usage_limits.edit.current_usage')}: {formatUsage(currentUsage)}
        </div>
      )}
    </div>
  );
}
