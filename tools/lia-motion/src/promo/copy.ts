/**
 * Every word the film shows, in one place (French edition).
 *
 * Claims are the landing page's own (`apps/web/locales/fr/translation.json`,
 * `landing.*`): 20+ specialised agents, 14 personalities, six interface
 * languages, sensitive actions confirmed by the person. Names and data are
 * fictitious. Another language is another copy of this object, rendered as
 * its own reviewed composition.
 */
export type Segment = string | { g: string };

export const COPY = {
  hook: {
    items: [
      'Tes e-mails.',
      'Ton agenda.',
      'Tes contacts.',
      'Tes fichiers.',
      'Tes tâches.',
      'Tes rappels.',
      'Tes trajets.',
      'Ta maison.',
      'Tes réunions.',
      'Tes documents.',
    ],
    scattered: ['Ton quotidien', 'est éparpillé.'],
  },
  reveal: {
    line: [{ g: 'LIA' }, ' garde le fil.'] as Segment[],
    sub: 'Ton assistant IA personnel.',
  },
  context: {
    ready: ['Ta journée,', 'déjà prête.'],
    links: ['Elle relie', 'tes sources.'],
    knows: ['Elle apprend', 'à te connaître.'],
  },
  action: {
    sentence: ['Une phrase', 'suffit.'],
    parallel: ['Trois actions,', 'en parallèle.'],
    click: ['Tu valides', 'd’un clic.'],
    control: ['Tu gardes', [{ g: 'la main.' }] as Segment[]],
  },
  anticipate: {
    first: ['Elle', 'anticipe.'],
    second: ['Tu', 'décides.'],
  },
  /**
   * The six chapters' illustrated enumerations: a lead, a title, and per tile
   * a product label (`apps/web/locales/fr`) with one line of what it does.
   */
  know: {
    lead: 'Les autres répondent.',
    title: [[{ g: 'LIA te' }], [{ g: 'connaît.' }]] as Segment[][],
    memory: ['Mémoire avancée', 'Chaque souvenir qualifié, rappelé au bon moment.'],
    interests: ['Centres d’intérêt', 'Elle suit tes sujets et t’en apporte l’essentiel.'],
    habits: ['Habitudes', 'Ton rythme appris, visible et corrigeable.'],
    commitments: ['Engagements', '« Je dois », « On me doit » : rien ne se perd.'],
    portrait: ['Comment LIA te perçoit', 'Son regard sur toi, en toute transparence.'],
    psyche: ['Sa psyché', 'Humeur et émotions qui nuancent chaque échange.'],
    personas: ['Personnalités et avatars', '14 caractères, des compagnons animés.'],
  },
  act: {
    lead: 'Bien plus qu’un chat.',
    title: [[{ g: 'Elle fait' }], [{ g: 'le travail.' }]] as Segment[][],
    documents: ['Word, Excel, PowerPoint', 'Des fichiers soignés, prêts à partager.'],
    images: ['Génération d’images', 'Crée et retouche des images sur mesure.'],
    skills: ['Compétences (skills)', 'Tes savoir-faire, décrits en une phrase.'],
    mcp: ['MCP et plugins', 'Branche tes outils et tes extensions.'],
    spaces: ['Espaces de connaissances', 'Interroge tes documents, sources citées.'],
    menus: ['Menus contextuels', 'Un clic sur un mail : « Demander à LIA ».'],
    pages: ['Pages interactives', 'Un jeu, un quiz, un outil, en une phrase.'],
  },
  foresee: {
    lead: 'Elle n’attend pas',
    title: [[{ g: 'que tu' }], [{ g: 'demandes.' }]] as Segment[][],
    proactive: ['Notifications proactives', 'Ce qu’elle juge utile de te dire.'],
    discussions: ['Discussions proactives', 'Elle ouvre la conversation au bon moment.'],
    reminders: ['Rappels', 'Uniques ou récurrents, jamais oubliés.'],
    routines: ['Actions planifiées', 'À l’heure dite, sur condition ou par webhook.'],
    push: ['Notifications push', 'Sur ton téléphone comme sur ton ordinateur.'],
    radio: ['Radio LIA', 'Tes infos et ta journée, lues pour toi.'],
  },
  channels: {
    lead: 'Même loin de l’écran.',
    title: [[{ g: 'Partout' }], [{ g: 'avec toi.' }]] as Segment[][],
    live: ['Live et Live direct', 'Une conversation à voix haute, en temps réel.'],
    calls: ['Appels', 'Elle t’appelle, tu lui réponds de vive voix.'],
    telegram: ['Telegram', 'Écris-lui ou envoie-lui un vocal.'],
    sms: ['Mes SMS', 'Archivés, chiffrés, repris dans ton briefing.'],
    apps: ['Android et iPhone', 'Une app reliée à ton propre serveur.'],
    world: ['Le Monde de LIA', 'Une maison et son jardin à explorer avec elle.'],
    languages: ['6 langues', 'De l’interface aux personnalités.'],
  },
  circle: {
    lead: 'Et avec tes proches.',
    title: [[{ g: 'Ton cercle,' }], [{ g: 'connecté.' }]] as Segment[][],
    relay: ['Messages relayés', '« Dis à Léa que j’arrive » : c’est transmis.'],
    connections: ['Mes connexions', 'Relie-toi aux personnes de ton instance.'],
    sharing: ['Partage en lecture seule', 'Agenda et tâches, avec qui tu veux.'],
    capabilities: ['Skills, MCP et plugins', 'Partage tes capacités avec tes proches.'],
    log: ['Accès tracés', 'Chaque lecture de tes partages est notée.'],
  },
  control: {
    lead: 'Rien n’est caché.',
    title: [[{ g: 'Tout est' }], [{ g: 'tracé.' }]] as Segment[][],
    registers: ['Registres', 'Ce qu’elle a fait, lu et tenté, résultat compris.'],
    cost: ['Consommation', 'Le coût de chaque réponse, affiché.'],
    approval: ['Validation humaine', 'Rien de sensible sans ton accord.'],
    export: ['Export données', 'Toutes tes données, en une archive.'],
    security: ['Sécurité', 'Authentification forte, appareils, chiffrement.'],
    dashboards: ['Tableaux de bord', 'Suivi complet : usage, coûts, santé du service.'],
    openSource: ['Open source', 'Auto-hébergeable : tes données chez toi.'],
  },
  linked: {
    title: 'Tout est relié.',
    agents: '20+ agents spécialisés. Une seule assistante.',
  },
  simple: {
    devices: 'Sur ordinateur et téléphone.',
    clicks: 'Quelques clics. Aucune commande à retenir.',
  },
  outro: {
    lines: [
      ['Ton quotidien.'] as Segment[],
      [{ g: 'LIA' }, ' garde le fil.'] as Segment[],
      ['Tu gardes la main.'] as Segment[],
    ],
    footer: 'Assistant IA personnel  ·  Open source  ·  Conçu en France',
  },
} as const;
