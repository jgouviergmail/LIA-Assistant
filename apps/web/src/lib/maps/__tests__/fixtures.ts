/**
 * A small, hand-written `MapsData`: three functional bricks in two families,
 * two technical bricks in one layer, three decisions across two chapters — big
 * enough for every rule of the views to bite, small enough to read.
 */

import type { MapsData } from '../types';

export function mapsDataFixture(): MapsData {
  return {
    functional: {
      groups: [
        { id: 'g.a', icon: 'brain', tone: 'blue' },
        { id: 'g.b', icon: 'bell', tone: 'rose' },
      ],
      bricks: [
        {
          id: 'f.one',
          group: 'g.a',
          icon: 'brain',
          domains: ['alpha'],
          surfaces: ['/dashboard/chat'],
          deps: ['f.two'],
        },
        { id: 'f.two', group: 'g.a', icon: 'bell', deps: [] },
        { id: 'f.three', group: 'g.b', icon: 'mail', deps: ['f.one'] },
      ],
      flows: [{ id: 'flow.x', icon: 'send', steps: ['f.one', 'f.two', 'f.two', 'f.three'] }],
    },
    technical: {
      repo: 'https://example.test/blob/main/',
      layers: [{ id: 'l.a', icon: 'cpu', tone: 'violet' }],
      bricks: [
        {
          id: 't.one',
          layer: 'l.a',
          icon: 'cpu',
          paths: ['apps/api/src/core'],
          domains: ['alpha'],
          infra: ['cache'],
          deps: [],
        },
        { id: 't.two', layer: 'l.a', icon: 'server', deps: ['t.one'] },
      ],
      flows: [{ id: 'tflow.y', icon: 'send', steps: ['t.one', 't.two'] }],
    },
    history: {
      themes: [
        { id: 'platform', icon: 'rocket', tone: 'slate' },
        { id: 'voice', icon: 'mic', tone: 'amber' },
      ],
      eras: [
        { id: 'first', from: '2025-10-01', to: '2025-12-31' },
        { id: 'second', from: '2026-01-01', to: null },
      ],
      entries: [
        {
          adr: 1,
          date: '2025-10-15',
          theme: 'platform',
          functional: ['f.one'],
          technical: ['t.one'],
        },
        {
          adr: 2,
          date: '2025-11-02',
          theme: 'voice',
          functional: ['f.one', 'f.two'],
          technical: ['t.one'],
        },
        {
          adr: 3,
          date: '2026-01-10',
          theme: 'platform',
          functional: ['f.three'],
          technical: ['t.two'],
          nofile: 'Documented elsewhere.',
        },
      ],
    },
    text: {
      functional: {
        intro: { lede: 'Ce que LIA fait.' },
        groups: {
          'g.a': { name: 'Converser', summary: 'Le fil.' },
          'g.b': { name: 'Prévenir', summary: 'Les alertes.' },
        },
        bricks: {
          'f.one': { name: 'Conversation', role: 'Le fil de discussion.', goal: 'Répondre juste.' },
          'f.two': { name: 'Mémoire', role: 'Se souvenir.', goal: 'Ne rien redemander.' },
          'f.three': { name: 'Notifications', role: 'Prévenir.', goal: 'Au bon moment.' },
        },
        flows: {
          'flow.x': {
            name: 'Une demande',
            summary: 'Le chemin par défaut.',
            steps: ['Tu écris.', 'Elle se souvient.', 'Elle vérifie.', 'Elle prévient.'],
          },
        },
      },
      technical: {
        intro: { lede: 'Comment LIA est construite.' },
        layers: { 'l.a': { name: 'Socle', summary: "L'API." } },
        bricks: {
          't.one': { name: 'FastAPI', role: "L'API.", stack: ['Python 3.14', 'Pydantic v2'] },
          't.two': { name: 'Redis', role: 'Le cache.', stack: [] },
        },
        flows: {
          'tflow.y': {
            name: 'Une requête',
            summary: 'Aller-retour.',
            steps: ['Entrée.', 'Cache.'],
          },
        },
      },
      history: {
        intro: { lede: 'Chaque décision.' },
        themes: {
          platform: { name: 'Plateforme', summary: 'Livrer.' },
          voice: { name: 'Voix', summary: 'Parler.' },
        },
        eras: {
          first: { name: 'Les fondations', summary: 'Le début.' },
          second: { name: 'La suite', summary: 'Après.' },
        },
        entries: {
          '1': { title: 'Un graphe', summary: 'LangGraph orchestre.' },
          '2': { title: 'La voix', summary: 'LIA parle.' },
          '3': { title: 'Un cache', summary: 'Redis retient.' },
        },
      },
    },
    facts: {
      version: '1.2.0',
      releaseDate: '2026-01-20',
      releases: 5,
      milestones: [
        { version: '1.0.0', date: '2025-11-01' },
        { version: '1.2.0', date: '2026-01-20' },
      ],
      domains: 2,
      infra: 1,
      adrFiles: { '1': 'ADR-001-First.md', '2': 'ADR-002-Second.md' },
    },
  };
}
