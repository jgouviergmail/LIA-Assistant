/**
 * Authored French motion screenplay. Beats retain the declared product scope;
 * the build checks that scope against the landing's REQUIRED_FEATURE_KEYS.
 * Native footage and exercised actions are qualified separately in capture-v2.
 *
 * Screenshots and clips show the real UI with fictional fixture data. Provenance
 * is public/capture-v2/manifest.json. Voiceover is an editable
 * editorial script, not a claim that a voice track has been recorded.
 */

export const FPS = 30;
export const DEMONSTRATION_NOTE = 'Démonstration scénarisée · données fictives';

export const FEATURE_LABELS = {
  natural_language: 'Langage naturel',
  multi_agent: 'Agents spécialisés',
  rich_responses: 'Réponses enrichies',
  chat_sync: 'Conversation synchronisée',
  email_share: 'Partage par e-mail',
  generated_files: 'Galerie des créations',
  multichannel: 'Web, Telegram et push',
  languages: 'Interface en six langues',
  memory: 'Mémoire contextuelle',
  bookmarks: 'Réponses conservées',
  personal_crm: 'Relations',
  peers: 'Assistants connectés',
  peer_shares: 'Partages révocables',
  peer_safety: 'Protection du cercle',
  personalities: 'Personnalités',
  psyche: 'Psyche',
  mood_face: 'Compagnons animés',
  self_knowledge: 'Connaissance de ses capacités',
  journals: 'Journaux personnels',
  briefing: 'Briefing quotidien',
  personal_radio: 'Radio personnelle',
  proactive: 'Suggestions proactives',
  proactive_wake: 'Réaction aux événements',
  proactive_moments: 'Moments de suivi',
  interests: 'Centres d’intérêt',
  habits: 'Habitudes observées',
  habits_lifecycle: 'Évolution des habitudes',
  reminders_scheduling: 'Rappels et routines',
  conditional_routines: 'Routines conditionnelles',
  workboard: 'Tableau de travail',
  workboard_delegation: 'Tickets confiés à LIA',
  telephony: 'Appels pour toi',
  telephony_callback: 'Appels vers toi',
  live_voice: 'Conversation Live',
  meetings: 'Réunions et comptes rendus',
  meeting_templates: 'Modèles de compte rendu',
  skills: 'Skills',
  health_metrics: 'Mesures santé',
  excalidraw: 'Schémas Excalidraw',
  image_generation: 'Création d’images',
  document_generation: 'Création de documents',
  attachments: 'Photos et pièces jointes',
  mcp_apps: 'MCP Apps',
  plugins: 'Plugins',
  mcp: 'Serveurs MCP',
  rag_spaces: 'Espaces de connaissances',
  mail_label_spaces: 'Espaces par libellé Gmail',
  sub_agents: 'Sous-agents',
  browser_control: 'Navigation assistée',
  computed_answers: 'Calculs par outils',
  devops_cli: 'DevOps pour l’administrateur',
  control: 'Confirmations et traces',
  usage_limits: 'Coûts et quotas',
  privacy: 'Données et accès',
  native_apps: 'Apps Android et iOS',
  responsive: 'Ordinateur et mobile',
  simplicity: 'Réglages accessibles',
  themes: 'Thèmes et apparence',
  connected_services: 'Google, iCloud et Microsoft 365',
  environment: 'Météo, air et pollens',
  smart_home: 'Maison Philips Hue',
  web_intelligence: 'Recherche, lieux et itinéraires',
  voice_mode: 'Transcription et voix',
} as const;

export type FeatureKey = keyof typeof FEATURE_LABELS;
export type SceneKind =
  | 'intro'
  | 'dossier'
  | 'avatars'
  | 'memory'
  | 'radio'
  | 'routine'
  | 'voice'
  | 'meeting'
  | 'creation'
  | 'ecosystem'
  | 'peers'
  | 'control'
  | 'connections'
  | 'relations'
  | 'workboard'
  | 'knowledge'
  | 'health'
  | 'journal'
  | 'habits';

export interface MotionCard {
  label: string;
  title: string;
  detail?: string;
  meta?: string;
  icon?: string;
}

export interface MotionBeat {
  title: string;
  detail: string;
  featureKeys: readonly FeatureKey[];
}

export interface MotionScene {
  id: string;
  kind: SceneKind;
  title: string;
  subtitle: string;
  eyebrow: string;
  accent: `#${string}`;
  durationSeconds: number;
  featureKeys: readonly FeatureKey[];
  cards: readonly MotionCard[];
  beats: readonly MotionBeat[];
  chips?: readonly string[];
  prompt?: string;
  response?: string;
  screenshot?: string;
  footnote?: string;
  status?: 'experimental' | 'planned';
  voiceover: string;
  /** Repository sources checked while authoring; for production handoff. */
  evidence: readonly string[];
}

const featureKeysFromBeats = (beats: readonly MotionBeat[]): readonly FeatureKey[] =>
  beats.flatMap(beat => [...beat.featureKeys]);

/** Declared editorial scope; not a claim of filmed provider execution. */
const scene = (content: Omit<MotionScene, 'featureKeys'>): MotionScene => ({
  ...content,
  featureKeys: featureKeysFromBeats(content.beats),
});

export const FULL_SCENES: readonly MotionScene[] = [
  scene({
    id: 'your-day',
    kind: 'intro',
    durationSeconds: 9,
    accent: '#8b7cff',
    eyebrow: 'LIA · L’intelligence à tes côtés',
    title: 'Ta journée. Ton assistant.',
    subtitle: 'Une conversation qui relie ce qui compte pour toi.',
    prompt: 'LIA, prépare ma journée et mon rendez-vous avec Camille.',
    response: 'Je rassemble ton agenda, tes messages et le contexte du dossier.',
    cards: [
      {
        label: 'Conversation',
        title: 'Préparer le rendez-vous',
        detail: 'Une demande, les bons outils.',
        icon: 'chat',
      },
      {
        label: 'En déplacement',
        title: 'Le fil te suit',
        detail: 'Ordinateur, tablette, téléphone.',
        icon: 'mobile',
      },
      {
        label: 'À ton image',
        title: 'Les réglages à portée',
        detail: 'Langue, capacités, sections favorites.',
        icon: 'settings',
      },
    ],
    beats: [
      {
        title: 'Tu demandes, LIA organise',
        detail: 'En langage naturel, dans un fil qui se synchronise.',
        featureKeys: ['natural_language', 'chat_sync'],
      },
      {
        title: 'À portée, partout',
        detail: 'Une interface adaptée au mobile et des réglages recherchables.',
        featureKeys: ['responsive', 'simplicity'],
      },
      {
        title: 'Dans ta langue',
        detail: 'Français, anglais, allemand, espagnol, italien, chinois.',
        featureKeys: ['languages'],
      },
    ],
    voiceover:
      'Ta journée commence par une demande. LIA rassemble ce qui compte, dans une conversation qui te suit, sur ordinateur comme sur téléphone.',
    evidence: [
      'apps/web/src/components/landing/editorial/chapters-data.ts',
      'apps/web/locales/fr/translation.json',
    ],
  }),
  scene({
    id: 'connected-dossier',
    kind: 'dossier',
    durationSeconds: 14,
    accent: '#65d4f5',
    eyebrow: '01 · Rapprocher les informations',
    title: 'Le contexte devient utile.',
    subtitle: 'Messages, agenda, documents et sources publiques se rencontrent.',
    prompt: 'Prépare le dossier : nos échanges, le devis et le trajet.',
    response: 'Le rendez-vous est à 10 h. Voici les points ouverts, le devis et le trajet.',
    screenshot: '/screenshots/proof/dossier.png',
    cards: [
      {
        label: 'Tes services',
        title: 'Mail + agenda + contacts',
        detail: 'Google, iCloud ou Microsoft 365.',
        icon: 'mail',
      },
      {
        label: 'Le dossier',
        title: 'Devis et pièce jointe',
        detail: 'Résumé, calculs et page du fournisseur.',
        icon: 'document',
      },
      {
        label: 'La sortie',
        title: 'Trajet et météo',
        detail: 'Informations sourcées, carte dépliable.',
        icon: 'map',
      },
    ],
    beats: [
      {
        title: 'Les bons spécialistes',
        detail: 'Tes services connectés alimentent un dossier commun.',
        featureKeys: ['multi_agent', 'connected_services'],
      },
      {
        title: 'Lire, comparer, calculer',
        detail: 'Pièces jointes, outils de calcul et navigation visible.',
        featureKeys: ['attachments', 'computed_answers', 'browser_control'],
      },
      {
        title: 'Préparer la sortie',
        detail: 'Recherche, lieux, trajet, météo, air et pollens disponibles.',
        featureKeys: ['web_intelligence', 'environment', 'rich_responses'],
      },
      {
        title: 'Puis préparer la maison',
        detail: '« Tamise le salon » devient une commande Philips Hue.',
        featureKeys: ['smart_home'],
      },
    ],
    footnote: 'Services et données selon les accès et la configuration de l’instance.',
    voiceover:
      'Ses spécialistes rapprochent tes messages, ton agenda et tes documents. Elle consulte des sources publiques, calcule avec ses outils et prépare ton trajet. La maison connectée rejoint aussi la conversation.',
    evidence: ['README.md', 'apps/web/locales/fr/translation.json'],
  }),
  scene({
    id: 'living-companions',
    kind: 'avatars',
    durationSeconds: 13,
    accent: '#ffa9cb',
    eyebrow: '02 · Une présence expressive',
    title: 'Un compagnon qui s’anime.',
    subtitle: 'Le regard, l’expression et le mouvement suivent l’échange.',
    cards: [
      {
        label: 'Présence',
        title: 'À l’écoute',
        detail: 'Un regard et des mouvements discrets.',
        icon: 'avatar',
      },
      {
        label: 'Travail',
        title: 'Recherche en cours',
        detail: 'L’expression suit l’activité réelle.',
        icon: 'sparkle',
      },
      {
        label: 'Personnalité',
        title: 'Le ton qui te correspond',
        detail: 'Ami, professeur, coach…',
        icon: 'heart',
      },
    ],
    beats: [
      {
        title: 'Plusieurs compagnons animés',
        detail: 'Regards, mimiques et mouvements accompagnent l’activité.',
        featureKeys: ['mood_face'],
      },
      {
        title: 'Une personnalité choisie',
        detail: 'Le ton et l’humour s’adaptent à l’échange.',
        featureKeys: ['personalities', 'psyche'],
      },
      {
        title: 'Une apparence à toi',
        detail: 'Compagnons, thèmes, polices et tailles se personnalisent.',
        featureKeys: ['themes'],
      },
    ],
    chips: ['À l’écoute', 'En réflexion', 'En train de parler'],
    footnote: 'Expression et émotions simulées · animation réduite disponible.',
    voiceover:
      'LIA a aussi une présence. Ses compagnons animés suivent l’échange et le travail en cours. Tu choisis son apparence et sa personnalité ; son expression accompagne le ton de la conversation.',
    evidence: [
      'apps/web/src/components/eyes/eye-styles.ts',
      'apps/web/src/components/eyes/ExpressiveEyes.tsx',
      'README.md',
    ],
  }),
  scene({
    id: 'remember-people',
    kind: 'memory',
    durationSeconds: 12,
    accent: '#c4a0ff',
    eyebrow: '03 · Retrouver le fil',
    title: 'Ce qui compte se retrouve.',
    subtitle: 'Préférences, réponses conservées et relations gardent leur contexte.',
    prompt: 'Quels points restent ouverts avec Camille ?',
    response: 'Le devis révisé et la date de livraison. Tu préfères valider par écrit.',
    screenshot: '/screenshots/proof/memory.png',
    cards: [
      {
        label: 'Mémoire',
        title: 'Valider par écrit',
        detail: 'Consigne épinglée · modifiable.',
        icon: 'pin',
      },
      {
        label: 'Relations',
        title: 'Camille · dossier Atlas',
        detail: 'Échanges, appels et points ouverts.',
        icon: 'people',
      },
      {
        label: 'Réponses conservées',
        title: 'Le comparatif du dossier',
        detail: 'Retrouvable après le reset du chat.',
        icon: 'bookmark',
      },
    ],
    beats: [
      {
        title: 'Tes repères durables',
        detail: 'Préférences modifiables et réponses conservées.',
        featureKeys: ['memory', 'bookmarks'],
      },
      {
        title: 'Les personnes et le contexte',
        detail: 'Relations rassemble les échanges et les points ouverts.',
        featureKeys: ['personal_crm'],
      },
      {
        title: 'Des apprentissages consultables',
        detail: 'Ses journaux se corrigent ; LIA explique aussi ses capacités.',
        featureKeys: ['journals', 'self_knowledge'],
      },
    ],
    voiceover:
      'Les préférences que tu gardes, les réponses conservées et les échanges avec tes proches retrouvent leur contexte. Tu peux consulter et corriger ses apprentissages, ou lui demander ce qu’elle sait faire.',
    evidence: ['README.md', 'apps/web/locales/fr/translation.json'],
  }),
  scene({
    id: 'personal-radio',
    kind: 'radio',
    durationSeconds: 13,
    accent: '#fbbf78',
    eyebrow: '04 · Ta journée à lire et à écouter',
    title: 'Une Radio sur ta journée.',
    subtitle: 'Ton programme personnel rencontre les nouvelles que tu choisis.',
    screenshot: '/screenshots/proof/radio.png',
    cards: [
      {
        label: 'Briefing',
        title: 'Ta journée en vue',
        detail: 'Agenda, tâches et mesures santé.',
        icon: 'sunrise',
      },
      {
        label: 'À l’antenne',
        title: 'Ton journal du matin',
        detail: 'Voix, actualités et fond musical.',
        icon: 'radio',
      },
      {
        label: 'À côté du lecteur',
        title: 'Sources et transcription',
        detail: 'Programme, durée et coût visibles.',
        icon: 'document',
      },
    ],
    beats: [
      {
        title: 'Le briefing te prépare',
        detail: 'Tes sources du jour et tes mesures santé réunies.',
        featureKeys: ['briefing', 'health_metrics'],
      },
      {
        title: 'Ta station, à la demande',
        detail: 'Sujets, sources, voix, minuteur et budget se choisissent.',
        featureKeys: ['personal_radio'],
      },
    ],
    voiceover:
      'Le briefing te donne une vue de ta journée. Ta Radio mêle ensuite ce programme personnel aux nouvelles que tu choisis, avec les sources, la transcription et le coût près du lecteur.',
    evidence: ['docs/technical/RADIO.md', 'README.md', 'apps/web/locales/fr/translation.json'],
  }),
  scene({
    id: 'right-moment',
    kind: 'routine',
    durationSeconds: 14,
    accent: '#8ee5b2',
    eyebrow: '05 · Entre deux conversations',
    title: 'Au moment que tu choisis.',
    subtitle: 'Rappels, conditions et propositions suivent tes réglages.',
    prompt: 'Quand Camille répond, prépare un résumé du devis et préviens-moi.',
    response: 'La routine attend son message. Tu pourras relire le résultat.',
    cards: [
      {
        label: 'Routine',
        title: 'Attendre la réponse de Camille',
        detail: 'Condition : un mail de cet expéditeur.',
        icon: 'workflow',
      },
      {
        label: 'Moment',
        title: 'Après le rendez-vous',
        detail: 'Un suivi dans ta plage autorisée.',
        icon: 'clock',
      },
      {
        label: 'Rythme',
        title: 'Ton suivi d’habitudes',
        detail: 'Observations, progression et pauses.',
        icon: 'repeat',
      },
    ],
    beats: [
      {
        title: 'Une heure ou une condition',
        detail: 'Rappels et routines attendent le moment ou l’événement choisi.',
        featureKeys: ['reminders_scheduling', 'conditional_routines'],
      },
      {
        title: 'Quand une information arrive',
        detail: 'Mail ou agenda peuvent déclencher une proposition pertinente.',
        featureKeys: ['proactive', 'proactive_wake'],
      },
      {
        title: 'Un suivi qui te ressemble',
        detail: 'Moments après réunion et sujets que tu as choisis.',
        featureKeys: ['proactive_moments', 'interests'],
      },
      {
        title: 'Un rythme visible',
        detail: 'Habitudes observées, séries et évolution se consultent et se mettent en pause.',
        featureKeys: ['habits', 'habits_lifecycle'],
      },
    ],
    footnote: 'Sources, horaires et pauses configurables · habitudes sur activation.',
    voiceover:
      'Tu règles les horaires, les sources et les pauses. Une routine peut attendre un message ou une condition. LIA propose un suivi au bon moment et rend visibles les habitudes qu’elle observe.',
    evidence: ['README.md', 'apps/web/locales/fr/translation.json'],
  }),
  scene({
    id: 'delegated-work',
    kind: 'workboard',
    durationSeconds: 11,
    accent: '#81d5dd',
    eyebrow: '06 · Une demande devient un travail suivi',
    title: 'Confie-lui le dossier.',
    subtitle: 'Un ticket garde son porteur, ses échanges et son résultat.',
    prompt: 'Prends ce ticket : comparer les devis du dossier Atlas.',
    response: 'Je prends le ticket. Voici le comparatif à valider.',
    cards: [
      {
        label: 'À faire',
        title: 'Comparer les devis',
        detail: 'Porteur : LIA · échéance visible.',
        icon: 'kanban',
      },
      {
        label: 'En cours',
        title: 'Pièces réunies',
        detail: 'Recherche et commentaires au même endroit.',
        icon: 'document',
      },
      {
        label: 'À valider',
        title: 'Comparatif livré',
        detail: 'Une décision attend ton commentaire.',
        icon: 'check',
      },
    ],
    beats: [
      {
        title: 'Une responsabilité visible',
        detail: 'Le tableau suit le porteur, l’échéance et l’histoire du ticket.',
        featureKeys: ['workboard'],
      },
      {
        title: 'LIA travaille, tu valides',
        detail: 'Elle rend un résultat ou te demande la décision qui manque.',
        featureKeys: ['workboard_delegation'],
      },
    ],
    voiceover:
      'Confie un ticket à LIA. Son tableau garde le travail en cours, les échanges et le résultat. Une décision manque ? Elle la demande sur le ticket, et ton commentaire lui répond.',
    evidence: ['docs/technical/WORKBOARD.md', 'README.md'],
  }),
  scene({
    id: 'voice-and-phone',
    kind: 'voice',
    durationSeconds: 13,
    accent: '#a5bcff',
    eyebrow: '07 · Du texte à la conversation',
    title: 'Parle. Garde le fil.',
    subtitle: 'Voix, Live et téléphone prolongent la même assistance.',
    prompt: 'Appelle Camille pour vérifier la date de livraison.',
    response: 'Voici le destinataire et la demande à confirmer avant l’appel.',
    cards: [
      {
        label: 'Live',
        title: 'Une conversation en direct',
        detail: 'Parler, interrompre, lire les sous-titres.',
        icon: 'wave',
      },
      {
        label: 'Téléphone',
        title: 'LIA appelle pour toi',
        detail: 'Demande validée, puis résumé dans le chat.',
        icon: 'phone',
      },
      {
        label: 'Tes canaux',
        title: 'Le même fil, à portée',
        detail: 'Web, Telegram, apps Android et iOS.',
        icon: 'mobile',
      },
    ],
    beats: [
      {
        title: 'La voix et le Live',
        detail: 'Transcription, voix configurable et dialogue interrompable.',
        featureKeys: ['voice_mode', 'live_voice'],
      },
      {
        title: 'Les appels deviennent du contexte',
        detail: 'LIA peut appeler un tiers après validation, ou ton numéro vérifié.',
        featureKeys: ['telephony', 'telephony_callback'],
      },
      {
        title: 'Sur les canaux que tu utilises',
        detail: 'Telegram, push et apps natives reliées à ton serveur.',
        featureKeys: ['multichannel', 'native_apps'],
      },
    ],
    footnote: 'Live sur ta clé fournisseur · mode direct en lecture seule.',
    voiceover:
      'Parle avec LIA en Live, interrompt-la, ou demande-lui de passer un appel après validation. Elle peut aussi t’appeler sur ton numéro vérifié. Le contexte revient dans la conversation.',
    evidence: ['README.md', 'docs/technical/LIVE_MODE.md', 'apps/web/locales/fr/translation.json'],
  }),
  scene({
    id: 'meeting-to-results',
    kind: 'creation',
    durationSeconds: 13,
    accent: '#f3a6a1',
    eyebrow: '08 · Du rendez-vous aux livrables',
    title: 'Ce qui s’est dit prend forme.',
    subtitle: 'Compte rendu, documents, images et schémas restent à portée.',
    prompt: 'Rédige le compte rendu, le comparatif et un schéma du projet.',
    response: 'Les décisions, les actions et les livrables sont prêts à relire.',
    screenshot: '/screenshots/proof/meetings.png',
    cards: [
      {
        label: 'Réunion',
        title: 'Décisions et actions',
        detail: 'Transcription + modèle de compte rendu.',
        icon: 'mic',
      },
      {
        label: 'Livrables',
        title: 'Document · image · schéma',
        detail: 'PDF, Word, tableur et Excalidraw.',
        icon: 'document',
      },
      {
        label: 'Galerie',
        title: 'Garder et partager',
        detail: 'Téléchargement, rétention et envoi par e-mail.',
        icon: 'folder',
      },
    ],
    beats: [
      {
        title: 'Capturer puis structurer',
        detail: 'La réunion devient un compte rendu dans le modèle choisi.',
        featureKeys: ['meetings', 'meeting_templates'],
      },
      {
        title: 'Produire les bons supports',
        detail: 'Documents, images et schémas dans la conversation.',
        featureKeys: ['document_generation', 'image_generation', 'excalidraw'],
      },
      {
        title: 'Conserver le résultat',
        detail: 'Galerie, durée de vie visible et partage par e-mail.',
        featureKeys: ['generated_files', 'email_share'],
      },
    ],
    voiceover:
      'La réunion devient un compte rendu, puis des livrables : documents, images ou schémas. Tu les relis dans le chat, les gardes dans ta galerie et les partages quand ils sont prêts.',
    evidence: ['docs/technical/MEETINGS.md', 'README.md', 'apps/web/locales/fr/translation.json'],
  }),
  scene({
    id: 'knowledge-and-tools',
    kind: 'ecosystem',
    durationSeconds: 14,
    accent: '#b6a2ff',
    eyebrow: '09 · Ses capacités grandissent avec tes besoins',
    title: 'Ton savoir. Tes outils.',
    subtitle: 'Espaces de connaissances et extensions rejoignent la conversation.',
    prompt: 'Retrouve la décision du dossier, puis lance le tableau de suivi.',
    response: 'La décision est citée depuis ton espace. Le tableau peut s’ouvrir ici.',
    screenshot: '/screenshots/proof/knowledge.png',
    cards: [
      {
        label: 'Connaissances',
        title: 'Documents et fils choisis',
        detail: 'Espaces, dossiers Drive, libellé Gmail.',
        icon: 'library',
      },
      {
        label: 'Extensions',
        title: 'Skills + plugins + MCP',
        detail: 'Des outils choisis pour ton besoin.',
        icon: 'blocks',
      },
      {
        label: 'Dans le chat',
        title: 'Mini-apps et spécialistes',
        detail: 'Widgets interactifs et sous-agents.',
        icon: 'app',
      },
    ],
    beats: [
      {
        title: 'Retrouver une décision avec sa source',
        detail: 'Documents et fils sous un libellé Gmail alimentent tes espaces.',
        featureKeys: ['rag_spaces', 'mail_label_spaces'],
      },
      {
        title: 'Ajouter une compétence',
        detail: 'Skills, plugins et serveurs MCP étendent les capacités disponibles.',
        featureKeys: ['skills', 'plugins', 'mcp'],
      },
      {
        title: 'Ouvrir et approfondir',
        detail: 'MCP Apps dans le chat et sous-agents aux recherches complémentaires.',
        featureKeys: ['mcp_apps', 'sub_agents'],
      },
    ],
    footnote:
      'Extensions et interfaces selon le serveur, les accès et les capacités prises en charge.',
    voiceover:
      'Tes espaces rendent les documents et les fils choisis interrogeables, avec leurs sources. Skills, plugins et serveurs MCP apportent d’autres outils, des interfaces dans le chat et des recherches confiées à des sous-agents.',
    evidence: ['README.md', 'apps/web/locales/fr/translation.json'],
  }),
  scene({
    id: 'assistant-circle',
    kind: 'peers',
    durationSeconds: 11,
    accent: '#f4c78b',
    eyebrow: '10 · Ton cercle',
    title: 'Vos assistants se relaient.',
    subtitle: 'Des échanges et des disponibilités partagés selon vos choix.',
    prompt: 'Camille est-elle disponible jeudi ? Transmets-lui le comparatif.',
    response: 'Je consulte les disponibilités qu’elle partage. Voici le message à confirmer.',
    screenshot: '/screenshots/proof/relations.png',
    cards: [
      {
        label: 'Ton assistant',
        title: 'Le message à confirmer',
        detail: 'Le comparatif et la formulation.',
        icon: 'avatar',
      },
      {
        label: 'Son assistant',
        title: 'Le relais à Camille',
        detail: 'Une réponse dans son propre chat.',
        icon: 'people',
      },
      {
        label: 'Les accès',
        title: 'Libre / occupé',
        detail: 'Lecture seule, révocable à tout moment.',
        icon: 'shield',
      },
    ],
    beats: [
      {
        title: 'Un relais entre assistants',
        detail: 'Le message confirmé arrive dans le chat du proche connecté.',
        featureKeys: ['peers'],
      },
      {
        title: 'Ouvrir juste les informations choisies',
        detail: 'Disponibilités et autres champs en lecture seule, révocables.',
        featureKeys: ['peer_shares'],
      },
      {
        title: 'Un cercle volontaire',
        detail: 'Découverte activée par choix et blocage silencieux.',
        featureKeys: ['peer_safety'],
      },
    ],
    footnote: 'Connexions entre personnes de la même instance LIA.',
    voiceover:
      'Sur la même instance, les assistants de ton cercle se relaient. Tu confirmes les messages et choisis les informations partagées en lecture seule. Chaque accès reste révocable.',
    evidence: ['README.md', 'apps/web/locales/fr/translation.json'],
  }),
  scene({
    id: 'your-control',
    kind: 'control',
    durationSeconds: 13,
    accent: '#89d0bc',
    eyebrow: '11 · Du choix à la maîtrise',
    title: 'Tu gardes la décision.',
    subtitle: 'Actions à confirmer, coûts visibles et données administrables.',
    prompt: 'Envoie le comparatif à Camille.',
    response: 'Relis le destinataire, le message et la pièce jointe, puis confirme.',
    screenshot: '/screenshots/proof/approval.png',
    cards: [
      {
        label: 'Avant d’agir',
        title: 'Relire · confirmer',
        detail: 'Destinataire et contenu visibles.',
        icon: 'check',
      },
      {
        label: 'Après la réponse',
        title: 'Voir le coût et les étapes',
        detail: 'Quotas, budgets et registres.',
        icon: 'gauge',
      },
      {
        label: 'Ton instance',
        title: 'Ton serveur, tes réglages',
        detail: 'Fournisseurs et diagnostic administrateur.',
        icon: 'server',
      },
    ],
    beats: [
      {
        title: 'Une décision lisible',
        detail: 'Les actions sensibles attendent leur confirmation.',
        featureKeys: ['control'],
      },
      {
        title: 'Une dépense visible',
        detail: 'Les comptes et l’instance ont leurs plafonds ; les coûts se consultent.',
        featureKeys: ['usage_limits'],
      },
      {
        title: 'Un cadre que tu peux examiner',
        detail: 'Données exportables, fournisseurs configurés et diagnostic réservé à l’admin.',
        featureKeys: ['privacy', 'devops_cli'],
      },
    ],
    chips: ['Conversations', 'Capacités', 'Contexte', 'Contrôle'],
    footnote:
      'Le contexte utile va aux fournisseurs configurés ; l’opérateur peut accéder aux données stockées.',
    voiceover:
      'Avant une action sensible, tu relis et tu confirmes. Les coûts, les plafonds et les traces se consultent. Ton instance garde ses réglages, ses fournisseurs et ses outils d’administration. LIA, à tes côtés.',
    evidence: ['README.md', 'apps/web/locales/fr/translation.json'],
  }),
];

const SHORT_EDITS = [
  { durationSeconds: 6, voiceover: 'Une demande. Ton contexte. LIA rassemble ce qui compte.' },
  {
    durationSeconds: 7,
    voiceover: 'Messages, agenda, documents, recherche : les bons outils se coordonnent.',
  },
  {
    durationSeconds: 7,
    voiceover: 'Un compagnon animé, une présence expressive, une personnalité que tu choisis.',
  },
  { durationSeconds: 6, voiceover: 'Mémoire, réponses conservées et Relations gardent le fil.' },
  { durationSeconds: 6, voiceover: 'Ta journée se prépare en briefing et s’écoute en Radio.' },
  {
    durationSeconds: 7,
    voiceover: 'Rappels, routines et propositions suivent les conditions que tu règles.',
  },
  { durationSeconds: 5, voiceover: 'Confie un ticket. LIA rend un résultat à valider.' },
  { durationSeconds: 6, voiceover: 'Parle en Live, au téléphone, ou retrouve tes canaux.' },
  { durationSeconds: 6, voiceover: 'Réunions, documents, images et schémas prennent forme.' },
  {
    durationSeconds: 7,
    voiceover: 'Tes connaissances et tes extensions rejoignent la conversation.',
  },
  { durationSeconds: 5, voiceover: 'Les assistants de ton cercle se relaient avec ton accord.' },
  {
    durationSeconds: 7,
    voiceover: 'Tu confirmes les actions et suis les coûts. LIA, à tes côtés.',
  },
] as const;

/** One demonstration per short scene gives its result time to remain visible. */
const SHORT_REPRESENTATIVE_FEATURES: Readonly<Record<string, FeatureKey>> = {
  'your-day': 'natural_language',
  'connected-dossier': 'multi_agent',
  'living-companions': 'mood_face',
  'remember-people': 'memory',
  'personal-radio': 'personal_radio',
  'right-moment': 'conditional_routines',
  'delegated-work': 'workboard_delegation',
  'voice-and-phone': 'live_voice',
  'meeting-to-results': 'meetings',
  'knowledge-and-tools': 'skills',
  'assistant-circle': 'peers',
  'your-control': 'control',
};

/** The short edit introduces chapters; the full film and focuses carry detail. */
export const SHORT_SCENES: readonly MotionScene[] = FULL_SCENES.map((content, index) => {
  const representative = content.beats.find(beat =>
    beat.featureKeys.includes(SHORT_REPRESENTATIVE_FEATURES[content.id])
  );
  if (!representative) throw new Error(`Missing short-film beat for scene: ${content.id}`);
  return scene({
    ...content,
    ...SHORT_EDITS[index],
    beats: [representative],
  });
});

const focus = (
  baseId: string,
  edits: Partial<MotionScene> & Pick<MotionScene, 'id' | 'durationSeconds'>
): MotionScene => {
  const base = FULL_SCENES.find(content => content.id === baseId);
  if (!base) throw new Error(`Unknown motion scene: ${baseId}`);
  const result = { ...base, ...edits };
  return { ...result, featureKeys: featureKeysFromBeats(result.beats) };
};

/** Independently usable films deepen the differentiating workflows. */
export const FOCUS_SCENES: readonly MotionScene[] = [
  focus('living-companions', {
    id: 'focus-avatars',
    durationSeconds: 20,
    eyebrow: 'Focus · Les compagnons animés',
    voiceover:
      'Choisis le compagnon qui te ressemble. Son regard suit l’échange, son expression accompagne les recherches et sa bouche suit l’audio entendu. La personnalité et Psyche modulent le ton. Tu règles l’apparence et peux réduire les animations.',
  }),
  focus('remember-people', {
    id: 'focus-relations',
    kind: 'relations',
    durationSeconds: 20,
    eyebrow: 'Focus · Mémoire et Relations',
    screenshot: '/screenshots/proof/relations.png',
    voiceover:
      'Avant de retrouver Camille, demande à LIA où vous en êtes. Relations rassemble vos échanges et les points ouverts. Les préférences gardées et les journaux apportent le contexte ; une réponse conservée retrouve ses sources. Tu peux corriger ce que LIA apprend.',
  }),
  focus('personal-radio', {
    id: 'focus-radio',
    durationSeconds: 22,
    eyebrow: 'Focus · Une Radio personnelle',
    voiceover:
      'Lance ta station pour une durée choisie. Ta journée et les nouvelles de tes sources entrent dans le programme. Tu choisis les sujets, les voix et les vérifications. La musique accompagne la parole ; la transcription, les articles et le coût restent visibles.',
  }),
  focus('right-moment', {
    id: 'focus-routines',
    durationSeconds: 22,
    eyebrow: 'Focus · Le bon moment',
    voiceover:
      'Quand Camille répond, une routine peut préparer le résumé que tu as demandé. Une autre suit un horaire. Les propositions respectent tes sources, tes plages et tes pauses. Les moments de suivi et les habitudes observées se règlent, se consultent et se mettent en pause.',
  }),
  focus('delegated-work', {
    id: 'focus-workboard',
    durationSeconds: 20,
    eyebrow: 'Focus · Confier un travail à LIA',
    voiceover:
      'Le dossier a un porteur et une échéance. Confie le ticket à LIA : elle cherche, commente et remet un résultat. Si une décision lui manque, elle te la demande sur le ticket. Ton commentaire lui répond et l’histoire du travail reste lisible.',
  }),
  focus('meeting-to-results', {
    id: 'focus-meetings',
    kind: 'meeting',
    durationSeconds: 22,
    eyebrow: 'Focus · Réunions et comptes rendus',
    title: 'La réunion devient une référence.',
    subtitle: 'Enregistrer, structurer, reformater et retrouver les décisions.',
    beats: [
      {
        title: 'Enregistrer sur ton appareil',
        detail: 'La capture continue pendant que tu utilises LIA.',
        featureKeys: ['meetings'],
      },
      {
        title: 'Choisir la bonne structure',
        detail: 'Modèles intégrés ou personnels ; reformatage depuis la transcription.',
        featureKeys: ['meeting_templates'],
      },
      {
        title: 'Retrouver la décision plus tard',
        detail: 'Le compte rendu rejoint son espace de connaissances.',
        featureKeys: ['rag_spaces'],
      },
    ],
    voiceover:
      'Ton appareil enregistre la réunion pendant que tu continues à utiliser LIA. La transcription devient un compte rendu dans le modèle adapté, ou celui que tu choisis. Tu peux le reformater puis retrouver ses décisions, avec leur contexte, dans ton espace de connaissances.',
  }),
  focus('knowledge-and-tools', {
    id: 'focus-knowledge',
    kind: 'knowledge',
    durationSeconds: 20,
    eyebrow: 'Focus · Des réponses depuis tes documents',
    title: 'Retrouver la source, garder le contexte.',
    subtitle: 'Documents, dossiers Drive et fils Gmail que tu choisis.',
    beats: [
      {
        title: 'Choisir ce qui entre',
        detail: 'Importer tes fichiers ou synchroniser un dossier Drive.',
        featureKeys: ['rag_spaces'],
      },
      {
        title: 'Suivre un libellé Gmail',
        detail: 'Seuls les fils désignés deviennent des documents interrogeables.',
        featureKeys: ['mail_label_spaces'],
      },
      {
        title: 'Conserver un résultat utile',
        detail: 'Une réponse gardée peut être citée quand elle concerne la question.',
        featureKeys: ['bookmarks'],
      },
    ],
    voiceover:
      'Une décision prise il y a des semaines se retrouve depuis tes documents. Choisis les fichiers, un dossier Drive ou un libellé Gmail. LIA interroge ces espaces et cite ce qu’elle a lu. Tu peux suspendre une source ou retirer un espace.',
  }),
  focus('knowledge-and-tools', {
    id: 'focus-extensions',
    kind: 'ecosystem',
    durationSeconds: 22,
    eyebrow: 'Focus · Skills, plugins et MCP',
    screenshot: '/screenshots/proof/skill.png',
    title: 'Des capacités pour ton usage.',
    subtitle: 'De la compétence sur mesure à la mini-application dans le chat.',
    beats: [
      {
        title: 'Une compétence installée après lecture',
        detail: 'Génération d’un skill, bibliothèque ou plugin compatible.',
        featureKeys: ['skills', 'plugins'],
      },
      {
        title: 'Tes outils rejoignent LIA',
        detail: 'Serveurs MCP et widgets MCP Apps selon leurs capacités.',
        featureKeys: ['mcp', 'mcp_apps'],
      },
      {
        title: 'Approfondir avec plusieurs angles',
        detail: 'Sous-agents bornés, outils autorisés et budgets propres.',
        featureKeys: ['sub_agents'],
      },
    ],
    voiceover:
      'Décris une compétence à LIA, puis relis le skill proposé avant de l’installer. Un plugin peut réunir plusieurs capacités. Les serveurs MCP ajoutent des outils et parfois des interfaces interactives. Pour approfondir, des sous-agents travaillent sur plusieurs angles dans leurs budgets.',
  }),
  focus('connected-dossier', {
    id: 'focus-connected-services',
    kind: 'connections',
    durationSeconds: 22,
    eyebrow: 'Focus · Tes services connectés',
    title: 'Ton quotidien, relié.',
    subtitle: 'Des comptes choisis et des services utiles à ta demande.',
    beats: [
      {
        title: 'Relier tes comptes',
        detail: 'Google, Apple iCloud, Microsoft 365 ; un fournisseur par famille.',
        featureKeys: ['connected_services'],
      },
      {
        title: 'Rapprocher l’intérieur et l’extérieur',
        detail: 'Recherche, lieux, trajets, météo, air et pollens disponibles.',
        featureKeys: ['web_intelligence', 'environment'],
      },
      {
        title: 'Agir sur la maison',
        detail: 'Lumières, pièces et ambiances Philips Hue.',
        featureKeys: ['smart_home'],
      },
    ],
    voiceover:
      'Relie les services que tu choisis : mails, agenda, contacts et tâches, selon le fournisseur de chaque famille. Ajoute les sources publiques, les trajets et la météo disponibles. Même les lumières Philips Hue se règlent depuis la conversation.',
  }),
  focus('assistant-circle', {
    id: 'focus-peers',
    durationSeconds: 20,
    eyebrow: 'Focus · Ton cercle d’assistants',
    voiceover:
      'Une connexion volontaire relie deux personnes de la même instance. Après ta confirmation, ton assistant transmet le message au sien. Les disponibilités partagées se consultent en lecture seule. Tu choisis les champs ouverts et peux révoquer l’accès ou bloquer une connexion.',
  }),
  focus('voice-and-phone', {
    id: 'focus-voice',
    status: 'planned',
    durationSeconds: 18,
    eyebrow: 'Focus · Voix, Live et appels',
    title: 'La voix, au-delà du chat.',
    subtitle: 'Des modes vocaux et des appels avec un objectif et un débrief.',
    beats: [
      {
        title: 'Choisir ton mode vocal',
        detail: 'Voix et Live : réglages natifs, sans session fournisseur dans ce montage.',
        featureKeys: ['voice_mode', 'live_voice'],
      },
      {
        title: 'Définir puis suivre un appel',
        detail: 'Objectif et débrief illustrés par un appel de démonstration.',
        featureKeys: ['telephony', 'telephony_callback'],
      },
    ],
    voiceover:
      'Choisis ton mode vocal ou le Live. La téléphonie permet de confier un objectif à LIA et de retrouver le débrief de l’appel. Les réglages définissent le mode et les contrôles de ton numéro.',
    footnote: 'Réglages et données de démonstration · aucun appel ou Live fournisseur exercé.',
    evidence: [
      'apps/web/src/components/settings/VoiceModeSettings.tsx',
      'apps/web/src/components/settings/LiveModeSettings.tsx',
      'apps/web/src/components/settings/TelephonyCallsSection.tsx',
      'apps/web/src/components/settings/TelephonyIdentitySection.tsx',
    ],
  }),
  focus('meeting-to-results', {
    id: 'focus-creation',
    status: 'planned',
    kind: 'creation',
    durationSeconds: 18,
    eyebrow: 'Focus · Images, documents et schémas',
    title: 'Du résultat au fichier.',
    subtitle: 'Retrouver les créations et choisir les options de génération.',
    beats: [
      {
        title: 'Retrouver tes fichiers',
        detail: 'La galerie native montre des métadonnées de démonstration.',
        featureKeys: ['generated_files', 'document_generation'],
      },
      {
        title: 'Choisir les options d’image',
        detail: 'Les réglages natifs définissent la qualité et le format.',
        featureKeys: ['image_generation'],
      },
      {
        title: 'Composer un schéma',
        detail: 'Capacité Excalidraw présentée par un carton éditorial, sans résultat inventé.',
        featureKeys: ['excalidraw'],
      },
    ],
    voiceover:
      'LIA peut préparer des images, des documents et des schémas. Retrouve les fichiers dans leur galerie et choisis les options d’image. Cette démonstration montre leur interface et leurs réglages.',
    footnote: 'Interface native et données de démonstration · aucune génération fournisseur exercée.',
    evidence: [
      'apps/web/src/components/settings/GeneratedAssetsSettings.tsx',
      'apps/web/src/components/settings/ImageGenerationSettings.tsx',
      'apps/web/src/components/chat/GeneratedDocumentPreview.tsx',
      'apps/web/src/components/landing/editorial/chapters-data.ts',
    ],
  }),
  focus('right-moment', {
    id: 'focus-proactive',
    status: 'planned',
    durationSeconds: 18,
    eyebrow: 'Focus · Proactivité choisie',
    title: 'Un suivi aux bons moments.',
    subtitle: 'Routines, sources et horaires que tu peux régler.',
    beats: [
      {
        title: 'Définir une routine',
        detail: 'Consulter une routine et ses conditions dans l’interface native.',
        featureKeys: ['reminders_scheduling', 'conditional_routines'],
      },
      {
        title: 'Choisir les propositions',
        detail: 'Sources, plages horaires et moments de suivi accessibles dans les réglages.',
        featureKeys: ['proactive', 'proactive_wake', 'proactive_moments'],
      },
      {
        title: 'Suivre les habitudes choisies',
        detail: 'Apprentissage volontaire et contrôles de pause.',
        featureKeys: ['habits', 'habits_lifecycle'],
      },
    ],
    voiceover:
      'Définis les routines utiles et les sources de tes propositions. Choisis leurs horaires et les moments de suivi. Les habitudes peuvent être observées si tu actives cet apprentissage, puis mises en pause.',
    footnote: 'Réglages et données de démonstration · aucun suivi automatique déclenché.',
    evidence: [
      'apps/web/src/components/settings/HeartbeatSettings.tsx',
      'apps/web/src/components/settings/HeartbeatSourceSwitches.tsx',
      'apps/web/src/components/settings/HabitsSettings.tsx',
      'apps/web/src/hooks/useScheduledActions.ts',
    ],
  }),
  scene({
    id: 'focus-health',
    kind: 'health',
    durationSeconds: 20,
    accent: '#8ee5b2',
    eyebrow: 'Focus · Tes mesures santé',
    title: 'Tes mesures, dans leur contexte.',
    subtitle: 'Les pas et la fréquence cardiaque se consultent par période.',
    prompt: 'Montre mon activité sur la semaine.',
    response: 'Voici les mesures reçues. Les périodes sans données restent visibles.',
    cards: [
      {
        label: 'Ta source',
        title: 'Des mesures que tu envoies',
        detail: 'Montre, raccourci ou script · jeton révocable.',
        icon: 'activity',
      },
      {
        label: 'La période',
        title: 'Pas et fréquence cardiaque',
        detail: 'Jour, semaine ou mois · trous préservés.',
        icon: 'chart',
      },
      {
        label: 'Le briefing',
        title: 'Une ligne santé dans ta journée',
        detail: 'Une vue descriptive des mesures disponibles.',
        icon: 'sunrise',
      },
    ],
    beats: [
      {
        title: 'Une source que tu choisis',
        detail: 'Tu envoies tes pas et ta fréquence cardiaque avec un jeton révocable.',
        featureKeys: ['health_metrics'],
      },
      {
        title: 'Une période que tu peux examiner',
        detail:
          'Les courbes gardent les périodes sans mesure ; le briefing reprend les données disponibles.',
        featureKeys: ['health_metrics'],
      },
    ],
    footnote: 'Vue descriptive des mesures transmises par tes sources.',
    voiceover:
      'Envoie tes pas et ta fréquence cardiaque depuis la source que tu choisis, avec un jeton révocable. LIA affiche ces mesures par période et préserve les trous de données. Une ligne santé peut aussi rejoindre ton briefing.',
    evidence: [
      'apps/web/src/hooks/useHealthMetrics.ts',
      'apps/web/src/components/settings/HealthMetricsSettings.tsx',
      'apps/web/locales/fr/translation.json',
    ],
  }),
  scene({
    id: 'focus-journals',
    kind: 'journal',
    durationSeconds: 20,
    accent: '#c4a0ff',
    eyebrow: 'Focus · Les journaux personnels',
    title: 'Ses observations se corrigent.',
    subtitle: 'Ce que LIA apprend garde son thème, sa source et son degré de confiance.',
    prompt: 'Ce déplacement est une exception. Je préfère le train en général.',
    response: 'Tu peux corriger l’observation ; son contexte reste consultable.',
    cards: [
      {
        label: 'Observation',
        title: 'Privilégie le train',
        detail: 'Source : conversation · confiance visible.',
        icon: 'book',
      },
      {
        label: 'Correction',
        title: 'Signaler une exception',
        detail: 'Modifier une entrée ou signaler une erreur.',
        icon: 'edit',
      },
      {
        label: 'Portrait',
        title: 'Retrouver ses appuis',
        detail: 'Souvenirs, habitudes, intérêts et débriefs.',
        icon: 'people',
      },
    ],
    beats: [
      {
        title: 'Lire ce qu’elle a observé',
        detail: 'Les entrées se consultent par thème, avec leur source et leur confiance.',
        featureKeys: ['journals'],
      },
      {
        title: 'Replacer une observation dans son contexte',
        detail: 'Une confirmation ou une contradiction peut faire évoluer sa confiance.',
        featureKeys: ['journals'],
      },
      {
        title: 'Corriger et garder la main',
        detail: 'Tu modifies une entrée, signales une erreur ou relances la consolidation.',
        featureKeys: ['journals'],
      },
    ],
    voiceover:
      'Les journaux gardent les observations que LIA tire des échanges, avec un thème, une source et un degré de confiance. Une précision peut faire évoluer ce qu’elle comprend. Tu lis ses entrées, les modifies ou signales une erreur ; son portrait nomme ses appuis.',
    evidence: [
      'apps/web/src/components/settings/JournalsSettings.tsx',
      'apps/web/src/hooks/useJournals.ts',
      'apps/web/locales/fr/translation.json',
    ],
  }),
  scene({
    id: 'focus-habits',
    kind: 'habits',
    durationSeconds: 20,
    accent: '#8ee5b2',
    eyebrow: 'Focus · Les habitudes observées',
    title: 'Ton rythme devient visible.',
    subtitle: 'Des observations, une progression et des choix que tu peux revoir.',
    cards: [
      {
        label: 'Observation',
        title: 'Ton rythme sur la journée',
        detail: 'Carte des heures, jours observés et seuils affichés.',
        icon: 'chart',
      },
      {
        label: 'Habitude confirmée',
        title: 'Une série et ses jalons',
        detail: 'La progression reprend le registre d’activité.',
        icon: 'repeat',
      },
      {
        label: 'À ton choix',
        title: 'Activer, mettre en pause, oublier',
        detail: 'Une habitude peut aussi être bloquée.',
        icon: 'pause',
      },
    ],
    beats: [
      {
        title: 'Voir d’où vient l’observation',
        detail: 'Carte des heures, jours observés et seuils appliqués se consultent.',
        featureKeys: ['habits'],
      },
      {
        title: 'Suivre une habitude confirmée',
        detail: 'Séries, jalons et évolution restent liés au registre d’activité.',
        featureKeys: ['habits_lifecycle'],
      },
      {
        title: 'Régler ce que tu gardes',
        detail: 'Mettre en pause, bloquer ou oublier une habitude depuis ses contrôles.',
        featureKeys: ['habits'],
      },
    ],
    footnote: 'Apprentissage des habitudes désactivé par défaut · activation volontaire.',
    voiceover:
      'Si tu actives l’apprentissage, LIA observe ton rythme et les demandes récurrentes. Les jours observés et les seuils restent visibles. Une habitude confirmée porte sa série et ses jalons. Tu peux la mettre en pause, la bloquer ou l’oublier.',
    evidence: [
      'apps/web/src/components/settings/HabitsSettings.tsx',
      'apps/web/src/components/settings/HabitExplanation.tsx',
      'apps/web/src/hooks/useHabits.ts',
      'apps/web/locales/fr/translation.json',
    ],
  }),
  scene({
    id: 'focus-speaking-avatar',
    kind: 'voice',
    durationSeconds: 20,
    accent: '#ffa9cb',
    eyebrow: 'Focus · Option expérimentale',
    status: 'experimental',
    title: 'Un avatar parlant personnel.',
    subtitle: 'Un visage Simli peut accompagner les commentaires vocaux et le Live.',
    cards: [
      {
        label: 'Activation volontaire',
        title: 'Ton compte Simli',
        detail: 'Connecteur chiffré et clé personnelle.',
        icon: 'shield',
      },
      {
        label: 'À portée',
        title: 'Une fenêtre mobile',
        detail: 'Trois tailles et un contrôle d’arrêt.',
        icon: 'avatar',
      },
      {
        label: 'État visible',
        title: 'Connexion et fermeture',
        detail: 'Fermeture confirmée ou en attente.',
        icon: 'wave',
      },
    ],
    beats: [
      {
        title: 'Une option personnelle',
        detail: 'Activation explicite et connecteur Simli de ton compte.',
        featureKeys: ['mood_face', 'voice_mode'],
      },
      {
        title: 'Avec les commentaires et le Live',
        detail: 'Fenêtre déplaçable, tailles et contrôle de fermeture.',
        featureKeys: ['live_voice'],
      },
    ],
    footnote:
      'Expérimental · crédits Simli possibles pendant le silence · qualification fournisseur et appareils en cours.',
    voiceover:
      'En option expérimentale, un visage Simli peut accompagner les commentaires vocaux et le Live. Tu relies ton propre compte et actives la fonction. Sa fenêtre affiche la connexion et la fermeture. Le fonctionnement reste en qualification, avec une consommation possible pendant le silence.',
    evidence: ['docs/technical/SPEAKING_AVATAR.md', 'README.md'],
  }),
];

export const durationSeconds = (scenes: readonly MotionScene[]): number =>
  scenes.reduce((total, content) => total + content.durationSeconds, 0);

export const durationFrames = (scenes: readonly MotionScene[]): number =>
  durationSeconds(scenes) * FPS;
