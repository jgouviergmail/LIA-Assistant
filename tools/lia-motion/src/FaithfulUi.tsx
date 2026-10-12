import React, { type CSSProperties } from 'react';
import {
  Bell, BookOpen, Check, Circle, CircleHelp, ClipboardList, Copy, Download,
  GitBranch, LayoutDashboard, LogOut, Mail, MessageSquare, Mic, Moon, Plus,
  Radio, Scale, Search, Send, Settings, ThumbsDown, ThumbsUp, Trash2,
  User, Users, VolumeX,
} from 'lucide-react';

/** Values and HTML vocabulary come from landing-proof-data.ts and its French
 * capture translation. These are authored demonstration data, not user data. */
export const STORY_DEMO = {
  request: 'Prépare ma réunion de lancement avec le dossier projet, les e-mails du fournisseur et le compte rendu.',
  draftRequest: 'Prépare un message pour clarifier la date de livraison. Demande-moi avant de l’envoyer.',
  heading: 'Ta réunion de lancement, prête à préparer',
  summary: 'Le dossier projet, le dernier e-mail du fournisseur et le compte rendu concordent sur le périmètre. Une date de livraison reste à clarifier.',
  recipient: 'supplier@example.test',
  subject: 'Confirmer la date de livraison Atlas',
  body: 'Bonjour,\n\nNotre dossier prévoit le 19 octobre, tandis que le dernier e-mail mentionne le 22. Merci de confirmer la date retenue par l’équipe.\n\nMerci,\nAlex Démo',
  result: 'Brouillon validé dans cette démonstration. Aucun message réel n’a été envoyé.',
} as const;

const navigation = [LayoutDashboard, MessageSquare, Users, ClipboardList, Bell, Settings, CircleHelp];
const utilities = [GitBranch, Circle, Radio, VolumeX, Moon, Scale];

export function NativeNavigation() {
  return <div className="story-native-nav">
    <div className="story-native-nav-inner">
      <div className="story-native-brand">LIA</div>
      <div className="story-native-nav-icons">
        {navigation.map((Icon, index) => <div key={index} className={`story-native-nav-button ${index === 1 ? 'is-active' : ''}`}><Icon size={16} strokeWidth={1.7} /></div>)}
      </div>
      <div className="story-native-nav-utilities">
        {utilities.map((Icon, index) => <div key={index} className="story-native-nav-button"><Icon size={16} strokeWidth={1.7} /></div>)}
        <div className="story-native-flag">🇫🇷</div>
        <div className="story-native-logout"><LogOut size={18} /></div>
      </div>
    </div>
  </div>;
}

export function NativeChatHeader({ frame }: { frame: number }) {
  void frame;
  return <div className="story-native-chat-header">
    <div className="story-native-search"><Search size={14} /><span>Rechercher...</span></div>
    <div className="story-native-header-pills">
      <div><Mic size={16} /></div><div><span className="story-native-meter" />8%</div><div><BookOpen size={15} />1</div>
    </div>
    <div className="story-native-delete"><Trash2 size={14} />Supprimer</div>
  </div>;
}

export function NativeComposer({ text = '', sending = false }: { text?: string; sending?: boolean }) {
  return <div className="story-native-composer">
    <div className="story-native-composer-inner">
      <div className="story-native-add"><Plus size={18} /></div>
      <div className={`story-native-input ${text ? 'has-text' : ''}`}>{text || 'Écris ton message...'}{text ? <span className="story-native-caret" /> : null}</div>
      <div className="story-native-send">{text || sending ? <Send size={16} /> : <Mic size={16} />}<span>{text || sending ? 'Envoyer' : 'Maintiens pour parler'}</span></div>
    </div>
  </div>;
}

export function NativeUserMessage({ text, style }: { text: string; style?: CSSProperties }) {
  return <div className="story-native-user" style={style}>
    <div className="story-native-user-avatar"><User size={18} /></div>
    <div><div className="story-native-user-bubble">{text}</div><span className="story-native-time">09:29</span></div>
  </div>;
}

export function NativeMessageActions() {
  return <div className="story-native-message-actions">{[Copy, Download, ThumbsUp, ThumbsDown].map((Icon, index) => <div key={index}><Icon size={14} strokeWidth={1.7} /></div>)}</div>;
}

export function NativeSourceRow({ index, highlight = 0 }: { index: number; highlight?: number }) {
  const dateStyle: CSSProperties = {
    backgroundColor: `rgba(245,158,11,${highlight * 0.19})`,
    boxShadow: `0 2px 0 rgba(245,158,11,${highlight * 0.8})`,
  };
  const labels = ['Dossier projet', 'E-mail fournisseur', 'Compte rendu'];
  return <React.Fragment>
    <dt>{labels[index]}</dt>
    <dd>{index === 0 ? <>Plan de lancement.pdf · objectif <span style={dateStyle}>19 octobre</span></> : index === 1 ? <>supplier@example.test · proposition du <span style={dateStyle}>22 octobre</span></> : 'Réunion · décision encore ouverte'}</dd>
  </React.Fragment>;
}

/** The product renders one definition list. The film keeps that shared grid
 * when lifting the excerpt, rather than turning its lines into new cards. */
export function NativeSourceBlock({ highlight = 0, rowHighlights, style }: {
  highlight?: number; rowHighlights?: readonly number[]; style?: CSSProperties;
}) {
  return <dl className="story-native-source-list" style={style}>
    {[0, 1, 2].map(index => <NativeSourceRow key={index} index={index} highlight={rowHighlights?.[index] ?? highlight} />)}
  </dl>;
}

export function NativeDateCallout() {
  return <div className="story-native-rich story-native-warning">
    <p className="story-native-callout-title">Une date à clarifier avant la réunion</p>
    <p>Le dossier indique le 19 octobre ; le fournisseur propose le 22. Fais confirmer la date avant de partager le planning.</p>
  </div>;
}

export function NativeResearchResponse({ frame, reveal = 1, sourceOpacity = 1, calloutOpacity = 1, highlight = 0 }: {
  frame: number; reveal?: number; sourceOpacity?: number; calloutOpacity?: number; highlight?: number;
}) {
  void frame;
  return <div className="story-native-research">
    <div className="story-native-assistant-bubble">
      <div className="story-native-rich" style={{ clipPath: `inset(0 0 ${(1 - reveal) * 100}% 0)` }}>
        <h2>{STORY_DEMO.heading}</h2>
        <p>{STORY_DEMO.summary}</p>
        <div style={{ opacity: calloutOpacity }}><NativeDateCallout /></div>
        <NativeSourceBlock style={{ opacity: sourceOpacity }} highlight={highlight} />
        <h3>Trois prochaines étapes</h3>
        <ol className="story-native-steps">
          <li>Clarifier la date de livraison avec le fournisseur.</li>
          <li>Garder ce point ouvert dans la réunion de lundi.</li>
          <li>Préparer un message à valider avant envoi.</li>
        </ol>
        <div className="story-native-info">
          <p className="story-native-callout-title">Sources de cette démonstration</p>
          <p>Plan de lancement.pdf (espace Projet Atlas), e-mail fournisseur et compte rendu. Données de démonstration ; aucun message réel envoyé.</p>
        </div>
      </div>
      <NativeMessageActions />
    </div>
    <div className="story-native-usage">09:30 | <span>🟠 2 400 IN</span> <span>🟢 380 OUT</span> <span>🔵 800 CACHE</span> <span>🟣 1 GOOGLE</span> · 0,001800 €</div>
  </div>;
}

export function NativeDraftResponse({ frame }: { frame: number }) {
  void frame;
  return <div className="story-native-draft-response">
    <div className="story-native-assistant-bubble">
      <div className="story-native-rich">
        <h2>Un message prêt à être validé</h2>
        <p>La date proposée diffère du dossier projet. Voici un message pour demander une confirmation.</p>
        <dl className="story-native-draft-dl"><dt>Destinataire</dt><dd>{STORY_DEMO.recipient}</dd><dt>Objet</dt><dd>{STORY_DEMO.subject}</dd></dl>
        <p>Tu peux confirmer, modifier ou annuler. Ce brouillon de démonstration n’a pas été envoyé.</p>
      </div>
      <NativeMessageActions />
    </div>
  </div>;
}

/** Controlled view of HitlActionCard.tsx: same inline location, spacing,
 * title, preview and three button variants. No runtime hooks or network. */
export function NativeApprovalCard({ status = 'awaiting', pressed = false }: { status?: 'awaiting' | 'submitting' | 'resolved'; pressed?: boolean }) {
  return <section className="story-native-hitl" aria-label="Brouillon à valider">
    <div className="story-native-hitl-icon"><Mail size={16} /></div>
    <div className="story-native-hitl-content">
      <p className="story-native-hitl-title">Brouillon à valider</p>
      <div className="story-native-hitl-preview">
        <div><span>À</span>{STORY_DEMO.recipient}</div>
        <div><span>Objet</span>{STORY_DEMO.subject}</div>
        <p>{STORY_DEMO.body}</p>
      </div>
      <div className="story-native-hitl-buttons">
        {status === 'resolved' ? <p className="story-native-resolved"><Check size={14} />Confirmé</p> : <>
          <div className={`story-native-button story-native-button-primary ${pressed ? 'is-pressed' : ''} ${status === 'submitting' ? 'is-disabled' : ''}`}>Confirmer</div>
          <div className={`story-native-button story-native-button-ghost ${status === 'submitting' ? 'is-disabled' : ''}`}>Modifier</div>
          <div className={`story-native-button story-native-button-outline ${status === 'submitting' ? 'is-disabled' : ''}`}>Annuler</div>
        </>}
      </div>
    </div>
  </section>;
}

export function NativeResult({ frame }: { frame: number }) {
  void frame;
  return <div className="story-native-result">
    <div className="story-native-assistant-bubble"><div className="story-native-rich"><p>{STORY_DEMO.result}</p></div><NativeMessageActions /></div>
  </div>;
}
