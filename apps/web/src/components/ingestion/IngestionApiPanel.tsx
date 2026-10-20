'use client';
import { useId, useState } from 'react';
import { Copy, Eye, EyeOff, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface IngestionEndpoint {
  id: string;
  label: string;
  url: string;
  hint?: string;
}
export interface IngestionPanelLabels {
  copy: string;
  close: string;
  show: string;
  hide: string;
  secret: string;
}
interface Props {
  endpoints: readonly IngestionEndpoint[];
  labels: IngestionPanelLabels;
  secret: string | null;
  onCopy: (value: string) => void;
  onClearSecret: () => void;
}
/** Presentation shared by every phone resource; issuance and consent stay source-owned. */
export function IngestionApiPanel({ endpoints, labels, secret, onCopy, onClearSecret }: Props) {
  const secretId = useId();
  const [show, setShow] = useState(false);
  return (
    <div className="min-w-0 space-y-4">
      {endpoints.map(endpoint => (
        <div key={endpoint.id} className="min-w-0 space-y-2">
          <Label htmlFor={endpoint.id}>{endpoint.label}</Label>
          <div className="flex min-w-0 gap-2">
            <Input
              id={endpoint.id}
              value={endpoint.url}
              readOnly
              className="min-w-0 font-mono text-xs"
              aria-describedby={endpoint.hint ? `${endpoint.id}-hint` : undefined}
            />
            <Button
              type="button"
              size="icon"
              variant="outline"
              className="shrink-0"
              aria-label={`${labels.copy} · ${endpoint.label}`}
              onClick={() => onCopy(endpoint.url)}
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
          {endpoint.hint && (
            <p id={`${endpoint.id}-hint`} className="break-words text-xs text-muted-foreground">
              {endpoint.hint}
            </p>
          )}
        </div>
      ))}
      {secret && (
        <div className="min-w-0 space-y-3 rounded-lg border border-warning/50 bg-warning/10 p-3">
          <Label htmlFor={secretId} className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            {labels.secret}
          </Label>
          <div className="flex min-w-0 flex-wrap gap-2">
            <div className="min-w-0 flex-1 basis-48">
              <Input
                id={secretId}
                type={show ? 'text' : 'password'}
                value={secret}
                readOnly
                autoComplete="off"
                spellCheck={false}
                className="min-w-0 font-mono text-xs"
              />
            </div>
            <Button
              type="button"
              size="icon"
              variant="outline"
              aria-label={show ? labels.hide : labels.show}
              onClick={() => setShow(value => !value)}
            >
              {show ? (
                <EyeOff className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Eye className="h-4 w-4" aria-hidden="true" />
              )}
            </Button>
            <Button
              type="button"
              size="icon"
              variant="outline"
              aria-label={`${labels.copy} · ${labels.secret}`}
              onClick={() => onCopy(secret)}
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
          <Button type="button" size="sm" variant="ghost" onClick={onClearSecret}>
            {labels.close}
          </Button>
        </div>
      )}
    </div>
  );
}
