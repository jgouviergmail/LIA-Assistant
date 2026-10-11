'use client';

import { useId, type Dispatch, type ReactNode, type SetStateAction } from 'react';
import type { TFunction } from 'i18next';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import type { MCPServerFormSource, MCPServerFormState } from '@/lib/mcp-server-form';
import { MCPAuthenticationFields } from './MCPAuthenticationFields';

interface Props {
  form: MCPServerFormState;
  setForm: Dispatch<SetStateAction<MCPServerFormState>>;
  editingServer: MCPServerFormSource | null;
  t: TFunction;
  descriptionAction?: ReactNode;
}

/** Original settings fields; credentials remain local to each browser form. */
export function MCPServerFormFields({ form, setForm, editingServer, t, descriptionAction }: Props) {
  const id = useId();
  return <div className="space-y-4">
          {/* Name */}
          <div className="space-y-3">
            <Label htmlFor={`${id}-mcp-name`}>{t('settings.mcp.field_name')}</Label>
            <Input
              id={`${id}-mcp-name`}
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder={t('settings.mcp.field_name_placeholder')}
              maxLength={100}
            />
          </div>

          {/* URL */}
          <div className="space-y-3">
            <Label htmlFor={`${id}-mcp-url`}>{t('settings.mcp.field_url')}</Label>
            <Input
              id={`${id}-mcp-url`}
              value={form.url}
              onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
              placeholder="https://mcp-server.example.com/mcp"
              type="url"
            />
          </div>

          {/* Domain Description */}
          <div className="space-y-3">
            <Label htmlFor={`${id}-mcp-domain-description`}>
              {t('settings.mcp.field_domain_description')}{' '}
              <span className="text-xs text-muted-foreground">({t('common.optional')})</span>
            </Label>
            <Textarea
              id={`${id}-mcp-domain-description`}
              value={form.domain_description}
              onChange={e => setForm(f => ({ ...f, domain_description: e.target.value }))}
              placeholder={t('settings.mcp.field_domain_description_placeholder')}
              maxLength={500}
              rows={2}
              className="resize-none"
            />
            <div className="flex items-center gap-2">
              <p className="text-xs text-muted-foreground flex-1">
                {t('settings.mcp.field_domain_description_help')}
              </p>
              {descriptionAction}
            </div>
          </div>

          <MCPAuthenticationFields id={id} form={form} setForm={setForm} editingServer={editingServer} t={t} />

          {/* Timeout */}
          <div className="space-y-3">
            <Label htmlFor={`${id}-mcp-timeout`}>{t('settings.mcp.field_timeout')}</Label>
            <Input
              id={`${id}-mcp-timeout`}
              value={form.timeout_seconds}
              onChange={e =>
                setForm(f => ({
                  ...f,
                  timeout_seconds: Math.max(5, Math.min(120, Number(e.target.value) || 30)),
                }))
              }
              type="number"
              min={5}
              max={120}
            />
          </div>

          {/* Iterative Mode (ADR-062) */}
          <div className="flex items-center justify-between py-2">
            <div className="space-y-0.5">
              <Label htmlFor={`${id}-mcp-iterative-mode`} className="text-sm font-medium">
                {t('settings.mcp.field_iterative_mode')}
              </Label>
              <p className="text-xs text-muted-foreground">
                {t('settings.mcp.field_iterative_mode_help')}
              </p>
            </div>
            <Switch
              id={`${id}-mcp-iterative-mode`}
              checked={form.iterative_mode}
              onCheckedChange={checked => setForm(f => ({ ...f, iterative_mode: checked }))}
            />
          </div>


  </div>;
}
