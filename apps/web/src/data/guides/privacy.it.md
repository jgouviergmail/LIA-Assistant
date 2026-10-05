# LIA — Informativa sulla privacy

> I tuoi dati. Il tuo assistente. Le tue regole.

**Versione**: 1.0
**Data**: 2026-10-05
**Licenza**: AGPL-3.0 (Open Source)

---

## Indice

1. [Introduzione](#introduction)
2. [Dati raccolti](#data_collected)
3. [Basi giuridiche del trattamento](#legal_basis)
4. [Hosting e ubicazione dei dati](#hosting)
5. [Sicurezza dei dati](#security)
6. [Fornitori di LLM](#llm_providers)
7. [Conservazione dei dati](#retention)
8. [I tuoi diritti](#rights)
9. [Cookie](#cookies)
10. [Contatti](#contact)

---

## 1. Introduzione

Questa informativa sulla privacy descrive come LIA, un assistente personale di IA open source, raccoglie, utilizza e protegge i tuoi dati personali. LIA è sviluppato e gestito da uno sviluppatore indipendente come progetto open source con licenza AGPL-3.0.

LIA è attualmente in fase beta ed è offerto gratuitamente durante questo periodo. L'applicazione è accessibile all'indirizzo [https://lia.jeyswork.com](https://lia.jeyswork.com). Il codice sorgente completo è disponibile pubblicamente, consentendoti di verificare in qualsiasi momento come vengono trattati i tuoi dati.

Questa informativa si applica all'istanza ospitata di LIA. Se distribuisci una tua istanza (self-hosting), ne controlli il funzionamento e devi valutare gli obblighi di protezione dei dati applicabili al tuo utilizzo; questa informativa non si applica direttamente. Ti incoraggiamo comunque a usarla come punto di partenza per tale valutazione.

Utilizzando LIA, riconosci di aver letto e compreso questa informativa. Se non accetti le condizioni descritte, ti invitiamo a non utilizzare il servizio.

## 2. Dati raccolti

LIA tratta le seguenti categorie di dati per fornire il servizio e le funzionalità opzionali che scegli di utilizzare:

**Dati dell'account utente:**
- Indirizzo email (identificativo univoco)
- Nome e cognome
- Password (sottoposta a hashing con bcrypt, mai memorizzata in chiaro)
- Preferenze linguistiche e fuso orario
- Ruolo dell'utente (standard o amministratore)

**Dati delle conversazioni:**
- Messaggi scambiati tra te e l'assistente
- Piani di esecuzione generati dal sistema di pianificazione
- Risultati delle azioni eseguite dagli agenti (ricerca di email, creazione di eventi, ecc.)
- Cronologia delle conversazioni, salvata sotto forma di checkpoint in PostgreSQL
- Ricordi, preferenze, documenti e altri contenuti che fornisci per personalizzare l'assistente

**Dati di connessione a servizi di terze parti:**
- Token di accesso e di aggiornamento OAuth per i servizi che utilizzano OAuth, tra cui Google Workspace e Microsoft 365
- Password specifiche per le applicazioni o altre credenziali per connettori come Apple iCloud, e chiavi API dei fornitori che configuri
- Questi segreti memorizzati sono cifrati con Fernet (AES-128-CBC con autenticazione HMAC-SHA256)

**Dati delle funzionalità opzionali:**
- Un indirizzo di casa che salvi e la posizione del browser, se concedi l'autorizzazione; anche la memorizzazione dell'ultima posizione nota richiede un'attivazione volontaria. Questi campi di localizzazione sono cifrati, la posizione memorizzata sostituisce quella precedente senza creare una cronologia delle posizioni e viene cancellata quando disattivi l'opzione
- Audio, trascrizioni ed eventuali immagini o documenti utilizzati in una richiesta vocale, una riunione o una richiesta multimodale
- Misurazioni relative alla salute, se scegli di collegare una fonte e utilizzare le funzionalità dedicate

**Dati di utilizzo:**
- Metriche operative aggregate (numero di richieste, tempi di risposta) e registrazioni di utilizzo per account
- Contatori dei token LLM consumati per sessione
- Log di errori tecnici con controlli per oscurare segreti e contenuti personali; le tracce diagnostiche opzionali hanno un ambito distinto, descritto più avanti

**Dati che LIA NON raccoglie:**
- Modelli biometrici di autenticazione conservati dal tuo dispositivo quando utilizzi una passkey
- Dati di navigazione al di fuori dell'applicazione
- Profili pubblicitari o dati di targeting

## 3. Basi giuridiche del trattamento

La seguente tabella indica le basi giuridiche utilizzate per il servizio ospitato ai sensi del Regolamento generale sulla protezione dei dati (GDPR):

| Attività di trattamento | Base giuridica | Motivazione |
|---|---|---|
| Creazione e gestione dell'account | Esecuzione di un contratto (art. 6.1.b) | Necessaria per fornire il servizio |
| Conversazioni con l'assistente | Esecuzione di un contratto (art. 6.1.b) | Funzione principale del servizio |
| Connessioni a servizi di terze parti (Google, Apple, Microsoft) | Consenso esplicito (art. 6.1.a) | Scegli attivamente di collegare ogni servizio |
| Invio di dati ai fornitori di LLM | Esecuzione di un contratto (art. 6.1.b) | Necessario per il funzionamento dell'assistente |
| Log tecnici e metriche | Legittimo interesse (art. 6.1.f) | Mantenere la sicurezza e l'affidabilità del servizio |
| Cookie di preferenza linguistica | Consenso (art. 6.1.a) | Memorizzare la tua scelta della lingua |

Puoi revocare in qualsiasi momento il consenso per i trattamenti che si basano su di esso, senza pregiudicare la liceità del trattamento effettuato prima della revoca.

## 4. Hosting e ubicazione dei dati

**Infrastruttura dell'istanza ospitata:**

L'istanza ufficiale di LIA è ospitata su un server fisico amministrato dallo sviluppatore. I dati sono memorizzati in Francia.

- **Database**: PostgreSQL per l'archiviazione persistente (account, conversazioni, checkpoint)
- **Cache**: Redis per le sessioni e la memorizzazione temporanea nella cache
- **Reverse proxy**: Cloudflare Tunnel per l'accesso sicuro tramite HTTPS
- **Certificati TLS**: Gestiti automaticamente da Cloudflare

**Trasferimenti internazionali di dati:**

Quando interagisci con LIA, i dati necessari alla tua richiesta possono essere trasmessi a fornitori di modelli, servizi vocali, avatar, ricerca o altri servizi, a seconda delle funzionalità e della configurazione che utilizzi. Questi fornitori possono avere server situati al di fuori dell'Unione europea, in particolare negli Stati Uniti e in Cina. Per ulteriori dettagli, consulta la sezione «Fornitori di LLM».

Le connessioni a Google Workspace, Apple iCloud e Microsoft 365 comportano anche scambi con i server di questi fornitori, soggetti alle rispettive informative sulla privacy.

## 5. Sicurezza dei dati

LIA implementa un'architettura di sicurezza a più livelli progettata per proteggere i tuoi dati in ogni fase:

**Architettura BFF (Backend-for-Frontend):**
La sessione dell'applicazione utilizza un cookie HttpOnly, mentre le credenziali di lunga durata dei connettori e i segreti API per modelli o avatar vengono gestiti lato server. Alcune connessioni vocali e degli avatar utilizzano credenziali di sessione temporanee nel browser. Anche Google Maps interattivo riceve una chiave API per il browser dopo un'attivazione autenticata; questa chiave richiede restrizioni presso il fornitore e quote adeguate.

**Cifratura dei dati sensibili:**
- Le credenziali dei connettori, i segreti dei fornitori e i campi di localizzazione designati che vengono memorizzati sono cifrati con [Fernet](https://cryptography.io/en/latest/fernet/) (AES-128-CBC + autenticazione HMAC-SHA256)
- Le password sono sottoposte a hashing con bcrypt (fattore di costo adattivo)
- L'accesso all'applicazione ospitata avviene tramite HTTPS; la protezione delle connessioni interne e dei backup dipende dalla distribuzione

Questa cifratura a livello di campo non cifra tutte le colonne del database. Le conversazioni sono leggibili dal server per essere elaborate e non sono cifrate end-to-end. Un operatore con accesso al database e alla chiave di cifratura può accedere ai dati memorizzati; la sicurezza di tale accesso e dei backup dipende anche dalla gestione dell'istanza.

**Informazioni personali e diagnostica:**
I controlli di oscuramento proteggono i log tecnici; non anonimizzano automaticamente il contesto inviato a un modello. I tuoi messaggi e i contenuti pertinenti dei servizi collegati possono contenere informazioni personali necessarie alla tua richiesta. Se il tracciamento LLM è attivo, gli strumenti diagnostici possono conservare anche input e output dei modelli e metadati associati all'account. L'operatore deve configurarne l'accesso, l'hosting e la conservazione.

**Sessioni e autenticazione:**
- Le sessioni degli utenti vengono memorizzate in Redis con scadenza automatica
- L'autenticazione si basa su cookie sicuri (HttpOnly, Secure, SameSite)
- Il JavaScript lato client non può leggere il cookie HttpOnly della sessione dell'applicazione; le credenziali temporanee per le sessioni vocali o degli avatar abilitate nel browser hanno uno scopo diverso

**Log sicuri:**
I log tecnici utilizzano un formato JSON strutturato (tramite structlog), con regole per omettere i contenuti citati dell'utente e oscurare segreti e informazioni personali riconosciuti. Questi controlli non rendono anonimo ogni archivio diagnostico.

## 6. Fornitori di LLM

LIA utilizza più fornitori di modelli linguistici di grandi dimensioni (LLM) per elaborare le tue richieste. La scelta dipende dalla configurazione della tua istanza e dal tipo di attività:

| Fornitore | Sede | Utilizzo in LIA |
|---|---|---|
| OpenAI | Stati Uniti | Modelli GPT per conversazione e pianificazione |
| Anthropic | Stati Uniti | Modelli Claude per conversazione e analisi |
| Google (Gemini) | Stati Uniti | Modelli Gemini per elaborazione multimodale |
| DeepSeek | Cina | Modelli di ragionamento avanzato |
| Qwen (Alibaba) | Cina | Modelli di elaborazione del linguaggio |
| Perplexity | Stati Uniti | Ricerca web potenziata |
| Ollama | Dipende dall'endpoint configurato | Inferenza dei modelli su un server locale quando è configurato in questo modo |

**Cosa viene trasmesso ai fornitori di LLM:**
- Il contenuto dei tuoi messaggi
- Il contesto conversazionale necessario per la coerenza delle risposte
- I risultati pertinenti degli strumenti (contenuto delle email, dettagli degli eventi, documenti, ecc.), che possono contenere dati personali

I percorsi vocali, delle riunioni, delle immagini e dell'avatar parlante opzionale possono inoltre trasmettere audio, testo o immagini necessari ai rispettivi fornitori. Le funzionalità selezionate e l'instradamento determinano quali servizi li ricevono.

**Come vengono utilizzate le credenziali:**
Le credenziali dei connettori e le chiavi dei fornitori servono per autenticarsi presso il servizio pertinente; non vengono aggiunte ai prompt dei modelli come contenuto della conversazione. Evita di inserire password o altri segreti nei tuoi messaggi: il contenuto che fornisci può diventare parte di una richiesta a un fornitore.

**Impegni dei fornitori:**
L'utilizzo per l'addestramento, la conservazione e altre modalità di trattamento dei dati dipendono dal fornitore, dal prodotto, dalle impostazioni dell'account e dal contratto o dall'informativa sulla privacy applicabili. Esamina tali condizioni per ogni servizio che abiliti; LIA non può offrire a loro nome una garanzia universale che i dati non vengano usati per l'addestramento.

Scegliere un endpoint Ollama ospitato localmente mantiene l'inferenza del modello selezionato su quell'endpoint. Questo non rende locali le altre integrazioni: gli account collegati, la ricerca web e i servizi remoti vocali o degli avatar possono continuare a scambiare dati con i propri fornitori.

## 7. Conservazione dei dati

I periodi di conservazione sono definiti in base alla natura dei dati:

| Tipo di dati | Periodo di conservazione | Motivazione |
|---|---|---|
| Account utente | I contenuti personali vengono eliminati nella fase di cancellazione; il record dell'account e le registrazioni di fatturazione restano fino alla rispettiva fase di rimozione o al termine di conservazione applicabile | Funzionamento del servizio, contabilità e obblighi di legge applicabili |
| Cronologia delle conversazioni | Fino alla cancellazione da parte dell'utente o alla cancellazione dell'account | Continuità del servizio |
| Credenziali cifrate dei connettori | Fino alla disconnessione del servizio o alla cancellazione dell'account | Accesso ai servizi collegati |
| Posizione del browser memorizzata | Sostituita quando viene aggiornata e cancellata quando si disattiva la memorizzazione volontaria; la sua attualità ne limita l'utilizzo | Richieste basate sulla posizione senza una cronologia delle posizioni |
| Sessioni Redis | Scadenza automatica secondo le impostazioni della sessione e di «Ricordami» | Sicurezza |
| Log tecnici e tracce diagnostiche opzionali | Conservazione configurata per ciascun archivio diagnostico | Diagnostica e sicurezza |
| Metriche di utilizzo | Conservazione configurata per l'archivio delle metriche; le registrazioni associate all'account seguono il loro ciclo di vita documentato | Contabilizzazione dell'utilizzo e funzionamento del servizio |

**Cancellazione dell'account:**
Puoi richiedere la cancellazione dell'account all'amministratore. La fase di cancellazione elimina contenuti personali come conversazioni, ricordi, documenti, checkpoint e credenziali memorizzate dei connettori, ma conserva il record dell'account, inclusi nome e indirizzo email, e le registrazioni di fatturazione. La successiva fase di rimozione definitiva elimina il record dell'account rimasto. I registri di audit, gli archivi diagnostici separati, i backup e i dati già ricevuti dai fornitori richiedono proprie procedure di conservazione e cancellazione; nessuna delle due fasi elimina immediatamente ogni copia. L'operatore deve gestire le richieste di cancellazione applicabili in tutti questi archivi.

## 8. I tuoi diritti

Ai sensi del GDPR, hai i seguenti diritti:

- **Diritto di accesso** (art. 15): Ottenere una copia di tutti i dati personali che conserviamo su di te.
- **Diritto di rettifica** (art. 16): Correggere dati personali inesatti o incompleti.
- **Diritto alla cancellazione** (art. 17): Richiedere la cancellazione dei tuoi dati personali («diritto all'oblio»).
- **Diritto alla limitazione** (art. 18): Richiedere la limitazione del trattamento dei tuoi dati in determinate circostanze.
- **Diritto alla portabilità dei dati** (art. 20): Ricevere i tuoi dati in un formato strutturato, di uso comune e leggibile da dispositivo automatico.
- **Diritto di opposizione** (art. 21): Opporti al trattamento dei tuoi dati basato sul legittimo interesse.
- **Diritto di revoca del consenso**: In qualsiasi momento, senza pregiudicare la liceità del trattamento effettuato prima della revoca.

Per esercitare questi diritti, contattaci all'indirizzo indicato nella sezione «Contatti». Risponderemo senza ingiustificato ritardo e normalmente entro un mese dal ricevimento della tua richiesta; un'eventuale proroga motivata sarà comunicata come previsto dall'[articolo 12 del GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng).

Se ritieni che i tuoi diritti non siano rispettati, hai il diritto di presentare un reclamo alla CNIL (Commission Nationale de l'Informatique et des Libertés) o a qualsiasi altra autorità di controllo competente.

## 9. Cookie

LIA utilizza un numero minimo di cookie, esclusivamente funzionali:

| Cookie | Finalità | Durata | Tipo |
|---|---|---|---|
| `NEXT_LOCALE` | Memorizza la tua preferenza linguistica (fr, en, de, es, it, zh) | 1 anno | Funzionale |
| Cookie di sessione | Mantiene la tua sessione di autenticazione | Durata della sessione | Strettamente necessario |

**Cosa LIA NON utilizza:**
- Nessun cookie di tracciamento
- Nessun cookie pubblicitario
- Nessun cookie di analisi di terze parti (Google Analytics, ecc.)
- Nessun pixel di tracciamento
- Nessuna rilevazione dell'impronta del browser (fingerprinting)

I cookie utilizzati da LIA sono strettamente necessari al funzionamento del servizio oppure riguardano una tua scelta esplicita (preferenza linguistica). In conformità alla direttiva ePrivacy, i cookie strettamente necessari non richiedono un consenso preventivo.

## 10. Contatti

Per qualsiasi domanda sulla protezione dei tuoi dati personali, sull'esercizio dei tuoi diritti o su questa informativa, puoi contattarci:

- **Email**: liamyassistant@gmail.com
- **Sito web**: [https://lia.jeyswork.com](https://lia.jeyswork.com)
- **Codice sorgente**: [GitHub](https://github.com/jgouviergmail/LIA-Assistant) (AGPL-3.0)

**Titolare del trattamento:**
LIA è gestito da uno sviluppatore indipendente che agisce come titolare del trattamento ai sensi del GDPR.

**Modifiche a questa informativa:**
Questa informativa può essere aggiornata per riflettere modifiche al servizio o alla normativa applicabile. In caso di una modifica sostanziale, riceverai una notifica tramite l'applicazione. Fa fede la data di aggiornamento riportata all'inizio di questo documento. Ti incoraggiamo a consultare regolarmente questa informativa.

**Trasparenza open source:**
Come progetto open source, LIA ti consente di esaminare il codice sorgente in qualsiasi momento per verificare esattamente quali dati vengono raccolti, come vengono trattati e dove vengono inviati. Questa trasparenza radicale è un impegno fondamentale del progetto.
