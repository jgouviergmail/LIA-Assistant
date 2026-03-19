'use client';

import {
  BookOpen,
  CheckCircle2,
  ExternalLink,
  FileCode2,
  FolderOpen,
  Globe,
  Lightbulb,
  Zap,
} from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

// --- Static examples (no i18n needed for code) ---

const SKILL_EXAMPLE = `---
name: mon-skill
description: >
  Décrit ce que fait le skill et quand l'utiliser.
  Exemple : aide à rédiger des emails formels en français.
category: productivite
priority: 50
---

# Mon Skill

## Instructions

1. Analyser la demande de l'utilisateur
2. Appliquer les règles métier spécialisées
3. Fournir une réponse structurée et professionnelle`;

const PLAN_TEMPLATE_EXAMPLE = `plan_template:
  deterministic: true
  steps:
    - step_id: get_events
      agent_name: event_agent
      tool_name: get_events_tool
      parameters: {}
      depends_on: []
      description: Récupérer les événements du jour

    - step_id: get_weather
      agent_name: weather_agent
      tool_name: get_weather_forecast_tool
      parameters:
        days: 3
      depends_on: []
      description: Météo + tendance 3 jours

    - step_id: get_emails
      agent_name: email_agent
      tool_name: get_emails_tool
      parameters:
        query: "in:inbox newer_than:1d"
        max_results: 5
      depends_on: []
      description: 5 derniers emails du jour`;

// Agent → main tool(s) for plan_template
const AGENTS_TABLE = [
  { agent: 'event_agent', tool: 'get_events_tool', desc: 'Agenda & calendrier' },
  { agent: 'email_agent', tool: 'get_emails_tool', desc: 'Emails (query Gmail)' },
  { agent: 'task_agent', tool: 'get_tasks_tool', desc: 'Tâches' },
  { agent: 'weather_agent', tool: 'get_weather_forecast_tool', desc: 'Météo & prévisions' },
  { agent: 'contact_agent', tool: 'get_contacts_tool', desc: 'Contacts' },
  { agent: 'place_agent', tool: 'get_places_tool', desc: 'Lieux & adresses' },
  { agent: 'route_agent', tool: 'get_route_tool', desc: 'Itinéraires' },
  { agent: 'file_agent', tool: 'get_files_tool', desc: 'Fichiers Drive' },
  { agent: 'web_search_agent', tool: 'unified_web_search_tool', desc: 'Recherche web' },
  { agent: 'web_fetch_agent', tool: 'fetch_web_page_tool', desc: 'Lecture de page web' },
  { agent: 'wikipedia_agent', tool: 'search_wikipedia_tool', desc: 'Wikipedia' },
  { agent: 'perplexity_agent', tool: 'perplexity_search_tool', desc: 'Recherche IA' },
  { agent: 'brave_agent', tool: 'brave_search_tool', desc: 'Recherche + actualités' },
];

// --- Component ---

interface SkillGuideModalProps {
  lng: Language;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SkillGuideModal({ lng, open, onOpenChange }: SkillGuideModalProps) {
  const { t } = useTranslation(lng);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto">
        <DialogHeader className="pb-2">
          <DialogTitle className="flex items-center gap-2.5 text-xl">
            <div className="rounded-lg bg-primary/10 p-1.5 shrink-0">
              <BookOpen className="h-5 w-5 text-primary" />
            </div>
            {t('settings.skills.guide_modal_title')}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-7 py-1">
          {/* ① What is a skill */}
          <section className="space-y-3">
            <SectionHeader
              icon={<Lightbulb className="h-4 w-4 text-violet-500" />}
              iconBg="bg-violet-500/10"
              title={t('settings.skills.guide_modal_what_title')}
            />
            <p className="text-sm text-muted-foreground leading-relaxed pl-9">
              {t('settings.skills.guide_modal_what_body')}
            </p>
          </section>

          {/* ② SKILL.md format */}
          <section className="space-y-3">
            <SectionHeader
              icon={<FileCode2 className="h-4 w-4 text-blue-500" />}
              iconBg="bg-blue-500/10"
              title={t('settings.skills.guide_modal_format_title')}
            />
            <p className="text-sm text-muted-foreground pl-9">
              {t('settings.skills.guide_modal_format_intro')}
            </p>
            <CodeBlock>{SKILL_EXAMPLE}</CodeBlock>
          </section>

          {/* ③ Plan template */}
          <section className="space-y-3">
            <SectionHeader
              icon={<Zap className="h-4 w-4 text-orange-500" />}
              iconBg="bg-orange-500/10"
              title={t('settings.skills.guide_modal_plan_title')}
            />
            <p className="text-sm text-muted-foreground leading-relaxed pl-9">
              {t('settings.skills.guide_modal_plan_body')}
            </p>
            <CodeBlock>{PLAN_TEMPLATE_EXAMPLE}</CodeBlock>

            {/* Fields legend */}
            <div className="rounded-xl bg-muted/40 border p-4 ml-0 space-y-2">
              <p className="text-xs font-semibold text-foreground/70 mb-2">
                {t('settings.skills.guide_modal_plan_fields_title')}
              </p>
              <div className="grid grid-cols-1 gap-1.5 text-xs">
                {[
                  ['step_id', t('settings.skills.guide_modal_plan_field_step_id')],
                  ['agent_name', t('settings.skills.guide_modal_plan_field_agent')],
                  ['tool_name', t('settings.skills.guide_modal_plan_field_tool')],
                  ['parameters', t('settings.skills.guide_modal_plan_field_params')],
                  ['depends_on', t('settings.skills.guide_modal_plan_field_depends')],
                ].map(([key, desc]) => (
                  <div key={key} className="flex gap-2">
                    <code className="shrink-0 font-mono text-primary/80 w-24">{key}</code>
                    <span className="text-muted-foreground">{desc}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Agents table */}
            <div className="space-y-2">
              <p className="text-xs font-semibold text-foreground/70">
                {t('settings.skills.guide_modal_plan_agents')}
              </p>
              <div className="rounded-xl border overflow-hidden text-xs">
                <table className="w-full">
                  <thead>
                    <tr className="bg-muted/60 text-muted-foreground">
                      <th className="text-left px-3 py-2 font-medium">agent_name</th>
                      <th className="text-left px-3 py-2 font-medium">tool_name principal</th>
                      <th className="text-left px-3 py-2 font-medium hidden sm:table-cell">
                        Usage
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {AGENTS_TABLE.map(({ agent, tool, desc }, i) => (
                      <tr key={agent} className={i % 2 === 0 ? 'bg-background' : 'bg-muted/20'}>
                        <td className="px-3 py-1.5 font-mono text-blue-600 dark:text-blue-400 whitespace-nowrap">
                          {agent}
                        </td>
                        <td className="px-3 py-1.5 font-mono text-foreground/70 whitespace-nowrap">
                          {tool}
                        </td>
                        <td className="px-3 py-1.5 text-muted-foreground hidden sm:table-cell">
                          {desc}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-muted-foreground/60 italic">
                {t('settings.skills.guide_modal_plan_note')}
              </p>
            </div>
          </section>

          {/* ④ Directory structure */}
          <section className="space-y-3">
            <SectionHeader
              icon={<FolderOpen className="h-4 w-4 text-amber-500" />}
              iconBg="bg-amber-500/10"
              title={t('settings.skills.guide_modal_struct_title')}
            />
            <p className="text-sm text-muted-foreground leading-relaxed pl-9">
              {t('settings.skills.guide_modal_struct_body')}
            </p>
            <div className="rounded-xl bg-muted/50 border p-4 text-xs font-mono space-y-1 ml-9">
              <div className="text-foreground font-medium">📁 mon-skill/</div>
              <div className="pl-5 text-foreground">📄 SKILL.md</div>
              <div className="pl-5 text-muted-foreground">
                📁 scripts/ &nbsp;<span className="text-muted-foreground/50">— scripts Python</span>
              </div>
              <div className="pl-5 text-muted-foreground">
                📁 references/ &nbsp;
                <span className="text-muted-foreground/50">— docs de référence</span>
              </div>
              <div className="pl-5 text-muted-foreground">
                📁 assets/ &nbsp;
                <span className="text-muted-foreground/50">— templates, ressources</span>
              </div>
            </div>
          </section>

          {/* ⑤ Best practices */}
          <section className="space-y-3">
            <SectionHeader
              icon={<CheckCircle2 className="h-4 w-4 text-green-500" />}
              iconBg="bg-green-500/10"
              title={t('settings.skills.guide_modal_tips_title')}
            />
            <ul className="space-y-2.5 pl-9">
              {[1, 2, 3, 4].map(i => (
                <li key={i} className="flex gap-2.5 text-sm text-muted-foreground">
                  <span className="text-green-500 shrink-0 mt-0.5">✓</span>
                  <span>{t(`settings.skills.guide_modal_tip_${i}`)}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* ⑥ Compatibility banner */}
          <section className="rounded-xl border bg-primary/5 p-5 space-y-2.5">
            <div className="flex items-center gap-2">
              <Globe className="h-4 w-4 text-primary shrink-0" />
              <h3 className="font-semibold text-sm">
                {t('settings.skills.guide_modal_compat_title')}
              </h3>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t('settings.skills.guide_modal_compat_body')}
            </p>
            <a
              href="https://claude.com/blog/equipping-agents-for-the-real-world-with-agent-skills"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline font-medium"
            >
              {t('settings.skills.guide_modal_link')}
              <ExternalLink className="h-3 w-3 shrink-0" />
            </a>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// --- Sub-components ---

function SectionHeader({
  icon,
  iconBg,
  title,
}: {
  icon: React.ReactNode;
  iconBg: string;
  title: string;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <div className={`rounded-lg ${iconBg} p-1.5 shrink-0`}>{icon}</div>
      <h3 className="font-semibold text-base">{title}</h3>
    </div>
  );
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="rounded-xl bg-muted/70 border p-4 text-xs font-mono overflow-x-auto leading-relaxed text-foreground/80">
      {children}
    </pre>
  );
}
