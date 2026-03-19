import { useEffect, useRef } from 'react';
import { Message } from '@/types/chat';
import { ChatMessage } from './ChatMessage';
import { TypingIndicator } from './TypingIndicator';
import { MessageSquare } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { logger } from '@/lib/logger';

export interface ChatMessageListProps {
  messages: Message[];
  isTyping?: boolean;
}

export const ChatMessageList: React.FC<ChatMessageListProps> = ({ messages, isTyping = false }) => {
  const { t } = useTranslation();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const wasTypingRef = useRef(false);
  // Flag to cancel pending scroll-to-user if component unmounts during RAF
  const pendingScrollRef = useRef(false);

  // Auto-scroll behavior:
  // - Default: scroll to bottom (preserves original behavior for history load, new messages, etc.)
  // - When streaming ends: scroll to last user message aligned at top
  useEffect(() => {
    if (!isTyping && wasTypingRef.current) {
      // Streaming just ended: scroll to last user message aligned at top
      // Double RAF ensures the DOM is fully painted before scrolling
      pendingScrollRef.current = true;

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          // Check if scroll was cancelled (component unmounted or new effect triggered)
          if (!pendingScrollRef.current || !containerRef.current) return;

          // Find all user message wrappers and get the last one
          const userMessageWrappers = containerRef.current.querySelectorAll<HTMLElement>(
            '[data-message-role="user"]'
          );

          if (userMessageWrappers.length > 0) {
            const lastUserMessage = userMessageWrappers[userMessageWrappers.length - 1];
            // scroll-mt-8 (32px) matches container's pt-8 for visual alignment
            lastUserMessage.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }

          pendingScrollRef.current = false;
        });
      });
    } else {
      // All other cases: scroll to bottom (streaming follow, history load, etc.)
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }

    // Update previous state AFTER the condition check
    wasTypingRef.current = isTyping;

    // Cleanup: cancel pending scroll if effect re-runs or component unmounts
    return () => {
      pendingScrollRef.current = false;
    };
  }, [messages, isTyping]);

  // DEFENSIVE: Handle case where messages is not an array
  if (!Array.isArray(messages)) {
    // Log error without exposing message content (PII protection)
    logger.error('messages_invalid_type', undefined, {
      component: 'ChatMessageList',
      receivedType: typeof messages,
      isNull: messages === null,
      isUndefined: messages === undefined,
    });
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-destructive/20 backdrop-blur-sm">
          <MessageSquare className="h-10 w-10 text-destructive" />
        </div>
        <div className="bg-card/60 backdrop-blur-md rounded-xl px-6 py-4 border border-destructive/20">
          <h2 className="text-xl font-semibold mb-2 text-destructive">{t('chat.error.title')}</h2>
          <p className="text-sm text-muted-foreground max-w-md">{t('chat.error.message')}</p>
        </div>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-4">
        <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-primary/20 backdrop-blur-sm">
          <MessageSquare className="h-10 w-10 text-primary" />
        </div>
        <div className="bg-card/60 backdrop-blur-md rounded-xl px-6 py-4 border border-border/20">
          <h2 className="text-xl font-semibold mb-2">{t('chat.empty_state.title')}</h2>
          <p className="text-sm text-muted-foreground max-w-md">
            {t('chat.empty_state.description')}
          </p>
        </div>
      </div>
    );
  }

  return (
    // pt-8 (32px) provides top padding; scroll-mt-8 on messages must match for proper scroll alignment
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-2 pt-8 pb-6 mobile:px-6 scroll-smooth"
    >
      <div className="mobile:max-w-5xl mobile:mx-auto [&>*:first-child]:mt-2">
        {messages.map(message => (
          // scroll-mt-8 must match container's pt-8 for scrollIntoView alignment
          <div
            key={message.id}
            data-message-role={message.role}
            data-message-id={message.id}
            className="scroll-mt-8"
          >
            <ChatMessage message={message} isUser={message.role === 'user'} />
          </div>
        ))}

        {/* Typing indicator */}
        {isTyping && (
          <div className="flex gap-3 mb-4 flex-row-reverse">
            <div className="w-10 h-10 rounded-full flex items-center justify-center shadow-md bg-gradient-to-br from-primary to-primary/80 text-primary-foreground ring-2 ring-primary/30 font-bold text-sm">
              LIA
            </div>
            <div className="bg-card/60 backdrop-blur-md px-4 py-3 rounded-lg rounded-tr-none border border-border/20">
              <TypingIndicator />
            </div>
          </div>
        )}

        {/* Element for auto-scroll */}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
};
