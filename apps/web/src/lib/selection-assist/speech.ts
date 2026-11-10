/** The existing speech door: exact selected words, cancellable and validated at receipt. */
import apiClient from '@/lib/api-client';
import { z } from '@/lib/zod';
import { ASSIST_TIMEOUT_MS } from '@/lib/workbench/assist';

const answer = z.object({
  audio: z
    .string()
    .min(1)
    .regex(/^[A-Za-z0-9+/]+={0,2}$/),
  cut: z.boolean(),
  cost_eur: z.number().nonnegative(),
  usage: z.null(),
});
export type SelectionSpeech = z.infer<typeof answer>;

export async function requestReadAloud(
  path: string,
  body: object,
  signal: AbortSignal
): Promise<SelectionSpeech> {
  return answer.parse(
    await apiClient.post<unknown>(path, body, { signal, timeout: ASSIST_TIMEOUT_MS })
  );
}
