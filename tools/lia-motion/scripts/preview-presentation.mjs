import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {PRESENTATION_REVISION} from '../src/presentation-plan.ts';

const project=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=path.resolve(project,'../../exports/lia-motion');
const music=JSON.parse(await readFile(path.resolve(project,'src/music-film.json'),'utf8'));
const main=JSON.parse(await readFile(path.resolve(output,'main-delivery.json'),'utf8'));
const focus=JSON.parse(await readFile(path.resolve(output,'focus-delivery.json'),'utf8').catch(error=>{if(error.code==='ENOENT')return '{"generation":"pending","records":[]}';throw error;}));
if(main.generation!==PRESENTATION_REVISION)throw new Error('Current main delivery is required; previous revisions cannot enter the player');
const titles={
  full:'Film complet',landing:'Coupe landing',
  'focus-conversation':'Les bonnes informations','focus-avatars':'Compagnons et personnalité',
  'focus-memory':'Mémoire','focus-relations':'Relations','focus-peers':'Assistants connectés',
  'focus-radio':'Briefing et Radio','focus-routines':'Rappels et routines','focus-proactive':'Proactivité',
  'focus-habits':'Habitudes','focus-workboard':'Délégation et suivi','focus-voice':'Voix et Live',
  'focus-phone':'Appels','focus-meetings':'Réunions','focus-knowledge':'Connaissances',
  'focus-creation':'Créations','focus-extensions':'Skills, plugins et MCP',
  'focus-connected-services':'Services connectés','focus-health':'Mesures santé',
  'focus-journals':'Journaux','focus-control':'Accord et coûts','focus-mobile':'Mobile et canaux',
  'focus-admin':'Administration','focus-speaking-avatar':'Simli — expérimental',
  'focus-display':'Modes d’affichage','focus-notifications':'Rappels et notifications',
  'focus-planning':'Planning des actions','focus-registry':'Registre des actions',
  'focus-llm-config':'Configuration des LLM','focus-platform':'Santé de la plateforme',
};
const records=[...main.records].sort((a,b)=>a.name==='full'?-1:b.name==='full'?1:0).concat(focus.generation===PRESENTATION_REVISION?focus.records:[]);
const media=records.map(record=>({name:record.name,title:titles[record.name]??record.name,source:record.descriptor.renditions[0].src,poster:record.descriptor.poster,duration:record.descriptor.durationSeconds}));
const html=`<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LIA — présentation</title><style>
*{box-sizing:border-box}body{margin:0;color:#1b2140;background:radial-gradient(50rem 34rem at 12% -6%,#4f8dfd33,transparent 62%),radial-gradient(44rem 30rem at 88% 22%,#8b5cf62b,transparent 64%),radial-gradient(40rem 28rem at 30% 105%,#38d4f51f,transparent 60%),#e9ecf6;background-attachment:fixed;font:16px/1.5 system-ui,sans-serif}
main{max-width:1460px;margin:auto;padding:28px 32px 44px}header{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}header strong{font-size:28px;letter-spacing:-1px}header span{font-size:14px;color:#414868}h1{margin:0 0 12px;font-size:clamp(26px,4vw,38px);letter-spacing:-1.3px;line-height:1.2}.intro{margin:0 0 21px;max-width:1000px;color:#414868;font-size:15px}
video{display:block;width:100%;aspect-ratio:16/9;background:#e9ecf6;border-radius:18px;box-shadow:0 20px 50px #1b214015}.media-choice{margin-top:24px;display:flex;gap:8px;flex-wrap:wrap}button{font:inherit;font-size:13px;border:1px solid #2c56c427;border-radius:9px;background:#ffffff75;color:#1b2140;padding:9px 13px;cursor:pointer}button[aria-pressed=true]{background:#2c56c4;color:white;border-color:#2c56c4}button:focus-visible,a:focus-visible{outline:3px solid #2c56c4;outline-offset:3px}footer{font-size:12px;line-height:1.8;color:#414868;margin-top:25px}a{color:#2c56c4}.duration{font-variant-numeric:tabular-nums;margin-left:8px;opacity:.7} @media(max-width:600px){main{padding:18px 13px}header span{font-size:12px}button{font-size:12px;padding:8px 10px}}
</style></head><body><main><header><strong>LIA</strong><span>Film de présentation et focus · musique seule</span></header><h1>Une journée avec LIA.</h1><p class="intro">Découvre les usages de LIA, ses avatars animés et les actions que tu peux préparer et valider. Les scènes reprennent ses interfaces avec des données de démonstration.</p>
<video controls playsinline preload="metadata" poster="${media[0].poster}" aria-label="Film complet de présentation LIA"><source src="${media[0].source}" type="video/mp4"></video>
<nav class="media-choice" aria-label="Choisir un montage">${media.map((item,index)=>`<button type="button" data-index="${index}" aria-pressed="${index===0}">${item.title}<span class="duration">${Math.round(item.duration)} s</span></button>`).join('')}</nav>
<footer>${music.attribution}. <a href="${music.source}">Source</a> · <a href="${music.licenseUrl}">Licence</a>.<br>Sources éditables et scénario conservés dans tools/lia-motion. Les focus précisent les options et capacités expérimentales. Qualification technique TV à adapter aux spécifications du diffuseur.</footer>
</main><script>const media=${JSON.stringify(media).replaceAll('<','\\u003c')};const video=document.querySelector('video');document.querySelectorAll('[data-index]').forEach(button=>button.addEventListener('click',()=>{const item=media[Number(button.dataset.index)];video.pause();video.src=item.source;video.poster=item.poster;video.setAttribute('aria-label',item.title+' de présentation LIA');video.load();document.querySelectorAll('[data-index]').forEach(candidate=>candidate.setAttribute('aria-pressed',String(candidate===button)));}));</script></body></html>`;
for(const name of ['presentation-review.html','index.html','story24-review.html','proof-review.html'])await writeFile(path.resolve(output,name),html);
console.log(`Current film player: ${media.length} delivered ${PRESENTATION_REVISION.toUpperCase()} edits`);
