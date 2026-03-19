'use client';

import { Sparkles, Link2, MessageCircleHeart, Brain, Bell, Terminal, Heart } from 'lucide-react';

export type IllustrationType =
  | 'welcome'
  | 'connectors'
  | 'personality'
  | 'memory'
  | 'interests'
  | 'notifications'
  | 'examples';

interface OnboardingIllustrationProps {
  type: IllustrationType;
}

/**
 * SVG illustrations for onboarding pages.
 *
 * Uses geometric compositions with primary colors and Lucide icons as accents.
 */
export function OnboardingIllustration({ type }: OnboardingIllustrationProps) {
  const baseClasses = 'w-32 h-32 sm:w-40 sm:h-40 md:w-48 md:h-48';

  switch (type) {
    case 'welcome':
      return (
        <div className={`${baseClasses} relative`}>
          {/* Background circle */}
          <div className="absolute inset-0 rounded-full bg-gradient-to-br from-primary/20 to-primary/5" />
          {/* Inner decorative circles */}
          <div className="absolute inset-4 rounded-full bg-gradient-to-tr from-primary/30 to-transparent" />
          <div className="absolute inset-8 rounded-full bg-gradient-to-br from-primary/10 to-primary/40" />
          {/* Center icon */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="p-4 rounded-2xl bg-primary/20 backdrop-blur-sm">
              <Sparkles className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 text-primary" />
            </div>
          </div>
          {/* Floating decorations */}
          <div className="absolute top-2 right-4 w-3 h-3 rounded-full bg-primary/60 animate-pulse" />
          <div
            className="absolute bottom-4 left-2 w-2 h-2 rounded-full bg-primary/40 animate-pulse"
            style={{ animationDelay: '0.5s' }}
          />
          <div
            className="absolute top-1/4 left-0 w-2 h-2 rounded-full bg-primary/50 animate-pulse"
            style={{ animationDelay: '1s' }}
          />
        </div>
      );

    case 'connectors':
      return (
        <div className={`${baseClasses} relative`}>
          {/* Background */}
          <div className="absolute inset-0 rounded-full bg-gradient-to-br from-blue-500/20 to-blue-500/5" />
          {/* Connected nodes visualization */}
          <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100">
            {/* Connection lines */}
            <line
              x1="50"
              y1="30"
              x2="25"
              y2="60"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-primary/40"
            />
            <line
              x1="50"
              y1="30"
              x2="75"
              y2="60"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-primary/40"
            />
            <line
              x1="25"
              y1="60"
              x2="50"
              y2="80"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-primary/40"
            />
            <line
              x1="75"
              y1="60"
              x2="50"
              y2="80"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-primary/40"
            />
            {/* Nodes */}
            <circle cx="50" cy="30" r="8" className="fill-primary/30" />
            <circle cx="25" cy="60" r="6" className="fill-primary/40" />
            <circle cx="75" cy="60" r="6" className="fill-primary/40" />
            <circle cx="50" cy="80" r="5" className="fill-primary/50" />
          </svg>
          {/* Center icon */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="p-3 rounded-xl bg-blue-500/20">
              <Link2 className="w-10 h-10 sm:w-12 sm:h-12 md:w-14 md:h-14 text-blue-600 dark:text-blue-400" />
            </div>
          </div>
        </div>
      );

    case 'personality':
      return (
        <div className={`${baseClasses} relative`}>
          {/* Background */}
          <div className="absolute inset-0 rounded-full bg-gradient-to-br from-pink-500/20 to-purple-500/10" />
          {/* Speech bubbles */}
          <div className="absolute top-4 left-4 w-8 h-6 rounded-lg bg-pink-400/30 transform -rotate-12" />
          <div className="absolute top-8 right-6 w-6 h-5 rounded-lg bg-purple-400/30 transform rotate-6" />
          <div className="absolute bottom-6 left-8 w-7 h-5 rounded-lg bg-pink-300/30 transform rotate-3" />
          {/* Center icon */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="p-4 rounded-2xl bg-gradient-to-br from-pink-500/20 to-purple-500/20">
              <MessageCircleHeart className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 text-pink-600 dark:text-pink-400" />
            </div>
          </div>
        </div>
      );

    case 'memory':
      return (
        <div className={`${baseClasses} relative`}>
          {/* Background */}
          <div className="absolute inset-0 rounded-full bg-gradient-to-br from-emerald-500/20 to-teal-500/10" />
          {/* Neural network lines */}
          <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100">
            {/* Synaptic connections */}
            <path
              d="M30 40 Q50 20 70 40"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-emerald-500/30"
            />
            <path
              d="M20 55 Q50 45 80 55"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-teal-500/30"
            />
            <path
              d="M35 70 Q50 60 65 70"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-emerald-400/30"
            />
            {/* Nodes */}
            <circle cx="30" cy="40" r="3" className="fill-emerald-400/50" />
            <circle cx="70" cy="40" r="3" className="fill-teal-400/50" />
            <circle cx="20" cy="55" r="2" className="fill-emerald-500/40" />
            <circle cx="80" cy="55" r="2" className="fill-teal-500/40" />
          </svg>
          {/* Center icon */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="p-4 rounded-2xl bg-emerald-500/20">
              <Brain className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 text-emerald-600 dark:text-emerald-400" />
            </div>
          </div>
        </div>
      );

    case 'interests':
      return (
        <div className={`${baseClasses} relative`}>
          {/* Background */}
          <div className="absolute inset-0 rounded-full bg-gradient-to-br from-rose-500/20 to-pink-500/10" />
          {/* Floating interest bubbles */}
          <div className="absolute top-4 left-6 w-6 h-6 rounded-full bg-purple-400/30 animate-pulse" />
          <div
            className="absolute top-8 right-4 w-5 h-5 rounded-full bg-rose-400/30 animate-pulse"
            style={{ animationDelay: '0.3s' }}
          />
          <div
            className="absolute bottom-6 left-4 w-4 h-4 rounded-full bg-pink-400/30 animate-pulse"
            style={{ animationDelay: '0.6s' }}
          />
          <div
            className="absolute bottom-4 right-6 w-5 h-5 rounded-full bg-orange-400/30 animate-pulse"
            style={{ animationDelay: '0.9s' }}
          />
          {/* Connecting lines */}
          <svg className="absolute inset-0 w-full h-full" viewBox="0 0 100 100">
            <path
              d="M30 25 Q50 50 70 25"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-rose-400/30"
            />
            <path
              d="M20 50 Q50 60 80 50"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-pink-400/30"
            />
            <path
              d="M30 75 Q50 55 70 75"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-rose-300/30"
            />
          </svg>
          {/* Center icon */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="p-4 rounded-2xl bg-gradient-to-br from-rose-500/20 to-pink-500/20">
              <Heart className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 text-rose-600 dark:text-rose-400" />
            </div>
          </div>
        </div>
      );

    case 'notifications':
      return (
        <div className={`${baseClasses} relative`}>
          {/* Background */}
          <div className="absolute inset-0 rounded-full bg-gradient-to-br from-amber-500/20 to-orange-500/10" />
          {/* Sound waves */}
          <div
            className="absolute inset-6 rounded-full border-2 border-amber-400/20 animate-ping"
            style={{ animationDuration: '2s' }}
          />
          <div
            className="absolute inset-10 rounded-full border-2 border-orange-400/30 animate-ping"
            style={{ animationDuration: '2s', animationDelay: '0.5s' }}
          />
          {/* Center icon */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="p-4 rounded-2xl bg-amber-500/20">
              <Bell className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 text-amber-600 dark:text-amber-400" />
            </div>
          </div>
          {/* Notification dot */}
          <div className="absolute top-1/4 right-1/4 w-4 h-4 rounded-full bg-red-500 border-2 border-background animate-bounce" />
        </div>
      );

    case 'examples':
      return (
        <div className={`${baseClasses} relative`}>
          {/* Background */}
          <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-slate-500/20 to-slate-600/10" />
          {/* Code lines decoration */}
          <div className="absolute top-6 left-6 right-6 space-y-2">
            <div className="h-2 bg-slate-400/20 rounded w-3/4" />
            <div className="h-2 bg-slate-400/15 rounded w-1/2" />
            <div className="h-2 bg-slate-400/10 rounded w-2/3" />
          </div>
          {/* Center icon */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="p-4 rounded-2xl bg-slate-500/20">
              <Terminal className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 text-slate-600 dark:text-slate-400" />
            </div>
          </div>
          {/* Cursor blink */}
          <div className="absolute bottom-8 left-8 w-3 h-5 bg-primary/60 animate-pulse" />
        </div>
      );

    default:
      return null;
  }
}
