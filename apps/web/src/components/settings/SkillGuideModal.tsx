'use client';

import {
  BookOpen,
  CheckCircle2,
  Code2,
  ExternalLink,
  FileCode2,
  FolderOpen,
  Globe,
  Lightbulb,
  Puzzle,
  Rocket,
  Sparkles,
  Terminal,
  Zap,
} from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

// --- Static code examples (no i18n needed) ---

const SKILL_SIMPLE_EXAMPLE = `---
name: coaching-productivite
description: >
  Provides productivity coaching with prioritization
  frameworks (Eisenhower, Pomodoro). Use when the user
  asks for help organizing tasks or managing time.
category: productivite
priority: 50
---

# Coaching Productivité

## Instructions

1. Écouter le contexte : charge, contraintes, énergie
2. Diagnostiquer le frein principal
3. Proposer un framework adapté (Eisenhower, Pomodoro…)
4. Simplifier : 1-2 changements, pas une refonte totale

## Ressources disponibles

- references/techniques.md — Fiches détaillées des méthodes`;

const SKILL_ADVISORY_EXAMPLE = `---
name: preparation-reunion
description: >
  Prepares meeting materials by gathering calendar details,
  participant contacts, and recent email history. Use when
  the user mentions preparing for a meeting.
category: organisation
priority: 65
---

# Préparation de Réunion

## Instructions

1. Identifier la réunion cible dans le calendrier
2. Extraire les détails : titre, date, participants
3. Récupérer les coordonnées de chaque participant
4. Chercher les échanges email récents
5. Compiler un dossier de préparation structuré`;

const PLAN_TEMPLATE_EXAMPLE = `---
name: briefing-quotidien
description: >
  Generates a comprehensive today briefing combining
  calendar events, priority tasks, and weather forecast.
  Use when the user asks for a daily summary.
category: quotidien
priority: 70
plan_template:
  deterministic: true
  steps:
    - step_id: get_events
      agent_name: event_agent
      tool_name: get_events_tool
      parameters:
        days_ahead: 2
        max_results: 5
      depends_on: []
      description: Événements du jour et du lendemain

    - step_id: get_tasks
      agent_name: task_agent
      tool_name: get_tasks_tool
      parameters:
        show_completed: false
      depends_on: []
      description: Tâches en cours et prioritaires

    - step_id: get_weather
      agent_name: weather_agent
      tool_name: get_weather_forecast_tool
      parameters:
        days: 3
      depends_on: []
      description: Météo + tendance 3 jours
---

# Briefing Quotidien

## Instructions

1. Récupérer rdv, tâches, météo, emails
2. Formater : Agenda → Tâches → Météo → À noter
3. Commencer par le plus urgent`;

const SCRIPT_EXAMPLE = `# scripts/analyze.py
import json
import sys

data = json.loads(sys.stdin.read())
# ... traitement ...
print(json.dumps({"result": "ok"}))`;

// --- Tools catalogue organized by category ---

interface ToolParam {
  name: string;
  type: string;
  required?: boolean;
  desc: string;
}

interface ToolDef {
  name: string;
  desc: string;
  params: ToolParam[];
}

interface AgentDef {
  agent: string;
  label: string;
  oauth?: boolean;
  tools: ToolDef[];
}

interface AgentCategory {
  category: string;
  agents: AgentDef[];
}

const TOOL_CATALOGUE: AgentCategory[] = [
  {
    category: 'productivity',
    agents: [
      {
        agent: 'event_agent',
        label: 'Calendar',
        oauth: true,
        tools: [
          {
            name: 'get_events_tool',
            desc: 'tool_get_events',
            params: [
              { name: 'query', type: 'string', desc: 'param_search_query' },
              { name: 'event_id', type: 'string', desc: 'param_event_id' },
              { name: 'time_min', type: 'string (ISO 8601)', desc: 'param_time_min' },
              { name: 'time_max', type: 'string (ISO 8601)', desc: 'param_time_max' },
              { name: 'days_ahead', type: 'int', desc: 'param_days_ahead' },
              { name: 'max_results', type: 'int', desc: 'param_max_results' },
            ],
          },
          {
            name: 'create_event_tool',
            desc: 'tool_create_event',
            params: [
              { name: 'summary', type: 'string', required: true, desc: 'param_event_summary' },
              {
                name: 'start_datetime',
                type: 'string (ISO 8601)',
                required: true,
                desc: 'param_start_dt',
              },
              {
                name: 'end_datetime',
                type: 'string (ISO 8601)',
                required: true,
                desc: 'param_end_dt',
              },
              { name: 'timezone', type: 'string', desc: 'param_timezone' },
              { name: 'description', type: 'string', desc: 'param_description' },
              { name: 'location', type: 'string', desc: 'param_location' },
              { name: 'attendees', type: 'list[string]', desc: 'param_attendees' },
            ],
          },
          {
            name: 'update_event_tool',
            desc: 'tool_update_event',
            params: [
              { name: 'event_id', type: 'string', required: true, desc: 'param_event_id' },
              { name: 'summary', type: 'string', desc: 'param_event_summary' },
              { name: 'start_datetime', type: 'string (ISO 8601)', desc: 'param_start_dt' },
              { name: 'end_datetime', type: 'string (ISO 8601)', desc: 'param_end_dt' },
            ],
          },
          {
            name: 'delete_event_tool',
            desc: 'tool_delete_event',
            params: [
              { name: 'event_id', type: 'string', required: true, desc: 'param_event_id' },
            ],
          },
          {
            name: 'list_calendars_tool',
            desc: 'tool_list_calendars',
            params: [{ name: 'show_hidden', type: 'bool', desc: 'param_show_hidden' }],
          },
        ],
      },
      {
        agent: 'email_agent',
        label: 'Email',
        oauth: true,
        tools: [
          {
            name: 'get_emails_tool',
            desc: 'tool_get_emails',
            params: [
              { name: 'query', type: 'string', desc: 'param_gmail_query' },
              { name: 'message_id', type: 'string', desc: 'param_message_id' },
              { name: 'max_results', type: 'int', desc: 'param_max_results' },
            ],
          },
          {
            name: 'send_email_tool',
            desc: 'tool_send_email',
            params: [
              { name: 'to', type: 'string', required: true, desc: 'param_email_to' },
              { name: 'subject', type: 'string', desc: 'param_email_subject' },
              { name: 'body', type: 'string', desc: 'param_email_body' },
              {
                name: 'content_instruction',
                type: 'string',
                desc: 'param_content_instruction',
              },
              { name: 'cc', type: 'string', desc: 'param_cc' },
              { name: 'is_html', type: 'bool', desc: 'param_is_html' },
            ],
          },
          {
            name: 'reply_email_tool',
            desc: 'tool_reply_email',
            params: [
              { name: 'message_id', type: 'string', required: true, desc: 'param_message_id' },
              { name: 'body', type: 'string', required: true, desc: 'param_email_body' },
              { name: 'reply_all', type: 'bool', desc: 'param_reply_all' },
            ],
          },
          {
            name: 'forward_email_tool',
            desc: 'tool_forward_email',
            params: [
              { name: 'message_id', type: 'string', required: true, desc: 'param_message_id' },
              { name: 'to', type: 'string', required: true, desc: 'param_email_to' },
            ],
          },
          {
            name: 'apply_labels_tool',
            desc: 'tool_apply_labels',
            params: [
              {
                name: 'label_names',
                type: 'list[string]',
                required: true,
                desc: 'param_label_names',
              },
              { name: 'message_id', type: 'string', desc: 'param_message_id' },
            ],
          },
        ],
      },
      {
        agent: 'contact_agent',
        label: 'Contacts',
        oauth: true,
        tools: [
          {
            name: 'get_contacts_tool',
            desc: 'tool_get_contacts',
            params: [
              { name: 'query', type: 'string', desc: 'param_search_query' },
              { name: 'resource_name', type: 'string', desc: 'param_resource_name' },
              { name: 'max_results', type: 'int', desc: 'param_max_results' },
            ],
          },
          {
            name: 'create_contact_tool',
            desc: 'tool_create_contact',
            params: [
              { name: 'name', type: 'string', required: true, desc: 'param_contact_name' },
              { name: 'email', type: 'string', desc: 'param_contact_email' },
              { name: 'phone', type: 'string', desc: 'param_contact_phone' },
              { name: 'organization', type: 'string', desc: 'param_organization' },
            ],
          },
        ],
      },
      {
        agent: 'file_agent',
        label: 'Drive / Files',
        oauth: true,
        tools: [
          {
            name: 'get_files_tool',
            desc: 'tool_get_files',
            params: [
              { name: 'query', type: 'string', desc: 'param_search_query' },
              { name: 'file_id', type: 'string', desc: 'param_file_id' },
              { name: 'folder_id', type: 'string', desc: 'param_folder_id' },
              { name: 'max_results', type: 'int', desc: 'param_max_results' },
              { name: 'include_content', type: 'bool', desc: 'param_include_content' },
              { name: 'search_mode', type: 'string', desc: 'param_search_mode' },
            ],
          },
        ],
      },
      {
        agent: 'task_agent',
        label: 'Tasks',
        oauth: true,
        tools: [
          {
            name: 'get_tasks_tool',
            desc: 'tool_get_tasks',
            params: [
              { name: 'task_id', type: 'string', desc: 'param_task_id' },
              { name: 'task_list_id', type: 'string', desc: 'param_task_list_id' },
              { name: 'max_results', type: 'int', desc: 'param_max_results' },
              { name: 'show_completed', type: 'bool', desc: 'param_show_completed' },
            ],
          },
          {
            name: 'create_task_tool',
            desc: 'tool_create_task',
            params: [
              { name: 'title', type: 'string', required: true, desc: 'param_task_title' },
              { name: 'notes', type: 'string', desc: 'param_task_notes' },
              { name: 'due', type: 'string (ISO 8601)', desc: 'param_task_due' },
            ],
          },
          {
            name: 'complete_task_tool',
            desc: 'tool_complete_task',
            params: [
              { name: 'task_id', type: 'string', required: true, desc: 'param_task_id' },
            ],
          },
        ],
      },
    ],
  },
  {
    category: 'web_search',
    agents: [
      {
        agent: 'web_search_agent',
        label: 'Web Search',
        tools: [
          {
            name: 'unified_web_search_tool',
            desc: 'tool_web_search',
            params: [
              { name: 'query', type: 'string', required: true, desc: 'param_search_query' },
              { name: 'recency', type: 'string', desc: 'param_recency' },
            ],
          },
        ],
      },
      {
        agent: 'web_fetch_agent',
        label: 'Web Fetch',
        tools: [
          {
            name: 'fetch_web_page_tool',
            desc: 'tool_fetch_page',
            params: [
              { name: 'url', type: 'string', required: true, desc: 'param_url' },
              { name: 'extract_mode', type: 'string', desc: 'param_extract_mode' },
              { name: 'max_length', type: 'int', desc: 'param_max_length' },
            ],
          },
        ],
      },
      {
        agent: 'wikipedia_agent',
        label: 'Wikipedia',
        tools: [
          {
            name: 'search_wikipedia_tool',
            desc: 'tool_search_wikipedia',
            params: [
              { name: 'query', type: 'string', required: true, desc: 'param_search_query' },
              { name: 'language', type: 'string', desc: 'param_language' },
              { name: 'max_results', type: 'int', desc: 'param_max_results' },
            ],
          },
          {
            name: 'get_wikipedia_article_tool',
            desc: 'tool_get_article',
            params: [
              { name: 'title', type: 'string', required: true, desc: 'param_article_title' },
              { name: 'language', type: 'string', desc: 'param_language' },
              { name: 'max_length', type: 'int', desc: 'param_max_length' },
            ],
          },
        ],
      },
      {
        agent: 'perplexity_agent',
        label: 'Perplexity AI',
        tools: [
          {
            name: 'perplexity_search_tool',
            desc: 'tool_perplexity_search',
            params: [
              { name: 'query', type: 'string', required: true, desc: 'param_search_query' },
              { name: 'recency', type: 'string', desc: 'param_recency' },
            ],
          },
          {
            name: 'perplexity_ask_tool',
            desc: 'tool_perplexity_ask',
            params: [
              { name: 'question', type: 'string', required: true, desc: 'param_question' },
              { name: 'context', type: 'string', desc: 'param_context' },
            ],
          },
        ],
      },
      {
        agent: 'brave_agent',
        label: 'Brave Search',
        tools: [
          {
            name: 'brave_search_tool',
            desc: 'tool_brave_search',
            params: [
              { name: 'query', type: 'string', required: true, desc: 'param_search_query' },
              { name: 'count', type: 'int', desc: 'param_count' },
              { name: 'freshness', type: 'string', desc: 'param_freshness' },
            ],
          },
          {
            name: 'brave_news_tool',
            desc: 'tool_brave_news',
            params: [
              { name: 'query', type: 'string', required: true, desc: 'param_search_query' },
              { name: 'count', type: 'int', desc: 'param_count' },
            ],
          },
        ],
      },
    ],
  },
  {
    category: 'location_weather',
    agents: [
      {
        agent: 'place_agent',
        label: 'Places',
        tools: [
          {
            name: 'get_places_tool',
            desc: 'tool_get_places',
            params: [
              { name: 'query', type: 'string', desc: 'param_search_query' },
              { name: 'location', type: 'string', desc: 'param_location' },
              { name: 'place_type', type: 'string', desc: 'param_place_type' },
              { name: 'max_results', type: 'int', desc: 'param_max_results' },
              { name: 'radius_meters', type: 'int', desc: 'param_radius' },
              { name: 'open_now', type: 'bool', desc: 'param_open_now' },
              { name: 'min_rating', type: 'float', desc: 'param_min_rating' },
            ],
          },
        ],
      },
      {
        agent: 'route_agent',
        label: 'Routes',
        tools: [
          {
            name: 'get_route_tool',
            desc: 'tool_get_route',
            params: [
              {
                name: 'destination',
                type: 'string',
                required: true,
                desc: 'param_destination',
              },
              { name: 'origin', type: 'string', desc: 'param_origin' },
              { name: 'travel_mode', type: 'string', desc: 'param_travel_mode' },
              { name: 'departure_time', type: 'string (ISO 8601)', desc: 'param_departure' },
              { name: 'waypoints', type: 'list[string]', desc: 'param_waypoints' },
            ],
          },
        ],
      },
      {
        agent: 'weather_agent',
        label: 'Weather',
        tools: [
          {
            name: 'get_current_weather_tool',
            desc: 'tool_current_weather',
            params: [
              { name: 'location', type: 'string', desc: 'param_location' },
              { name: 'units', type: 'string', desc: 'param_units' },
            ],
          },
          {
            name: 'get_weather_forecast_tool',
            desc: 'tool_weather_forecast',
            params: [
              { name: 'location', type: 'string', desc: 'param_location' },
              { name: 'days', type: 'int', desc: 'param_forecast_days' },
              { name: 'units', type: 'string', desc: 'param_units' },
            ],
          },
          {
            name: 'get_hourly_forecast_tool',
            desc: 'tool_hourly_forecast',
            params: [
              { name: 'location', type: 'string', desc: 'param_location' },
              { name: 'hours', type: 'int', desc: 'param_hours' },
            ],
          },
        ],
      },
    ],
  },
  {
    category: 'other',
    agents: [
      {
        agent: 'reminder_agent',
        label: 'Reminders',
        tools: [
          {
            name: 'create_reminder_tool',
            desc: 'tool_create_reminder',
            params: [
              { name: 'content', type: 'string', required: true, desc: 'param_reminder_content' },
              {
                name: 'original_message',
                type: 'string',
                required: true,
                desc: 'param_original_message',
              },
              { name: 'trigger_datetime', type: 'string (ISO 8601)', desc: 'param_trigger_dt' },
              { name: 'relative_trigger', type: 'string', desc: 'param_relative_trigger' },
            ],
          },
          { name: 'list_reminders_tool', desc: 'tool_list_reminders', params: [] },
          {
            name: 'cancel_reminder_tool',
            desc: 'tool_cancel_reminder',
            params: [
              {
                name: 'reminder_identifier',
                type: 'string',
                required: true,
                desc: 'param_reminder_id',
              },
            ],
          },
        ],
      },
      {
        agent: 'browser_agent',
        label: 'Browser',
        tools: [
          {
            name: 'browser_task_tool',
            desc: 'tool_browser_task',
            params: [
              { name: 'task', type: 'string', required: true, desc: 'param_browser_task' },
            ],
          },
        ],
      },
      {
        agent: 'hue_agent',
        label: 'Philips Hue',
        tools: [
          { name: 'list_hue_lights_tool', desc: 'tool_list_lights', params: [] },
          {
            name: 'control_hue_light_tool',
            desc: 'tool_control_light',
            params: [
              {
                name: 'light_name_or_id',
                type: 'string',
                required: true,
                desc: 'param_light_name',
              },
              { name: 'on', type: 'bool', desc: 'param_light_on' },
              { name: 'brightness', type: 'int (0-100)', desc: 'param_brightness' },
              { name: 'color', type: 'string', desc: 'param_color' },
            ],
          },
          {
            name: 'activate_hue_scene_tool',
            desc: 'tool_activate_scene',
            params: [
              {
                name: 'scene_name_or_id',
                type: 'string',
                required: true,
                desc: 'param_scene_name',
              },
            ],
          },
        ],
      },
      {
        agent: 'image_generation_agent',
        label: 'Image Generation',
        tools: [
          {
            name: 'generate_image',
            desc: 'tool_generate_image',
            params: [
              { name: 'prompt', type: 'string', required: true, desc: 'param_image_prompt' },
            ],
          },
          {
            name: 'edit_image',
            desc: 'tool_edit_image',
            params: [
              { name: 'prompt', type: 'string', required: true, desc: 'param_image_prompt' },
              { name: 'source_attachment_id', type: 'string', desc: 'param_source_image' },
            ],
          },
        ],
      },
    ],
  },
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
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader className="pb-2">
          <DialogTitle className="flex items-center gap-2.5 text-xl">
            <div className="rounded-lg bg-primary/10 p-1.5 shrink-0">
              <BookOpen className="h-5 w-5 text-primary" />
            </div>
            {t('settings.skills.guide_modal_title')}
          </DialogTitle>
          <p className="text-sm text-muted-foreground mt-1">
            {t('settings.skills.guide_modal_subtitle')}
          </p>
        </DialogHeader>

        <Tabs defaultValue="fundamentals" className="w-full">
          <TabsList className="grid w-full grid-cols-3 mb-4">
            <TabsTrigger value="fundamentals" className="text-xs sm:text-sm gap-1">
              <Lightbulb className="h-3.5 w-3.5 hidden sm:block" />
              {t('settings.skills.guide_tab_fundamentals')}
            </TabsTrigger>
            <TabsTrigger value="create" className="text-xs sm:text-sm gap-1">
              <Puzzle className="h-3.5 w-3.5 hidden sm:block" />
              {t('settings.skills.guide_tab_create')}
            </TabsTrigger>
            <TabsTrigger value="advanced" className="text-xs sm:text-sm gap-1">
              <Rocket className="h-3.5 w-3.5 hidden sm:block" />
              {t('settings.skills.guide_tab_advanced')}
            </TabsTrigger>
          </TabsList>

          {/* ═══════════════════ TAB 1: Fundamentals ═══════════════════ */}
          <TabsContent value="fundamentals">
            <div className="space-y-6">
              {/* What is a skill */}
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

              {/* 3 Archetypes */}
              <section className="space-y-3">
                <SectionHeader
                  icon={<Sparkles className="h-4 w-4 text-amber-500" />}
                  iconBg="bg-amber-500/10"
                  title={t('settings.skills.guide_archetypes_title')}
                />
                <div className="grid gap-3 pl-9">
                  {(['prompt_expert', 'advisory', 'plan_template'] as const).map(arch => (
                    <div
                      key={arch}
                      className="rounded-lg border p-3 bg-card/50 hover:bg-card transition-colors"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-semibold">
                          {t(`settings.skills.guide_archetype_${arch}_name`)}
                        </span>
                        <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                          {t(`settings.skills.guide_archetype_${arch}_badge`)}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {t(`settings.skills.guide_archetype_${arch}_desc`)}
                      </p>
                    </div>
                  ))}
                </div>
              </section>

              {/* Activation model */}
              <section className="space-y-3">
                <SectionHeader
                  icon={<Zap className="h-4 w-4 text-orange-500" />}
                  iconBg="bg-orange-500/10"
                  title={t('settings.skills.guide_activation_title')}
                />
                <p className="text-sm text-muted-foreground leading-relaxed pl-9">
                  {t('settings.skills.guide_activation_body')}
                </p>
                <div className="rounded-xl bg-muted/40 border p-4 ml-9 space-y-2">
                  {(['l1', 'l2', 'l3'] as const).map(tier => (
                    <div key={tier} className="flex gap-3 text-xs">
                      <code className="shrink-0 font-mono text-primary/80 w-6 font-bold">
                        {tier.toUpperCase()}
                      </code>
                      <span className="text-muted-foreground">
                        {t(`settings.skills.guide_tier_${tier}`)}
                      </span>
                    </div>
                  ))}
                </div>
              </section>

              {/* Best practices */}
              <section className="space-y-3">
                <SectionHeader
                  icon={<CheckCircle2 className="h-4 w-4 text-green-500" />}
                  iconBg="bg-green-500/10"
                  title={t('settings.skills.guide_modal_tips_title')}
                />
                <ul className="space-y-2 pl-9">
                  {[1, 2, 3, 4, 5, 6].map(i => (
                    <li key={i} className="flex gap-2.5 text-sm text-muted-foreground">
                      <span className="text-green-500 shrink-0 mt-0.5">✓</span>
                      <span>{t(`settings.skills.guide_modal_tip_${i}`)}</span>
                    </li>
                  ))}
                </ul>
              </section>

              {/* Compatibility banner */}
              <CompatBanner t={t} />
            </div>
          </TabsContent>

          {/* ═══════════════════ TAB 2: Create a Skill ═══════════════════ */}
          <TabsContent value="create">
            <div className="space-y-6">
              {/* SKILL.md format */}
              <section className="space-y-3">
                <SectionHeader
                  icon={<FileCode2 className="h-4 w-4 text-blue-500" />}
                  iconBg="bg-blue-500/10"
                  title={t('settings.skills.guide_modal_format_title')}
                />
                <p className="text-sm text-muted-foreground pl-9">
                  {t('settings.skills.guide_modal_format_intro')}
                </p>

                {/* Frontmatter fields */}
                <div className="rounded-xl bg-muted/40 border p-4 space-y-2">
                  <p className="text-xs font-semibold text-foreground/70 mb-2">
                    {t('settings.skills.guide_frontmatter_title')}
                  </p>
                  <div className="grid grid-cols-1 gap-1.5 text-xs">
                    {(
                      [
                        ['name', 'string', true],
                        ['description', 'string', true],
                        ['category', 'string', false],
                        ['priority', 'int (1-100)', false],
                        ['plan_template', 'object', false],
                        ['always_loaded', 'bool', false],
                      ] as const
                    ).map(([key, type, req]) => (
                      <div key={key} className="flex gap-2 items-start">
                        <code className="shrink-0 font-mono text-primary/80 w-28">
                          {key}
                          {req && <span className="text-red-400 ml-0.5">*</span>}
                        </code>
                        <span className="text-muted-foreground/60 w-20 shrink-0">{type}</span>
                        <span className="text-muted-foreground">
                          {t(`settings.skills.guide_field_${key}`)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              {/* Simple example: Prompt Expert */}
              <section className="space-y-3">
                <SectionHeader
                  icon={<Lightbulb className="h-4 w-4 text-violet-500" />}
                  iconBg="bg-violet-500/10"
                  title={t('settings.skills.guide_example_simple_title')}
                />
                <p className="text-sm text-muted-foreground pl-9">
                  {t('settings.skills.guide_example_simple_desc')}
                </p>
                <CodeBlock>{SKILL_SIMPLE_EXAMPLE}</CodeBlock>
              </section>

              {/* Advisory example */}
              <section className="space-y-3">
                <SectionHeader
                  icon={<Sparkles className="h-4 w-4 text-amber-500" />}
                  iconBg="bg-amber-500/10"
                  title={t('settings.skills.guide_example_advisory_title')}
                />
                <p className="text-sm text-muted-foreground pl-9">
                  {t('settings.skills.guide_example_advisory_desc')}
                </p>
                <CodeBlock>{SKILL_ADVISORY_EXAMPLE}</CodeBlock>
              </section>

              {/* Directory structure */}
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
                  <div className="text-foreground font-medium">mon-skill/</div>
                  <div className="pl-5 text-foreground">
                    SKILL.md{' '}
                    <span className="text-muted-foreground/50 font-sans">
                      — {t('settings.skills.guide_struct_skillmd')}
                    </span>
                  </div>
                  <div className="pl-5 text-muted-foreground">
                    references/{' '}
                    <span className="text-muted-foreground/50 font-sans">
                      — {t('settings.skills.guide_struct_references')}
                    </span>
                  </div>
                  <div className="pl-5 text-muted-foreground">
                    scripts/{' '}
                    <span className="text-muted-foreground/50 font-sans">
                      — {t('settings.skills.guide_struct_scripts')}
                    </span>
                  </div>
                  <div className="pl-5 text-muted-foreground">
                    assets/{' '}
                    <span className="text-muted-foreground/50 font-sans">
                      — {t('settings.skills.guide_struct_assets')}
                    </span>
                  </div>
                  <div className="pl-5 text-muted-foreground">
                    translations.json{' '}
                    <span className="text-muted-foreground/50 font-sans">
                      — {t('settings.skills.guide_struct_translations')}
                    </span>
                  </div>
                </div>
              </section>

              {/* How to use references, scripts, assets */}
              <section className="space-y-3">
                <SectionHeader
                  icon={<Code2 className="h-4 w-4 text-teal-500" />}
                  iconBg="bg-teal-500/10"
                  title={t('settings.skills.guide_resources_title')}
                />
                <div className="space-y-3 pl-9">
                  {(['references', 'scripts', 'assets'] as const).map(res => (
                    <div
                      key={res}
                      className="rounded-lg border p-3 bg-card/50 hover:bg-card transition-colors"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <code className="text-xs font-mono font-semibold text-primary/80">
                          {res}/
                        </code>
                      </div>
                      <p className="text-xs text-muted-foreground leading-relaxed">
                        {t(`settings.skills.guide_resource_${res}_desc`)}
                      </p>
                      <p className="text-xs text-muted-foreground/60 mt-1 italic">
                        {t(`settings.skills.guide_resource_${res}_usage`)}
                      </p>
                    </div>
                  ))}
                </div>
              </section>

              {/* Import process */}
              <section className="rounded-xl border bg-blue-500/5 p-5 space-y-2">
                <div className="flex items-center gap-2">
                  <FolderOpen className="h-4 w-4 text-blue-500 shrink-0" />
                  <h3 className="font-semibold text-sm">
                    {t('settings.skills.guide_import_title')}
                  </h3>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {t('settings.skills.guide_import_body')}
                </p>
              </section>
            </div>
          </TabsContent>

          {/* ═══════════════════ TAB 3: Advanced ═══════════════════ */}
          <TabsContent value="advanced">
            <div className="space-y-6">
              {/* Plan template */}
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

                {/* Step fields legend */}
                <div className="rounded-xl bg-muted/40 border p-4 space-y-2">
                  <p className="text-xs font-semibold text-foreground/70 mb-2">
                    {t('settings.skills.guide_modal_plan_fields_title')}
                  </p>
                  <div className="grid grid-cols-1 gap-1.5 text-xs">
                    {(
                      [
                        'step_id',
                        'agent_name',
                        'tool_name',
                        'parameters',
                        'depends_on',
                        'step_type',
                      ] as const
                    ).map(key => (
                      <div key={key} className="flex gap-2">
                        <code className="shrink-0 font-mono text-primary/80 w-24">{key}</code>
                        <span className="text-muted-foreground">
                          {t(`settings.skills.guide_modal_plan_field_${key}`)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Auto-trigger explanation */}
                <div className="rounded-xl border bg-orange-500/5 p-4 space-y-1">
                  <p className="text-xs font-semibold text-foreground/70">
                    {t('settings.skills.guide_autotrigger_title')}
                  </p>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {t('settings.skills.guide_autotrigger_body')}
                  </p>
                </div>
              </section>

              {/* Complete Tools Reference */}
              <section className="space-y-3">
                <SectionHeader
                  icon={<Puzzle className="h-4 w-4 text-blue-500" />}
                  iconBg="bg-blue-500/10"
                  title={t('settings.skills.guide_tools_title')}
                />
                <p className="text-sm text-muted-foreground pl-9">
                  {t('settings.skills.guide_tools_intro')}
                </p>

                <Accordion type="multiple" className="w-full">
                  {TOOL_CATALOGUE.map(cat => (
                    <AccordionItem key={cat.category} value={cat.category} className="border-none">
                      <AccordionTrigger className="py-2 px-3 rounded-lg hover:no-underline hover:bg-muted/50 text-sm font-semibold">
                        {t(`settings.skills.guide_cat_${cat.category}`)}
                        <span className="text-xs font-normal text-muted-foreground ml-2">
                          ({cat.agents.length} agents)
                        </span>
                      </AccordionTrigger>
                      <AccordionContent className="pt-0 pb-2">
                        <div className="space-y-4 pl-2">
                          {cat.agents.map(agent => (
                            <AgentToolsBlock key={agent.agent} agent={agent} t={t} />
                          ))}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  ))}
                </Accordion>

                <p className="text-xs text-muted-foreground/60 italic pl-2">
                  {t('settings.skills.guide_tools_note')}
                </p>
              </section>

              {/* Scripts */}
              <section className="space-y-3">
                <SectionHeader
                  icon={<Terminal className="h-4 w-4 text-green-500" />}
                  iconBg="bg-green-500/10"
                  title={t('settings.skills.guide_scripts_title')}
                />
                <p className="text-sm text-muted-foreground leading-relaxed pl-9">
                  {t('settings.skills.guide_scripts_body')}
                </p>
                <CodeBlock>{SCRIPT_EXAMPLE}</CodeBlock>
                <div className="rounded-xl bg-muted/40 border p-4 space-y-1.5 text-xs">
                  <p className="font-semibold text-foreground/70">
                    {t('settings.skills.guide_scripts_rules_title')}
                  </p>
                  {[1, 2, 3, 4].map(i => (
                    <p key={i} className="text-muted-foreground flex gap-2">
                      <span className="text-muted-foreground/50 shrink-0">•</span>
                      {t(`settings.skills.guide_scripts_rule_${i}`)}
                    </p>
                  ))}
                </div>
              </section>

              {/* Skill tools (activate, read_resource, run_script) */}
              <section className="space-y-3">
                <SectionHeader
                  icon={<Code2 className="h-4 w-4 text-teal-500" />}
                  iconBg="bg-teal-500/10"
                  title={t('settings.skills.guide_skill_tools_title')}
                />
                <p className="text-sm text-muted-foreground leading-relaxed pl-9">
                  {t('settings.skills.guide_skill_tools_body')}
                </p>
                <div className="rounded-xl bg-muted/40 border p-4 space-y-3 text-xs">
                  {(
                    [
                      ['activate_skill_tool', 'guide_skilltool_activate'],
                      ['read_skill_resource', 'guide_skilltool_read'],
                      ['run_skill_script', 'guide_skilltool_run'],
                    ] as const
                  ).map(([tool, key]) => (
                    <div key={tool} className="flex gap-2 items-start">
                      <code className="shrink-0 font-mono text-primary/80 min-w-[160px]">
                        {tool}
                      </code>
                      <span className="text-muted-foreground">
                        {t(`settings.skills.${key}`)}
                      </span>
                    </div>
                  ))}
                </div>
              </section>

              {/* Compatibility banner */}
              <CompatBanner t={t} />
            </div>
          </TabsContent>
        </Tabs>
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

function AgentToolsBlock({
  agent,
  t,
}: {
  agent: AgentDef;
  t: (key: string) => string;
}) {
  return (
    <div className="rounded-lg border bg-card/50 p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <code className="font-mono text-xs text-blue-600 dark:text-blue-400 font-semibold">
          {agent.agent}
        </code>
        <span className="text-xs text-muted-foreground">— {agent.label}</span>
        {agent.oauth && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400">
            Connector
          </span>
        )}
      </div>
      <div className="space-y-2">
        {agent.tools.map(tool => (
          <div key={tool.name} className="pl-2 border-l-2 border-primary/20 ml-1">
            <div className="flex items-center gap-2 mb-1">
              <code className="font-mono text-xs text-foreground/70">{tool.name}</code>
              <span className="text-[10px] text-muted-foreground">
                {t(`settings.skills.${tool.desc}`)}
              </span>
            </div>
            {tool.params.length > 0 && (
              <div className="grid grid-cols-1 gap-0.5 text-[11px] ml-2">
                {tool.params.map(p => (
                  <div key={p.name} className="flex gap-1.5 items-baseline">
                    <code className="font-mono text-primary/60 shrink-0">
                      {p.name}
                      {p.required && <span className="text-red-400">*</span>}
                    </code>
                    <span className="text-muted-foreground/50 shrink-0">({p.type})</span>
                    <span className="text-muted-foreground/70 truncate">
                      {t(`settings.skills.${p.desc}`)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function CompatBanner({ t }: { t: (key: string) => string }) {
  return (
    <section className="rounded-xl border bg-primary/5 p-5 space-y-2.5">
      <div className="flex items-center gap-2">
        <Globe className="h-4 w-4 text-primary shrink-0" />
        <h3 className="font-semibold text-sm">{t('settings.skills.guide_modal_compat_title')}</h3>
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
  );
}
