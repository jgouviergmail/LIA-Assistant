/**
 * Assistant answers as they are STORED — the inputs of the `.md` export.
 *
 * Captured 2026-09-30, never invented: the `lia-response` document is an
 * answer archived on the dev instance (`html` display mode), shortened to one
 * instance of each construct it uses; the directive components are the
 * canonical example of `html_response_directive.txt` plus the collapsible its
 * schema defines; the cards are the output of the backend's own components
 * (`apps/api/src/domains/agents/display/components/`, `RenderContext(language="fr")`)
 * on representative payloads, and the skill answer is an archived `cards`-mode
 * turn: the model's Markdown, then the widget sentinel the response node appends.
 */

/** An archived `lia-response` answer: headings, hard breaks, lists, a table, a quote, links. */
export const ARCHIVED_HTML_ANSWER = `<div class="lia-response">
<p>Ah, le monde merveilleux du développement web, où un framework devient "legacy" avant même que tu n'aies fini de configurer ton fichier <code>package.json</code>. Jetons un coup d'œil sur <strong>Next.js</strong>.</p>

<hr>

<h1>Synthèse des dernières actualités de Next.js</h1>

<h2>1. Versions récentes et cycle de publication</h2>

<p><strong>Next.js 15 (stable) — octobre 2024</strong><br>
Dernière version majeure stable confirmée à ma connaissance.</p>

<h3>Confirmées (Next.js 15.x)</h3>
<ul>
<li><strong>React 19 support natif</strong> : Actions serveur (<code>"use server"</code>), hooks comme <code>use()</code> pour les promesses.</li>
<li><strong><code>next/after</code></strong> : API pour exécuter du code après l'envoi de la réponse.</li>
</ul>

<h2>6. Tendances et direction stratégique</h2>

<table>
<thead>
<tr>
<th>Tendance</th>
<th>Direction observée</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Server-first</strong></td>
<td>Next.js pousse résolument vers le serveur (Server Components, Server Actions, PPR).</td>
</tr>
<tr>
<td><strong>Rust dans la toolchain</strong></td>
<td>Turbopack (Rust), SWC (Rust) pour la compilation.</td>
</tr>
</tbody>
</table>

<blockquote>
<p><strong>L'œil de LIA :</strong> En gros, Vercel continue de verrouiller l'écosystème React.</p>
</blockquote>

<ul>
<li>🔍 <a href="https://github.com/vercel/next.js/releases" target="_blank">Consulter directement les dernières releases sur GitHub</a> pour voir si la version 16 est sortie.</li>
<li>🛠️ Vérifier si tes projets utilisent encore le <em>Pages Router</em>.</li>
</ul>
</div>`;

/** The canonical example of `html_response_directive.txt`, plus the two components it only names. */
export const DIRECTIVE_COMPONENTS = `<div class="lia-response">
<p>The indexing pipeline upgrade completed with <strong>zero schema regressions</strong>.</p>
<h2>Outcome</h2>
<div class="lia-stats">
<div class="lia-stat"><span class="lia-stat__value">4.2 ms</span><span class="lia-stat__label">p99 latency</span></div>
<div class="lia-stat"><span class="lia-stat__value">1.8M</span><span class="lia-stat__label">records synced</span></div>
<div class="lia-stat"><span class="lia-stat__value">0</span><span class="lia-stat__label">regressions</span></div>
</div>
<h2>Primary instance</h2>
<dl class="lia-kv">
<dt>Status</dt><dd><span class="lia-chip lia-chip--green"><span class="material-symbols-outlined">check_circle</span>Active</span></dd>
<dt>Region</dt><dd><strong>eu-west-1</strong></dd>
</dl>
<h2>Promotion procedure</h2>
<ol class="lia-steps">
<li>Place the primary instance into read-only replication mode.</li>
<li>Promote the hot-standby replica to primary coordinator.</li>
</ol>
<pre><code class="language-python">if current_replicas &lt; target_replicas and health_status == "OK":
    scale_cluster(target_replicas)
</code></pre>
<details class="lia-collapsible"><summary>Rollback plan</summary><p>Re-point DNS to the <em>legacy</em> primary.</p></details>
<div class="lia-callout lia-callout-warning">
<p class="lia-callout__title">Connection drain latency</p>
<p>Allow at least <strong>30 seconds</strong> after DNS propagation before terminating legacy sockets.</p>
</div>
</div>`;

/** `EventCard` — a calendar event, its « see more » fold and its action buttons. */
export const EVENT_CARD = `<hr class="lia-response-separator"><div class="lia-response-wrapper"><div class="lia-card lia-event lia-event--pending "><div class="lia-card-top"><div class="lia-illus lia-illus--amber"><span class="material-symbols-outlined">pending</span></div><div class="lia-card-top__info"><a class="lia-card-top__title" href="https://calendar.google.com/x" target="_blank">Revue de sprint</a></div></div><div class="lia-chip-row"><span class="lia-chip lia-chip--indigo"><span class="material-symbols-outlined">calendar_month</span>lundi 28 septembre</span><span class="lia-chip lia-chip--time"><span class="material-symbols-outlined">schedule</span>12:00 - 13:00</span><span class="lia-chip"><span class="material-symbols-outlined">timer</span>1h</span></div><div style="margin-top:var(--lia-space-sm)"><div class="lia-d-row"><span class="material-symbols-outlined" style="font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 20;color:#ef4444">location_on</span><a href="https://www.google.com/maps/dir/?api=1&destination=Salle%20Turing%2C%2012%20rue%20de%20la%20Paix%2C%20Paris" target="_blank">Salle Turing, 12 rue de la Paix, Paris</a></div></div><div class="lia-att-row"><div class="lia-att-row__avatars"><div class="lia-att-av" style="background:linear-gradient(135deg, #c7d2fe, #a5b4fc);color:#3730a3">B</div></div><span class="lia-att-row__label">1 participant</span></div><div class="lia-collapsible-wrapper"><details class="lia-collapsible"><summary class="lia-collapsible__trigger"><span>Voir plus</span><span class="lia-collapsible__icon"><span class="lia-icon" aria-hidden="true"><span class="material-symbols-outlined">expand_more</span></span></span></summary><div class="lia-collapsible__content"><div class="lia-desc-block">Ordre du jour : démo, rétro</div><div class="lia-d-item"><span class="material-symbols-outlined">person</span><span>Organisé par <a href="mailto:alice@example.com">Alice</a><span style="color:var(--lia-text-muted);font-size:var(--lia-text-xs)"> alice@example.com</span></span></div><div class="lia-sec"><div class="lia-illus-sm lia-illus--indigo"><span class="material-symbols-outlined">group</span></div><span class="lia-sec__label">Participants</span></div><div class="lia-part-list"><div class="lia-part-item"><span class="material-symbols-outlined" style="color:#16a34a">check_circle</span><a href="mailto:bob@example.com">Bob</a><span class="lia-part-item__email">bob@example.com</span></div></div></div></details></div></div><div class="lia-suggested-actions"><a href="https://calendar.google.com/x" class="lia-action-btn lia-action-btn--events" target="_blank" rel="noopener"><span class="lia-action-btn__icon" aria-hidden="true"><span class="material-symbols-outlined">calendar_month</span></span>Voir</a><a href="https://www.google.com/maps/dir/?api=1&amp;destination=Salle%20Turing%2C%2012%20rue%20de%20la%20Paix%2C%20Paris" class="lia-action-btn lia-action-btn--events" target="_blank" rel="noopener"><span class="lia-action-btn__icon" aria-hidden="true"><span class="material-symbols-outlined">directions</span></span>Itinéraire</a></div></div><hr class="lia-response-separator">`;

/** `ContactCard` — a title with an EMPTY href, and typed detail rows. */
export const CONTACT_CARD = `<hr class="lia-response-separator"><div class="lia-response-wrapper"><div class="lia-card lia-contact "><div class="lia-card-top"><div class="lia-illus lia-illus--indigo"><span style="font-size:var(--lia-text-base);font-weight:600">MC</span></div><div class="lia-card-top__info"><a class="lia-card-top__title" href="" target="_blank">Marie Curie</a><div class=lia-card-top__subtitle><span class="lia-icon lia-icon--xs" aria-hidden="true"><span class="material-symbols-outlined">work</span></span> Institut Radium · Directrice</div></div></div><div class="lia-d-row"><span class="material-symbols-outlined">mail</span><a href="mailto:marie@example.com">marie@example.com</a><span class="lia-tbadge lia-tbadge--work">Travail</span></div><div class="lia-d-row"><span class="material-symbols-outlined">phone</span><a href="tel:+33123456789">01.23.45.67.89</a><span class="lia-tbadge lia-tbadge--mobile">Mobile</span></div><div class="lia-d-row"><span class="material-symbols-outlined" style="font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 20;color:#ef4444">location_on</span><a href="https://www.google.com/maps/dir/?api=1&amp;destination=11%20rue%20Pierre%20et%20Marie%20Curie%2C%20Paris" target="_blank">11 rue Pierre et Marie Curie, Paris</a></div></div><div class="lia-suggested-actions"><a href="mailto:marie@example.com" class="lia-action-btn lia-action-btn--contacts" target="_blank" rel="noopener"><span class="lia-action-btn__icon" aria-hidden="true"><span class="material-symbols-outlined">mail</span></span>Email</a><a href="tel:+33123456789" class="lia-action-btn lia-action-btn--contacts" target="_blank" rel="noopener"><span class="lia-action-btn__icon" aria-hidden="true"><span class="material-symbols-outlined">phone</span></span>Appeler</a></div></div><hr class="lia-response-separator">`;

/** `EmailCard` — buttons (not links) as actions, an attachment behind a fold. */
export const EMAIL_CARD = `<hr class="lia-response-separator"><div class="lia-response-wrapper"><div class="lia-card lia-email lia-email--unread  "><div class="lia-card-top"><div class="lia-illus lia-illus--green"><span style="font-size:var(--lia-text-sm);font-weight:600;letter-spacing:-0.02em">C</span></div><div class="lia-card-top__info"><div class="lia-card-top__subtitle" style="margin-bottom:var(--lia-space-2xs)">dimanche à 10:00 <div class="lia-email__status-icons"><span class="lia-email__status-icon lia-email__status-icon--unread" title="Non lu"><span class="lia-icon lia-icon--sm" aria-hidden="true"><span class="material-symbols-outlined">mark_email_unread</span></span></span></div></div><a class="lia-card-top__title" style="font-size:var(--lia-text-base);font-weight:400" href="mailto:compta@example.com">Compta</a><div style="font-size:var(--lia-text-xs);color:var(--lia-text-muted)">compta@example.com</div></div></div><div class="lia-chip-row"><span class="lia-chip lia-chip--attach"><span class="material-symbols-outlined">attach_file</span>1</span></div><a href="https://mail.google.com/mail/u/0/#all/m1" class="lia-email__subject" target="_blank" rel="noopener" style="font-weight:700">Facture septembre</a><p class="lia-email__snippet">Veuillez trouver ci-joint la facture</p><div class="lia-collapsible-wrapper"><hr class="lia-separator lia-separator--collapsible" /><details class="lia-collapsible"><summary class="lia-collapsible__trigger"><span>Voir 1 pièce jointe</span><span class="lia-collapsible__icon"><span class="lia-icon" aria-hidden="true"><span class="material-symbols-outlined">expand_more</span></span></span></summary><div class="lia-collapsible__content"><div class="lia-attachments"><span class="lia-attachment lia-attachment--pdf" ><span class="lia-attachment__icon" aria-hidden="true"><span class="material-symbols-outlined">picture_as_pdf</span></span><span class="lia-attachment__name" title="facture.pdf">facture.pdf</span><span class="lia-attachment__size">(12.1KB)</span></span></div></div></details></div></div><div class="lia-suggested-actions"><button type="button" class="lia-action-btn lia-action-btn--email" data-action="reply"><span class="lia-action-btn__icon" aria-hidden="true"><span class="material-symbols-outlined">reply</span></span>Rép.</button><button type="button" class="lia-action-btn lia-action-btn--email" data-action="forward"><span class="lia-action-btn__icon" aria-hidden="true"><span class="material-symbols-outlined">forward</span></span>Transf.</button><button type="button" class="lia-action-btn lia-action-btn--email" data-action="archive"><span class="lia-action-btn__icon" aria-hidden="true"><span class="material-symbols-outlined">archive</span></span>Supp.</button></div></div><hr class="lia-response-separator">`;

/** `WeatherCard` (current) — the city is the title, drawn AFTER the temperature. */
export const WEATHER_CARD = `<hr class="lia-response-separator"><div class="lia-response-wrapper"><div class="lia-card lia-weather lia-weather--sunny "><div class="lia-weather__layout"><div class="lia-weather__left"><span class="lia-weather__icon"><span class="lia-icon" aria-hidden="true"><span class="material-symbols-outlined">light_mode</span></span></span><span class="lia-weather__temp">12°C</span><div class="lia-weather__desc">clear</div></div><div class="lia-weather__right"><div class="lia-weather__date">Aujourd&#x27;hui</div><div class="lia-weather__city">Paris</div></div></div><div class="lia-weather__stats"><div class="lia-weather__stat"><span class="lia-weather__stat-icon"><span class="lia-icon" aria-hidden="true"><span class="material-symbols-outlined">thermostat</span></span></span><span class="lia-weather__stat-label">Ressenti</span><span class="lia-weather__stat-value">10°C</span></div><div class="lia-weather__stat"><span class="lia-weather__stat-icon"><span class="lia-icon" aria-hidden="true"><span class="material-symbols-outlined">water_drop</span></span></span><span class="lia-weather__stat-label">Humidité</span><span class="lia-weather__stat-value">45%</span></div></div></div><div class="lia-suggested-actions"><a href="https://www.google.com/search?q=weather+Paris" class="lia-action-btn lia-action-btn--weathers" target="_blank" rel="noopener"><span class="lia-action-btn__icon" aria-hidden="true"><span class="material-symbols-outlined">date_range</span></span>Prévisions</a></div></div><hr class="lia-response-separator">`;

/** `RouteCard` — labelled endpoints and numbered steps. */
export const ROUTE_CARD = `<hr class="lia-response-separator"><div class="lia-response-wrapper"><div class="lia-card lia-route "><div class="lia-card-top"><div class="lia-illus lia-illus--amber"><span class="material-symbols-outlined">directions_car</span></div><div class="lia-card-top__info"><span class="lia-card-top__title">→ Gare de Lyon</span></div></div><div class="lia-chip-row"><span class="lia-chip lia-chip--amber"><span class="material-symbols-outlined">traffic</span>Modéré</span><span class="lia-chip lia-chip--green"><span class="material-symbols-outlined">timer</span>18 min</span><span class="lia-chip"><span class="material-symbols-outlined">straighten</span>4.2 km</span></div><div class="lia-route__endpoints"><div class="lia-route__endpoint"><span class="lia-route__endpoint-icon"><span class="lia-icon lia-icon--sm lia-icon--route" aria-hidden="true"><span class="material-symbols-outlined">flag</span></span></span><div class="lia-route__endpoint-content"><span class="lia-route__endpoint-label">Départ</span><span class="lia-route__endpoint-value">Bastille</span></div></div><div class="lia-route__endpoint"><span class="lia-route__endpoint-icon"><span class="lia-icon lia-icon--sm lia-icon--route" aria-hidden="true"><span class="material-symbols-outlined">sports_score</span></span></span><div class="lia-route__endpoint-content"><span class="lia-route__endpoint-label">Arrivée</span><span class="lia-route__endpoint-value">Gare de Lyon</span></div></div></div><div class="lia-collapsible-wrapper"><hr class="lia-separator lia-separator--collapsible" /><details class="lia-collapsible"><summary class="lia-collapsible__trigger"><span>Étapes (1)</span><span class="lia-collapsible__icon"><span class="lia-icon" aria-hidden="true"><span class="material-symbols-outlined">expand_more</span></span></span></summary><div class="lia-collapsible__content"><div class="lia-route__steps"><div class="lia-route__step"><span class="lia-route__step-number">1</span><span class="lia-route__step-instruction">Prendre la rue de Lyon</span></div></div></div></details></div></div><div class="lia-suggested-actions"><a href="https://www.google.com/maps/dir/?api=1&amp;destination=Gare%20de%20Lyon&amp;travelmode=driving&amp;origin=Bastille" class="lia-action-btn lia-action-btn--route" target="_blank" rel="noopener"><span class="lia-action-btn__icon" aria-hidden="true"><span class="material-symbols-outlined">map</span></span>Ouvrir dans Maps</a></div></div><hr class="lia-response-separator">`;

/** A Markdown hard break: two trailing spaces, spelled out so no editor trims them. */
const HARD_BREAK = '  ';

/** An archived `cards`-mode turn: the model's Markdown, then a skill widget sentinel. */
export const MARKDOWN_WITH_SKILL_WIDGET = `Voici le résultat — le sous-agent scripté a généré ce haïku :

> **Mock et stub dansent**${HARD_BREAK}
> **Sur la scène du test blanc**

Le skill **haiku-tests** est maintenant actif dans **Réglages > Compétences LIA > Mes skills**.

<div class="lia-skill-app" data-registry-id="skill_app_c9a86e"><div class="lia-skill-app__placeholder"><span class="lia-badge lia-badge--accent"><span class="lia-icon" aria-hidden="true"><span class="material-symbols-outlined">psychology</span></span> haiku-tests</span><div class="lia-skill-app__loading">Chargement du skill…</div></div></div>`;
