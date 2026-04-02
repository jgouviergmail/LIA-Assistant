/**
 * PsycheEducation — comprehensive interactive guide to the Psyche Engine.
 *
 * Explains the 5-layer architecture, PAD mood space, emotions, Big Five traits,
 * relationship stages, drives, and user settings with visual aids.
 *
 * Phase: evolution — Psyche Engine (Iteration 3)
 * Created: 2026-04-01
 */

'use client';

import React from 'react';

import { Fingerprint, Flame, Gauge, Handshake, Heart, Layers, SlidersHorizontal } from 'lucide-react';

import { MOOD_COLORS } from '@/lib/psyche-colors';
import type { MoodLabel } from '@/types/psyche';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';

interface PsycheEducationProps {
  lng: Language;
}

export function PsycheEducation({ lng }: PsycheEducationProps) {
  const { t } = useTranslation(lng, 'translation');

  return (
    <Accordion type="single" collapsible className="w-full space-y-1">
      {/* ================================================================
          OVERVIEW — How it works
          ================================================================ */}
      <AccordionItem value="overview" className="border-b-0">
        <AccordionTrigger className="py-2 text-sm hover:no-underline">
          <span className="flex items-center gap-2">
            <Layers className="h-3.5 w-3.5 text-muted-foreground" />
            {t('psyche.education.overview.title', 'How it works')}
          </span>
        </AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 text-xs text-muted-foreground leading-relaxed">
            <p>
              {t(
                'psyche.education.overview.intro',
                "The Psyche Engine gives your assistant a dynamic psychological state that evolves with every interaction. Instead of a fixed personality, the assistant now has moods that fluctuate, emotions that fire and decay, a relationship that deepens over time, and personality traits that shape how it reacts emotionally.",
              )}
            </p>
            <p>
              {t(
                'psyche.education.overview.principle',
                'Design principle: the assistant never says "I\'m feeling happy" — instead, its vocabulary becomes warmer, its energy higher, its suggestions more adventurous. You perceive a living personality without explicit emotional statements.',
              )}
            </p>

            {/* 5-layer diagram */}
            <div className="bg-muted/50 rounded-lg p-3 font-mono text-[10px] space-y-1">
              <div className="border border-border/50 rounded px-2 py-1 text-center">
                {t('psyche.education.overview.layer5', 'Layer 5 — Drives & Self-Efficacy (per session)')}
              </div>
              <div className="border border-border/50 rounded px-2 py-1 text-center">
                {t('psyche.education.overview.layer4', 'Layer 4 — Relationship (weeks/months)')}
              </div>
              <div className="border border-border/50 rounded px-2 py-1 text-center">
                {t('psyche.education.overview.layer3', 'Layer 3 — 16 Emotions (minutes)')}
              </div>
              <div className="border border-border/50 rounded px-2 py-1 text-center">
                {t('psyche.education.overview.layer2', 'Layer 2 — Mood in PAD space (hours)')}
              </div>
              <div className="border border-border/50 rounded px-2 py-1 text-center bg-primary/10">
                {t('psyche.education.overview.layer1', 'Layer 1 — Personality / Big Five (permanent)')}
              </div>
            </div>
            <p className="text-[10px] italic">
              {t(
                'psyche.education.overview.layers_note',
                'Each layer operates on a different timescale. Lower layers change slowly, upper layers change with every message.',
              )}
            </p>
          </div>
        </AccordionContent>
      </AccordionItem>

      {/* ================================================================
          PERSONALITY — Layer 1: Big Five (permanent)
          ================================================================ */}
      <AccordionItem value="traits" className="border-b-0">
        <AccordionTrigger className="py-2 text-sm hover:no-underline">
          <span className="flex items-center gap-2">
            <Fingerprint className="h-3.5 w-3.5 text-muted-foreground" />
            {t('psyche.education.traits.title', 'Personality Traits')}
          </span>
        </AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 text-xs text-muted-foreground leading-relaxed">
            <p>
              {t(
                'psyche.education.traits.intro',
                "Each personality has Big Five traits that actively shape emotional behavior — not just the baseline mood, but how the assistant reacts, recovers, and empathizes.",
              )}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px] border-collapse">
                <thead>
                  <tr className="border-b border-border/30">
                    <th className="text-left py-1 pr-2 font-medium text-foreground">{t('psyche.education.traits.trait', 'Trait')}</th>
                    <th className="text-left py-1 pr-2 font-medium text-foreground">{t('psyche.education.traits.modulates', 'Modulates')}</th>
                    <th className="text-left py-1 font-medium text-foreground">{t('psyche.education.traits.effect', 'Effect')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/20">
                  <tr>
                    <td className="py-1.5 pr-2 font-medium">{t('psyche.education.traits.neuroticism', 'Neuroticism')}</td>
                    <td className="py-1.5 pr-2">{t('psyche.education.traits.neuroticism_mod', 'Emotional reactivity')}</td>
                    <td className="py-1.5">{t('psyche.education.traits.neuroticism_effect', 'High = emotions hit harder. Low = stoic, muted reactions.')}</td>
                  </tr>
                  <tr>
                    <td className="py-1.5 pr-2 font-medium">{t('psyche.education.traits.agreeableness', 'Agreeableness')}</td>
                    <td className="py-1.5 pr-2">{t('psyche.education.traits.agreeableness_mod', 'Empathy & resilience')}</td>
                    <td className="py-1.5">{t('psyche.education.traits.agreeableness_effect', 'High = mirrors your emotions strongly. Low = resistant, pulls back to neutral when negative.')}</td>
                  </tr>
                  <tr>
                    <td className="py-1.5 pr-2 font-medium">{t('psyche.education.traits.conscientiousness', 'Conscientiousness')}</td>
                    <td className="py-1.5 pr-2">{t('psyche.education.traits.conscientiousness_mod', 'Recovery speed')}</td>
                    <td className="py-1.5">{t('psyche.education.traits.conscientiousness_effect', 'High = returns to baseline quickly. Low = moods linger.')}</td>
                  </tr>
                  <tr>
                    <td className="py-1.5 pr-2 font-medium">{t('psyche.education.traits.openness', 'Openness')}</td>
                    <td className="py-1.5 pr-2">{t('psyche.education.traits.openness_mod', 'Mood baseline')}</td>
                    <td className="py-1.5">{t('psyche.education.traits.openness_effect', 'High = curious baseline, more exploratory.')}</td>
                  </tr>
                  <tr>
                    <td className="py-1.5 pr-2 font-medium">{t('psyche.education.traits.extraversion', 'Extraversion')}</td>
                    <td className="py-1.5 pr-2">{t('psyche.education.traits.extraversion_mod', 'Mood baseline')}</td>
                    <td className="py-1.5">{t('psyche.education.traits.extraversion_effect', 'High = positive, warm baseline. Low = reserved, quieter.')}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>

      {/* ================================================================
          MOOD — Layer 2: PAD space (hours)
          ================================================================ */}
      <AccordionItem value="mood" className="border-b-0">
        <AccordionTrigger className="py-2 text-sm hover:no-underline">
          <span className="flex items-center gap-2">
            <Gauge className="h-3.5 w-3.5 text-muted-foreground" />
            {t('psyche.education.mood.title', 'Mood (PAD)')}
          </span>
        </AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 text-xs text-muted-foreground leading-relaxed">
            <p>
              {t(
                'psyche.education.mood.description',
                "The assistant's mood is modeled in a 3D space: Pleasure (positive/negative), Arousal (energy level), and Dominance (sense of control). These three axes combine to produce one of 14 distinct moods.",
              )}
            </p>

            {/* PAD axes explanation */}
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-sky-500/10 rounded-md p-2 text-center">
                <div className="font-bold text-sky-500 text-sm">P</div>
                <div className="text-[10px]">{t('psyche.education.mood.pleasure', 'Pleasure')}</div>
                <div className="text-[9px] mt-1">-1 = {t('psyche.education.mood.pleasure_neg', 'unhappy')}</div>
                <div className="text-[9px]">+1 = {t('psyche.education.mood.pleasure_pos', 'happy')}</div>
              </div>
              <div className="bg-amber-500/10 rounded-md p-2 text-center">
                <div className="font-bold text-amber-500 text-sm">A</div>
                <div className="text-[10px]">{t('psyche.education.mood.arousal', 'Arousal')}</div>
                <div className="text-[9px] mt-1">-1 = {t('psyche.education.mood.arousal_neg', 'calm')}</div>
                <div className="text-[9px]">+1 = {t('psyche.education.mood.arousal_pos', 'energized')}</div>
              </div>
              <div className="bg-violet-500/10 rounded-md p-2 text-center">
                <div className="font-bold text-violet-500 text-sm">D</div>
                <div className="text-[10px]">{t('psyche.education.mood.dominance', 'Dominance')}</div>
                <div className="text-[9px] mt-1">-1 = {t('psyche.education.mood.dominance_neg', 'submissive')}</div>
                <div className="text-[9px]">+1 = {t('psyche.education.mood.dominance_pos', 'assertive')}</div>
              </div>
            </div>

            {/* Mood descriptions table */}
            <p className="font-medium text-foreground text-xs">
              {t('psyche.education.mood.table_title', 'Mood profiles:')}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px] border-collapse">
                <thead>
                  <tr className="border-b border-border/30">
                    <th className="text-left py-1 pr-2 font-medium text-foreground">{t('psyche.education.mood.col_mood', 'Mood')}</th>
                    <th className="text-left py-1 pr-2 font-medium text-foreground">PAD</th>
                    <th className="text-left py-1 font-medium text-foreground">{t('psyche.education.mood.col_influence', 'Behavioral influence')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/20">
                  {([
                    ['serene', '+P −A +D'],
                    ['curious', '+P +A =D'],
                    ['energized', '+P +A +D'],
                    ['playful', '+P +A =D'],
                    ['reflective', '+P −A +D'],
                    ['content', '+P −A −D'],
                    ['tender', '+P −A −D'],
                    ['determined', '+P +A ++D'],
                    ['neutral', '=P =A =D'],
                    ['agitated', '−P +A −D'],
                    ['melancholic', '−P −A −D'],
                    ['defiant', '−P +A +D'],
                    ['resigned', '−P −A +D'],
                    ['overwhelmed', '=P ++A −−D'],
                  ] as const).map(([mood, pad]) => {
                    const cfg = MOOD_COLORS[mood as MoodLabel];
                    return (
                      <tr key={mood}>
                        <td className="py-1 pr-2 font-medium whitespace-nowrap">
                          <span className="mr-1">{cfg?.icon}</span>
                          {t(`psyche.moods.${mood}`, mood)}
                        </td>
                        <td className="py-1 pr-2 font-mono text-muted-foreground whitespace-nowrap">{pad}</td>
                        <td className="py-1">{t(`psyche.education.mood.directive_${mood}`, '')}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* How mood changes */}
            <p className="font-medium text-foreground text-xs">
              {t('psyche.education.mood.dynamics_title', 'How mood changes:')}
            </p>
            <ul className="list-disc list-inside space-y-1 text-[11px]">
              <li>{t('psyche.education.mood.decay', 'Decay: without stimulus, mood drifts back to the personality baseline. Speed depends on Conscientiousness and the Stability setting.')}</li>
              <li>{t('psyche.education.mood.emotion_push', 'Emotion push: each emotion has a direction in PAD space. When triggered, it pushes the mood.')}</li>
              <li>{t('psyche.education.mood.contagion', 'Contagion: the detected emotional state of the user pulls the mood (strength depends on Agreeableness).')}</li>
              <li>{t('psyche.education.mood.counter_reg', 'Counter-regulation: low-Agreeableness personalities resist negativity and pull back toward neutral.')}</li>
              <li>{t('psyche.education.mood.circadian', 'Circadian: slight midday pleasure boost, midnight dip.')}</li>
              <li>{t('psyche.education.mood.inertia', 'Inertia: the longer the mood stays in one state, the more resistant it becomes to change.')}</li>
            </ul>
          </div>
        </AccordionContent>
      </AccordionItem>

      {/* ================================================================
          EMOTIONS — 16 types
          ================================================================ */}
      <AccordionItem value="emotions" className="border-b-0">
        <AccordionTrigger className="py-2 text-sm hover:no-underline">
          <span className="flex items-center gap-2">
            <Heart className="h-3.5 w-3.5 text-muted-foreground" />
            {t('psyche.education.emotions.title', 'Emotions')}
          </span>
        </AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 text-xs text-muted-foreground leading-relaxed">
            <p>
              {t(
                'psyche.education.emotions.intro',
                'The assistant can experience up to 7 simultaneous emotions from a palette of 16. Each emotion has an intensity (0-100%) that decays over time and pushes the mood in a specific direction.',
              )}
            </p>

            {/* Emotion table */}
            <div className="overflow-x-auto">
              <table className="w-full text-[10px] border-collapse">
                <thead>
                  <tr className="border-b border-border/30">
                    <th className="text-left py-1 pr-2 font-medium text-foreground">{t('psyche.education.emotions.col_emotion', 'Emotion')}</th>
                    <th className="text-left py-1 pr-2 font-medium text-foreground">{t('psyche.education.emotions.col_type', 'Type')}</th>
                    <th className="text-left py-1 pr-2 font-medium text-foreground">PAD</th>
                    <th className="text-left py-1 font-medium text-foreground">{t('psyche.education.emotions.col_influence', 'Behavioral influence')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/20">
                  {([
                    ['joy', 'positive', '+P +A +D'],
                    ['gratitude', 'positive', '+P +A −D'],
                    ['pride', 'positive', '+P +A +D'],
                    ['amusement', 'positive', '+P +A +D'],
                    ['enthusiasm', 'positive', '++P ++A +D'],
                    ['tenderness', 'positive', '+P −A −D'],
                    ['curiosity', 'neutral', '+P +A +D'],
                    ['serenity', 'neutral', '+P −A +D'],
                    ['surprise', 'neutral', '+P ++A −D'],
                    ['empathy', 'neutral', '+P +A −D'],
                    ['confusion', 'neutral', '−P +A −D'],
                    ['determination', 'neutral', '+P +A ++D'],
                    ['frustration', 'negative', '−P +A −D'],
                    ['concern', 'negative', '−P +A +D'],
                    ['melancholy', 'negative', '−P −A −D'],
                    ['disappointment', 'negative', '−P −A −D'],
                  ] as const).map(([emotion, type, pad]) => (
                    <tr key={emotion}>
                      <td className="py-1 pr-2 font-medium whitespace-nowrap">
                        {t(`psyche.emotions.${emotion}`, emotion)}
                      </td>
                      <td className={cn('py-1 pr-2 whitespace-nowrap', {
                        'text-emerald-500': type === 'positive',
                        'text-red-400': type === 'negative',
                        'text-muted-foreground': type === 'neutral',
                      })}>
                        {t(`psyche.education.emotions.${type}`, type).replace(':', '')}
                      </td>
                      <td className="py-1 pr-2 font-mono text-muted-foreground whitespace-nowrap">{pad}</td>
                      <td className="py-1">{t(`psyche.education.emotions.directive_${emotion}`, '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Key mechanics */}
            <p className="font-medium text-foreground text-xs">
              {t('psyche.education.emotions.mechanics_title', 'Key mechanics:')}
            </p>
            <ul className="list-disc list-inside space-y-1 text-[11px]">
              <li>{t('psyche.education.emotions.cross_suppression', 'Cross-suppression: a positive emotion actively dampens negative ones by 30%, and vice versa. A genuine compliment reduces worry.')}</li>
              <li>{t('psyche.education.emotions.blend', 'Blend update: emotions can increase AND decrease. A weaker repetition of the same emotion lowers its intensity (no "sticky max" effect).')}</li>
              <li>{t('psyche.education.emotions.reactivity', 'Reactivity: Neuroticism amplifies emotion intensity (high N = very reactive, low N = stoic).')}</li>
              <li>{t('psyche.education.emotions.decay', 'Decay: all emotions lose intensity over time and disappear below 5%.')}</li>
            </ul>
          </div>
        </AccordionContent>
      </AccordionItem>

      {/* ================================================================
          RELATIONSHIP — 4 stages
          ================================================================ */}
      <AccordionItem value="relationship" className="border-b-0">
        <AccordionTrigger className="py-2 text-sm hover:no-underline">
          <span className="flex items-center gap-2">
            <Handshake className="h-3.5 w-3.5 text-muted-foreground" />
            {t('psyche.education.relationship.title', 'Relationship')}
          </span>
        </AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 text-xs text-muted-foreground leading-relaxed">
            <p>
              {t(
                'psyche.education.relationship.intro',
                'The relationship between you and your assistant evolves through 4 stages. Progress is one-way — depth never decreases, like a real relationship maturing over time.',
              )}
            </p>

            {/* Stage progression */}
            <div className="flex items-center gap-1 text-[10px] font-mono overflow-x-auto py-1">
              {['ORIENTATION', 'EXPLORATORY', 'AFFECTIVE', 'STABLE'].map((stage, i) => (
                <React.Fragment key={stage}>
                  <div className="bg-muted rounded-md px-2 py-1 whitespace-nowrap text-center">
                    <div className="font-medium text-foreground">{t(`psyche.stages.${stage}`, stage)}</div>
                  </div>
                  {i < 3 && <span className="text-muted-foreground">→</span>}
                </React.Fragment>
              ))}
            </div>

            <ul className="list-disc list-inside space-y-1 text-[11px]">
              <li><strong>{t('psyche.stages.ORIENTATION', 'Orientation')}:</strong> {t('psyche.education.relationship.orientation', 'Professional, measured. No assumptions of familiarity.')}</li>
              <li><strong>{t('psyche.stages.EXPLORATORY', 'Exploratory')}:</strong> {t('psyche.education.relationship.exploratory', 'Shows personality more freely. References past exchanges.')}</li>
              <li><strong>{t('psyche.stages.AFFECTIVE', 'Affective')}:</strong> {t('psyche.education.relationship.affective', 'Personal and direct. Uses humor. Remembers your preferences.')}</li>
              <li><strong>{t('psyche.stages.STABLE', 'Stable')}:</strong> {t('psyche.education.relationship.stable', 'Trusted companion. Candid, challenges constructively when needed.')}</li>
            </ul>

            <p className="font-medium text-foreground text-xs">
              {t('psyche.education.relationship.metrics_title', 'Tracked metrics:')}
            </p>
            <ul className="list-disc list-inside space-y-1 text-[11px]">
              <li><strong>{t('psyche.depth', 'Depth')}:</strong> {t('psyche.education.relationship.depth_desc', 'Grows logarithmically with each quality interaction. Never decreases.')}</li>
              <li><strong>{t('psyche.warmth', 'Warmth')}:</strong> {t('psyche.education.relationship.warmth_desc', 'Active warmth that decays during absence but recovers quickly on contact.')}</li>
              <li><strong>{t('psyche.trust', 'Trust')}:</strong> {t('psyche.education.relationship.trust_desc', 'Bayesian accumulation from interaction quality. Conflict resolution (rupture-repair) gives bonus trust.')}</li>
            </ul>
          </div>
        </AccordionContent>
      </AccordionItem>

      {/* ================================================================
          DRIVES — Curiosity, Engagement, Self-Efficacy
          ================================================================ */}
      <AccordionItem value="drives" className="border-b-0">
        <AccordionTrigger className="py-2 text-sm hover:no-underline">
          <span className="flex items-center gap-2">
            <Flame className="h-3.5 w-3.5 text-muted-foreground" />
            {t('psyche.education.drives.title', 'Drives')}
          </span>
        </AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 text-xs text-muted-foreground leading-relaxed">
            <p>
              {t(
                'psyche.education.drives.intro',
                'Drives are internal motivations that evolve with each interaction. They influence how proactive, thorough, and exploratory the assistant is.',
              )}
            </p>

            <div className="overflow-x-auto">
              <table className="w-full text-[10px] border-collapse">
                <thead>
                  <tr className="border-b border-border/30">
                    <th className="text-left py-1 pr-2 font-medium text-foreground">{t('psyche.education.drives.col_drive', 'Drive')}</th>
                    <th className="text-left py-1 pr-2 font-medium text-foreground">{t('psyche.education.drives.col_source', 'Fed by')}</th>
                    <th className="text-left py-1 font-medium text-foreground">{t('psyche.education.drives.col_effect', 'Effect when high')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/20">
                  <tr>
                    <td className="py-1.5 pr-2 font-medium">{t('psyche.curiosityDrive', 'Curiosity')}</td>
                    <td className="py-1.5 pr-2">{t('psyche.education.drives.curiosity_source', 'Interaction energy (arousal)')}</td>
                    <td className="py-1.5">{t('psyche.education.drives.curiosity_effect', 'Explores new angles, asks follow-up questions, suggests tangents.')}</td>
                  </tr>
                  <tr>
                    <td className="py-1.5 pr-2 font-medium">{t('psyche.history.engagement', 'Engagement')}</td>
                    <td className="py-1.5 pr-2">{t('psyche.education.drives.engagement_source', 'Interaction quality')}</td>
                    <td className="py-1.5">{t('psyche.education.drives.engagement_effect', 'More thorough and proactive. In flow — takes initiative.')}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p className="text-[11px]">
              {t(
                'psyche.education.drives.dynamics',
                'Both drives use a smooth moving average (20% new signal, 80% previous value). They never jump — they drift gradually toward the quality and energy of your exchanges.',
              )}
            </p>

            <p className="font-medium text-foreground text-xs">
              {t('psyche.education.drives.efficacy_title', 'Self-efficacy')}
            </p>
            <p className="text-[11px]">
              {t(
                'psyche.education.drives.efficacy_desc',
                'The assistant tracks its confidence across domains (planning, technical, emotional support, etc.). High confidence means bolder suggestions; low confidence means more caution and thoroughness. Updated after each interaction based on quality feedback.',
              )}
            </p>
          </div>
        </AccordionContent>
      </AccordionItem>

      {/* ================================================================
          SETTINGS — User controls
          ================================================================ */}
      <AccordionItem value="settings-explain" className="border-b-0">
        <AccordionTrigger className="py-2 text-sm hover:no-underline">
          <span className="flex items-center gap-2">
            <SlidersHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
            {t('psyche.education.settings_explanation.title', 'Expressivity & Stability')}
          </span>
        </AccordionTrigger>
        <AccordionContent>
          <div className="space-y-3 text-xs text-muted-foreground leading-relaxed">
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-muted/50 rounded-lg p-2.5">
                <div className="font-medium text-foreground text-[11px] mb-1">
                  {t('psyche.sensitivity', 'Expressiveness')}
                </div>
                <ul className="text-[10px] space-y-0.5">
                  <li>0% → {t('psyche.education.settings_explanation.expr_low', 'Stoic: emotions barely influence output')}</li>
                  <li>50% → {t('psyche.education.settings_explanation.expr_mid', 'Moderate: subtle tonal shifts')}</li>
                  <li>100% → {t('psyche.education.settings_explanation.expr_high', 'Highly expressive: strong emotional coloring')}</li>
                </ul>
              </div>
              <div className="bg-muted/50 rounded-lg p-2.5">
                <div className="font-medium text-foreground text-[11px] mb-1">
                  {t('psyche.stability', 'Mood Stability')}
                </div>
                <ul className="text-[10px] space-y-0.5">
                  <li>0% → {t('psyche.education.settings_explanation.stab_low', 'Volatile: mood swings with every message')}</li>
                  <li>50% → {t('psyche.education.settings_explanation.stab_mid', 'Normal: shifts over multiple messages')}</li>
                  <li>100% → {t('psyche.education.settings_explanation.stab_high', 'Very stable: resistant to change')}</li>
                </ul>
              </div>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
