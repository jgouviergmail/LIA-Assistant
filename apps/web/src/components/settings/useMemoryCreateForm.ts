'use client';
/** Native memory creation, including reviewable AI proposals, owns no embedding before Save. */
import { useRef, useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useHandoff } from '@/hooks/useHandoff';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';
import type { Memory, MemoryCreate, MemoryLimits } from '@/hooks/useMemories';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { isMemoryTextSavable, isRefusedInput } from '@/lib/memories/text-bounds';
import { EMPTY_MEMORY_FORM, type MemoryFormData } from './MemoryFormFields';

export function useMemoryCreateForm(
  lng: Language,
  create: (body: MemoryCreate) => Promise<Memory | undefined>,
  loading: boolean,
  busy: boolean,
  limits: MemoryLimits | undefined
) {
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const toast = useApplicationAccountToast(user?.id);
  const { t } = useTranslation(lng);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<MemoryFormData>(EMPTY_MEMORY_FORM);
  const [saving, setSaving] = useState(false);
  const inFlight = useRef(false);
  useHandoff(
    'memory',
    !loading,
    handed => {
      setForm({ ...EMPTY_MEMORY_FORM, ...handed.memory });
      setOpen(true);
    },
    open || busy
  );
  const close = () => {
    if (!inFlight.current) {
      setOpen(false);
      setForm(EMPTY_MEMORY_FORM);
    }
  };
  const start = () => {
    if (!inFlight.current) {
      setForm(EMPTY_MEMORY_FORM);
      setOpen(true);
    }
  };
  const save = async () => {
    if (inFlight.current || !isCurrent() || !isMemoryTextSavable(form, limits)) return;
    inFlight.current = true;
    setSaving(true);
    try {
      const saved = await create({
        ...form,
        usage_nuance: form.usage_nuance || undefined,
        trigger_topic: form.trigger_topic || undefined,
      });
      if (!isCurrent()) return;
      if (!saved) throw new Error('Memory creation returned no result');
      toast.success(t('memories.create_success'));
      setOpen(false);
      setForm(EMPTY_MEMORY_FORM);
    } catch (error) {
      toast.error(t(isRefusedInput(error) ? 'memories.text_refused' : 'memories.create_error'));
    } finally {
      inFlight.current = false;
      if (isCurrent()) setSaving(false);
    }
  };
  return {
    open,
    form,
    setForm,
    start,
    close,
    save,
    saving,
    onOpenChange: (next: boolean) => {
      if (!next) close();
    },
  };
}
