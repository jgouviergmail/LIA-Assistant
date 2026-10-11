import type { TFunction } from 'i18next';
import { HOME_PRODUCT_DEMO_KEY, type ProductSceneId } from './scenes';

/** Code-owned example data through the chat's production HTML vocabulary. */
function escapeText(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function productResultHtml(sceneId: ProductSceneId, t: TFunction): string {
  const k = (field: string) => escapeText(t(`${HOME_PRODUCT_DEMO_KEY}.scenes.${sceneId}.${field}`));
  const label = (field: string) => escapeText(t(`${HOME_PRODUCT_DEMO_KEY}.${field}`));
  const sources = [1, 2, 3].map(n => `<li>${k(`source_${n}`)}</li>`).join('');
  const note = `<p>${k('result_3')}</p>`;
  const draft = `<div class="lia-callout lia-callout-info">${note}</div>`;
  const details = `<details class="lia-collapsible"><summary>${label('card_details')}</summary><ul>${sources}</ul></details>`;
  const comparison = `<div class="lia-stats">${[1, 2]
    .map(
      n =>
        `<div class="lia-stat"><span class="lia-stat__value">${k(`result_${n}`)}</span><span class="lia-stat__label">${k(`evidence_${n}`)}</span></div>`
    )
    .join('')}</div>`;
  const document = `<div class="lia-callout lia-callout-info"><p class="lia-callout__title">${label('document_name')}</p><p>${label('document_format')}</p></div>`;
  const timeline = `<ol class="lia-steps">${[1, 2, 3].map(n => `<li>${k(`result_${n}`)}</li>`).join('')}</ol>`;
  const alert = `<div class="lia-callout lia-callout-warning"><p class="lia-callout__title">${k('result_1')}</p><p>${k('result_2')}</p></div>`;
  const relay = `<dl class="lia-kv"><dt>${k('evidence_1')}</dt><dd><strong>${k('result_1')}</strong></dd><dt>${k('evidence_2')}</dt><dd>${k('result_2')}</dd></dl>`;
  const minutes = `<dl class="lia-kv">${['meeting_decisions', 'meeting_actions', 'meeting_uncertainty'].map((field, i) => `<dt>${label(field)}</dt><dd>${k(`result_${i + 1}`)}</dd>`).join('')}</dl>`;
  const bodies: Record<ProductSceneId, string> = {
    decision: comparison + note + details,
    day: timeline,
    watch: alert + draft + details,
    call: note,
    research: document + minutes + details,
    relay: relay + draft + details,
  };
  return `<div class="lia-response">${bodies[sceneId]}</div>`;
}
