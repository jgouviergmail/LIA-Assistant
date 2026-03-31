# LIA — L'Assistente IA Personale Sovrano

> **Your Life. Your AI. Your Rules.**

**Versione**: 2.0
**Data**: 2026-03-24
**Applicazione**: LIA v1.13.8
**Licenza**: AGPL-3.0 (Open Source)

---

## Indice

1. [Il mondo è cambiato](#1-il-mondo-è-cambiato)
2. [La tesi di LIA](#2-la-tesi-di-lia)
3. [Sovranità: riprendere il controllo](#3-sovranità-riprendere-il-controllo)
4. [Trasparenza radicale: vedere cosa fa l'IA e quanto costa](#4-trasparenza-radicale-vedere-cosa-fa-lia-e-quanto-costa)
5. [La profondità relazionale: oltre la memoria](#5-la-profondità-relazionale-oltre-la-memoria)
6. [L'orchestrazione che funziona in produzione](#6-lorchestrazione-che-funziona-in-produzione)
7. [Il controllo umano come filosofia](#7-il-controllo-umano-come-filosofia)
8. [Agire nella vostra vita digitale](#8-agire-nella-vostra-vita-digitale)
9. [La proattività contestuale](#9-la-proattività-contestuale)
10. [La voce come interfaccia naturale](#10-la-voce-come-interfaccia-naturale)
11. [L'apertura come strategia](#11-lapertura-come-strategia)
12. [L'intelligenza che si auto-ottimizza](#12-lintelligenza-che-si-auto-ottimizza)
13. [Il tessuto: come tutto si intreccia](#13-il-tessuto-come-tutto-si-intreccia)
14. [Cosa LIA non pretende di essere](#14-cosa-lia-non-pretende-di-essere)
15. [Visione: dove va LIA](#15-visione-dove-va-lia)

---

## 1. Il mondo è cambiato

### 1.1. L'era agentica è arrivata

Siamo a marzo 2026. Il panorama dell'intelligenza artificiale non ha più nulla a che vedere con quello di due anni fa. I grandi modelli linguistici non sono più semplici generatori di testo — sono diventati **agenti capaci di agire**.

**ChatGPT** dispone ormai di una modalità Agent che combina navigazione web autonoma (ereditata da Operator), ricerca approfondita e connessione ad applicazioni di terze parti (Outlook, Slack, Google apps). Può analizzare concorrenti e creare presentazioni, pianificare la spesa e ordinarla, preparare un briefing sulle riunioni a partire dal calendario. Le attività vengono eseguite su un computer virtuale dedicato e gli utenti paganti accedono a un vero ecosistema di applicazioni integrate.

**Google Gemini Agent** si è integrato profondamente nell'ecosistema Google: Gmail, Calendar, Drive, Tasks, Maps, YouTube. Chrome Auto Browse permette a Gemini di navigare sul web in modo autonomo — compilare moduli, fare acquisti, eseguire workflow multi-step. L'integrazione nativa con Android tramite AppFunctions estende queste capacità a livello di sistema operativo.

**Microsoft Copilot** si è trasformato in piattaforma agentica aziendale con oltre 1 400 connettori, il supporto al protocollo MCP, coordinamento multi-agente e Work IQ — uno strato di intelligenza contestuale che conosce il vostro ruolo, il vostro team e la vostra azienda. Copilot Studio consente di creare agenti autonomi senza codice.

**Claude** di Anthropic propone Computer Use per interagire con interfacce grafiche e un ricco ecosistema MCP per connettere strumenti, database e file system. Claude Code opera come un agente di sviluppo completo.

Il mercato degli agenti IA raggiunge 7,84 miliardi di dollari nel 2025 con una crescita del 46 % annuo. Gartner prevede che il 40 % delle applicazioni aziendali integrerà agenti IA specifici entro la fine del 2026.

### 1.2. Ma il mondo ha un problema

Dietro questa effervescenza si nasconde una realtà più sfumata.

**Solo il 10-15 % dei progetti IA agentici raggiunge la produzione.** Il tasso di fallimento nel coordinamento tra agenti è del 35 %. Gartner avverte che oltre il 40 % dei progetti di IA agentica verrà annullato entro la fine del 2027, per mancanza di controllo su costi e rischi. I costi LLM esplodono nei cicli agentici non controllati, il comportamento non deterministico rende il debugging un incubo e le tracce di audit sono spesso assenti.

E soprattutto: **questi assistenti potenti sono tutti servizi cloud proprietari.** Le vostre email, la vostra agenda, i vostri contatti, i vostri documenti — tutto transita dai server di Google, Microsoft o OpenAI. Il prezzo della comodità è la cessione dei vostri dati più intimi ad aziende il cui modello di business si fonda sullo sfruttamento di quei dati. Il costo dell'abbonamento non è il vero prezzo: **i vostri dati personali sono il prodotto.**

E quando cambiate idea, quando volete andarvene? La vostra memoria, le vostre preferenze, la vostra cronologia — tutto resta prigioniero della piattaforma. Il lock-in è totale.

### 1.3. Una domanda fondamentale

È in questo contesto che LIA pone una domanda semplice ma radicale:

> **È possibile beneficiare della potenza degli agenti IA senza rinunciare alla propria sovranità digitale?**

La risposta è sì. Ed è l'intera ragion d'essere di LIA.

---

## 2. La tesi di LIA

### 2.1. Cosa LIA non è

LIA non è un concorrente diretto di ChatGPT, Gemini o Copilot. Pretendere di competere con i budget di ricerca di Google, Microsoft o OpenAI sarebbe un'impostura.

LIA non è nemmeno un wrapper — un'interfaccia che maschera un singolo LLM dietro una bella facciata.

### 2.2. Cosa LIA è

LIA è un **assistente IA personale sovrano**: un sistema completo, open source, auto-ospitabile, che orchestra intelligentemente i migliori modelli di IA sul mercato per agire nella vostra vita digitale — sotto il vostro controllo totale, sulla vostra infrastruttura.

È una tesi in cinque punti:

1. **La sovranità**: i vostri dati restano a casa vostra, sul vostro server, anche un semplice Raspberry Pi
2. **La trasparenza**: ogni decisione, ogni costo, ogni chiamata LLM è visibile e verificabile
3. **La profondità relazionale**: una comprensione psicologica ed emotiva che va oltre la semplice memoria fattuale
4. **L'affidabilità in produzione**: un sistema che ha risolto i problemi che il 90 % dei progetti agentici non supera
5. **L'apertura radicale**: nessun lock-in, 7 fornitori IA intercambiabili, standard aperti

Questi cinque punti non sono feature di marketing. Sono **scelte architetturali profonde** che attraversano ogni riga di codice, ogni decisione progettuale, ogni compromesso tecnico documentato in 59 Architecture Decision Records.

### 2.3. Il significato profondo

La convinzione alla base di LIA è che il futuro dell'IA personale non passerà dalla sottomissione a un gigante del cloud, ma dall'**appropriazione**: l'utente deve poter possedere il proprio assistente, comprenderne il funzionamento, controllarne i costi e farlo evolvere secondo le proprie esigenze.

L'IA più potente del mondo non serve a nulla se non ci si può fidare. E la fiducia non si decreta — si costruisce attraverso la trasparenza, il controllo e l'esperienza ripetuta.

---

## 3. Sovranità: riprendere il controllo

### 3.1. L'auto-hosting come atto fondatore

LIA gira in produzione su un **Raspberry Pi 5** — un computer single-board da 80 euro. È una scelta deliberata, non un vincolo. Se un assistente IA completo con 15 agenti specializzati, uno stack di osservabilità e un sistema di memoria psicologica può funzionare su un micro-server ARM, allora la sovranità digitale non è più un privilegio aziendale — è un diritto accessibile a tutti.

Le immagini Docker multi-architettura (amd64/arm64) consentono il deployment su qualsiasi infrastruttura: un NAS Synology, un VPS da 5 euro al mese, un server aziendale o un cluster Kubernetes.

### 3.2. I vostri dati, il vostro database

Quando usate ChatGPT, le vostre conversazioni sono archiviate sui server di OpenAI. Quando attivate la memoria di Gemini, i vostri ricordi vivono presso Google. Quando Copilot indicizza i vostri file, transitano attraverso Microsoft Azure.

Con LIA, tutto risiede nel **vostro** PostgreSQL:

- Le vostre conversazioni e la loro cronologia
- La vostra memoria a lungo termine e il vostro profilo psicologico
- I vostri spazi di conoscenza (RAG)
- I vostri diari personali
- Le vostre preferenze e configurazioni

Potete in qualsiasi momento esportare, salvare, migrare o cancellare la totalità dei vostri dati. Il GDPR non è un vincolo per LIA — è una conseguenza naturale dell'architettura.

### 3.3. La libertà di scelta dell'IA

ChatGPT vi lega a OpenAI. Gemini a Google. Copilot a Microsoft.

LIA vi connette a **7 fornitori simultaneamente**: OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen e Ollama. E potete mixare: usare OpenAI per la pianificazione, Anthropic per la risposta, DeepSeek per le attività in background — configurando ogni nodo della pipeline in modo indipendente dall'interfaccia di amministrazione.

Questa libertà non è solo una questione di costo o di prestazioni. È un'**assicurazione contro la dipendenza**: se un fornitore cambia le tariffe, degrada il servizio o chiude la propria API, passate ad un altro con un clic.

---

## 4. Trasparenza radicale: vedere cosa fa l'IA e quanto costa

### 4.1. Il problema della scatola nera

Quando ChatGPT Agent esegue un'attività, vedete il risultato. Ma quante chiamate LLM sono state necessarie? Quali modelli sono stati utilizzati? Quanti token? Quale costo? Perché quella decisione piuttosto che un'altra? Non ne sapete nulla. Il sistema è una scatola nera.

Questa opacità non è neutrale. Un abbonamento da 20 o 200 dollari al mese crea l'illusione della gratuità: non vedete mai il costo reale delle vostre interazioni. Ciò incoraggia un uso indiscriminato e priva l'utente di qualsiasi leva di ottimizzazione.

### 4.2. La trasparenza come valore fondamentale

LIA prende la posizione opposta: **tutto è visibile, tutto è verificabile**.

**Il pannello di debug** — accessibile nell'interfaccia di chat — espone in tempo reale per ogni conversazione:

| Categoria                  | Cosa vedete                                                                                                     |
| -------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Analisi dell'intento**   | Come il router ha classificato il vostro messaggio, con il punteggio di confidenza                              |
| **Pipeline di esecuzione** | Il piano generato, le ondate di esecuzione parallela, le chiamate agli strumenti con i loro input/output        |
| **Pipeline LLM**           | Ogni chiamata LLM ed embedding in ordine cronologico: modello, durata, token (input/cache/output), costo        |
| **Contesto e memoria**     | Quali ricordi sono stati iniettati, quali documenti RAG, quale profilo di interessi                             |
| **Intelligenza**           | I cache hit, i pattern appresi, le espansioni semantiche                                                        |
| **Diari personali**        | Le note iniettate con il loro punteggio di pertinenza, le estrazioni in background                              |
| **Ciclo di vita**          | Il timing esatto di ogni fase della richiesta                                                                    |

**Il monitoraggio dei costi** è granulare al centesimo: ogni messaggio mostra il proprio costo in token e in euro. L'utente può esportare il proprio consumo in CSV. L'amministratore dispone di dashboard in tempo reale con indicatori per utente, quote configurabili (token, messaggi, costo) per periodo e globali.

### 4.3. Perché cambia tutto

La trasparenza non è un gadget per tecnici. Cambia la relazione fondamentale tra l'utente e il suo assistente:

- **Capite** perché LIA ha scelto un approccio piuttosto che un altro
- **Controllate** i vostri costi e potete ottimizzare (modello più economico per il routing, più potente per la risposta)
- **Individuate** i problemi (un piano che va in loop, una cache che non funziona, una memoria che inquina)
- **Vi fidate** perché potete verificare, non perché vi si chiede di credere

---

## 5. La profondità relazionale: oltre la memoria

### 5.1. Cosa fanno gli altri

I grandi assistenti dispongono tutti di sistemi di memoria in rapida evoluzione. ChatGPT trattiene i fatti importanti, organizza automaticamente i ricordi per priorità e GPT-5 comprende ormai tono e intenzione emotiva. Gemini Personal Intelligence (gratuito da marzo 2026) accede a Gmail, Photos, Docs e YouTube per costruire un contesto ricco. Copilot usa Work IQ per comprendere il vostro ruolo, il vostro team e le vostre abitudini professionali.

Questi sistemi sono potenti e in costante miglioramento. Ma il loro approccio alla memoria resta essenzialmente **fattuale e contestuale**: trattengono le vostre preferenze, i vostri dati personali e i vostri pattern di interazione. La comprensione emotiva di GPT-5, ad esempio, è implicita — emerge dal modello — ma non è strutturata, ponderata né sfruttabile in modo programmatico.

### 5.2. Cosa fa LIA

LIA costruisce qualcosa di fondamentalmente diverso: un **profilo psicologico** dell'utente.

Ogni ricordo non è una semplice coppia chiave-valore. Porta con sé:

- Un **peso emotivo** (-10 a +10): questo argomento è fonte di gioia, ansia, sofferenza?
- Un **punteggio di importanza**: quanto questa informazione è strutturante per la persona?
- Una **sfumatura d'uso**: come utilizzare questa informazione in modo premuroso e appropriato?
- Una **categoria psicologica**: preferenza, fatto personale, relazione, sensibilità, pattern comportamentale

Non si tratta di psicologia spicciola. È un sistema di estrazione automatica che analizza ogni conversazione attraverso il prisma della personalità attiva dell'assistente, identifica le informazioni psicologicamente significative e le archivia con il loro contesto emotivo.

**Esempio concreto**: se menzionate di sfuggita che vostra madre è malata, LIA non archivia semplicemente "madre malata". Registra una sensibilità con un peso emotivo fortemente negativo, una sfumatura d'uso che prescrive di non affrontare mai l'argomento con leggerezza e una categoria "relazione/famiglia" che struttura l'informazione nel vostro profilo.

### 5.3. La sicurezza emotiva

LIA integra una **direttiva di pericolo emotivo**. Quando un ricordo associato a una forte carica emotiva negativa (peso <= -5) viene attivato, il sistema passa in modalità protettiva con quattro divieti assoluti:

1. Non scherzare mai sull'argomento
2. Non minimizzare mai
3. Non paragonare mai con altre situazioni
4. Non banalizzare mai

A nostra conoscenza, questo tipo di meccanismo di protezione emotiva adattiva non è comune negli assistenti IA consumer, che trattano generalmente tutti gli argomenti con la stessa neutralità. LIA adatta il suo comportamento alla realtà emotiva della persona che accompagna.

### 5.4. I diari di bordo: quando l'assistente riflette

LIA integra un meccanismo originale: i suoi **diari di bordo** (Personal Journals).

L'assistente tiene le proprie riflessioni, organizzate in quattro temi: auto-riflessione, osservazioni sull'utente, idee e analisi, apprendimenti. Queste note sono redatte in prima persona, colorate dalla personalità attiva, e influenzano concretamente le risposte future.

Non si tratta di un'ulteriore memoria. È una forma di **introspezione artificiale** — l'assistente che riflette sulle proprie interazioni, annota i propri apprendimenti, sviluppa le proprie prospettive. Quando ha scritto "l'utente preferisce spiegazioni concise sugli argomenti tecnici", questa osservazione influenza organicamente le risposte future, senza regole codificate rigidamente.

I diari sono attivati da due meccanismi: estrazione post-conversazione (dopo ogni scambio) e consolidamento periodico (ogni 4 ore, revisione e riorganizzazione delle note). Un **guard semantico di deduplicazione** garantisce che il diario rimanga denso anziché ripetitivo: quando un nuovo insight è troppo simile a una nota esistente, il sistema arricchisce la voce esistente invece di creare un duplicato. L'utente mantiene il controllo totale: lettura, modifica, cancellazione, attivazione/disattivazione.

### 5.5. Il sistema di interessi

Parallelamente, LIA sviluppa un **sistema di apprendimento dei centri d'interesse**: tramite analisi bayesiana delle richieste, rileva progressivamente gli argomenti che vi stanno a cuore e può, col tempo, inviarvi proattivamente informazioni pertinenti — un articolo, una notizia, un'analisi — su questi temi.

### 5.6. La ricerca ibrida

L'intero sistema di memoria si basa su una **ricerca ibrida** che combina similarità semantica (pgvector) e corrispondenza per parole chiave (BM25). Questo approccio duale offre una precisione superiore rispetto a ciascun metodo preso singolarmente: il semantico comprende il significato, il BM25 cattura nomi propri e termini esatti.

---

## 6. L'orchestrazione che funziona in produzione

### 6.1. La vera sfida dell'IA agentica

La promessa agentica è seducente: un assistente che pianifica, esegue e sintetizza. La realtà è brutale: 35 % di tasso di fallimento nel coordinamento, costi esplosivi per cicli non controllati, debugging quasi impossibile a causa del non-determinismo.

LIA non pretende di aver risolto l'IA agentica in generale. Ma ha risolto il **suo** problema specifico: orchestrare 15 agenti specializzati in modo affidabile, economico e osservabile in produzione, su hardware modesto.

### 6.2. Come funziona

Quando inviate un messaggio, questo attraversa una pipeline in 5 fasi:

**Fase 1 — Comprendere**: Il router analizza il vostro messaggio in poche centinaia di millisecondi e decide se si tratta di una semplice conversazione o di una richiesta che necessita azioni. L'analizzatore di richieste identifica i domini coinvolti (email, calendario, meteo...) e un router semantico affina il rilevamento grazie a embeddings semantici (+48 % di precisione).

**Fase 2 — Pianificare**: Per le richieste complesse, un pianificatore intelligente genera un piano di esecuzione strutturato — un albero di dipendenze con passaggi, condizioni e iterazioni. Se un piano simile è già stato validato in passato, un apprendimento bayesiano permette di riutilizzarlo direttamente (bypass del LLM, risparmi massicci).

**Fase 3 — Validare**: Il piano viene sottoposto a validazione semantica e poi, se necessario, alla vostra approvazione tramite il sistema Human-in-the-Loop (vedi sezione 7).

**Fase 4 — Eseguire**: I passaggi del piano vengono eseguiti in parallelo quando possibile, in sequenza quando ci sono dipendenze. Ogni agente specializzato gestisce il proprio dominio (contatti, email, calendario...) e i risultati alimentano i passaggi successivi.

**Fase 5 — Rispondere**: Un sistema di sintesi anti-allucinazione a tre livelli produce una risposta fedele ai dati reali, senza invenzioni né estrapolazioni.

In background, tre processi fire-and-forget vengono eseguiti senza impattare la latenza: estrazione della memoria, estrazione del diario, rilevamento degli interessi.

### 6.3. Il controllo dei costi

Laddove la maggior parte dei sistemi agentici vede i propri costi esplodere, LIA ha sviluppato un insieme di meccanismi di ottimizzazione che riducono il consumo di token dell'89 %:

- **Filtraggio del catalogo**: solo gli strumenti pertinenti alla vostra richiesta vengono presentati al LLM (96 % di riduzione)
- **Apprendimento di pattern**: i piani validati vengono memorizzati e riutilizzati (bypass LLM se confidenza > 90 %)
- **Message Windowing**: ogni nodo vede solo gli ultimi N messaggi necessari (5/10/20 a seconda del nodo)
- **Context Compaction**: riassunto LLM dei messaggi precedenti quando il contesto supera la soglia
- **Prompt Caching**: sfruttamento della cache nativa OpenAI/Anthropic (90 % di riduzione)
- **Embeddings semantici**: embeddings multilingue IA per il routing semantico e la deduplicazione

### 6.4. L'osservabilità come rete di sicurezza

LIA dispone di un'osservabilità nativa di livello produzione: 350+ metriche Prometheus, 18 dashboard Grafana, tracce distribuite (Tempo), logging strutturato (Loki) e tracing LLM specializzato (Langfuse). 59 Architecture Decision Records documentano ogni scelta progettuale.

In un ecosistema dove l'89 % dei deployment di agenti IA in produzione implementa una qualche forma di osservabilità, LIA va oltre con un debug panel integrato che rende queste metriche accessibili direttamente nell'interfaccia utente, non in uno strumento di monitoring separato.

---

## 7. Il controllo umano come filosofia

### 7.1. Cosa fanno gli altri

Gemini Agent "chiede conferma prima delle azioni critiche, come inviare un'email o effettuare un acquisto". ChatGPT Operator "rifiuta di eseguire determinate attività per ragioni di sicurezza, come inviare email e cancellare eventi". È un approccio binario: o l'azione è autorizzata, o viene rifiutata.

### 7.2. L'Human-in-the-Loop di LIA: 6 livelli di sfumatura

LIA non rifiuta le azioni sensibili — ve le **sottopone** con il livello di dettaglio appropriato:

| Livello                          | Trigger                                     | Cosa vedete                                     |
| -------------------------------- | ------------------------------------------- | ----------------------------------------------- |
| **Approvazione del piano**       | Azioni distruttive o sensibili              | Il piano completo con ogni passaggio dettagliato |
| **Chiarimento**                  | Ambiguità rilevata                          | Una domanda precisa per risolvere l'ambiguità    |
| **Revisione della bozza**        | Email, evento, contatto da creare/modificare | La bozza completa, modificabile prima dell'invio |
| **Conferma distruttiva**         | Cancellazione di 3+ elementi                | Avvertimento esplicito di irreversibilità        |
| **Conferma FOR_EACH**            | Operazioni di massa                         | Numero di operazioni e natura di ciascuna azione |
| **Review delle modifiche**       | Modifiche suggerite dall'IA                  | Confronto prima/dopo con evidenziazione          |

### 7.3. La sfumatura che cambia tutto

La revisione della bozza illustra questa filosofia. Quando chiedete a LIA di inviare un'email, non la invia direttamente (come farebbe un agente autonomo) e non rifiuta nemmeno (come farebbe ChatGPT Operator). Vi mostra la bozza completa con template markdown adattati al dominio (email, evento, contatto, attività), emoji per i campi, confronto before/after per le modifiche e un avvertimento di irreversibilità per le cancellazioni. Potete modificare, approvare o rifiutare.

È la differenza tra un agente che agisce al vostro posto e un assistente che vi **propone** e vi lascia decidere. La fiducia non nasce dall'assenza di rischio — nasce dalla **visibilità** su ciò che sta per accadere.

### 7.4. Il feedback implicito

Ogni approvazione o rifiuto alimenta il sistema di apprendimento dei pattern. Se approvate sistematicamente un certo tipo di piano, LIA impara e propone con maggiore confidenza. L'HITL non è solo un meccanismo di sicurezza — è un sistema di **calibrazione continua** dell'intelligenza del sistema.

---

## 8. Agire nella vostra vita digitale

### 8.1. Tre ecosistemi, un'unica interfaccia

LIA si connette ai tre grandi ecosistemi da ufficio sul mercato:

**Google Workspace** (OAuth 2.1 + PKCE): Gmail, Google Calendar, Google Contacts (14+ schemi), Google Drive, Google Tasks — con copertura CRUD completa.

**Microsoft 365** (OAuth 2.0 + PKCE): Outlook, Calendar, Contacts, To Do — account personali e professionali (Azure AD multi-tenant).

**Apple iCloud** (IMAP/SMTP, CalDAV, CardDAV): Apple Mail, Apple Calendar, Apple Contacts — per chi vive nell'ecosistema Apple.

Un principio di esclusività reciproca garantisce la coerenza: un solo fornitore attivo per categoria (email, calendario, contatti, attività). Potete avere Google per il calendario e Microsoft per le email.

### 8.2. Casa connessa

LIA controlla la vostra illuminazione Philips Hue tramite comandi in linguaggio naturale: accendere/spegnere, regolare luminosità e colori, gestire stanze e scene. Connessione locale (stessa rete) o cloud (OAuth2 Philips Hue).

### 8.3. Navigazione web ed estrazione

Un agente di navigazione autonomo (Playwright/Chromium headless) può navigare su siti web, cliccare, compilare moduli, estrarre dati da pagine JavaScript complesse — a partire da una semplice istruzione in linguaggio naturale. Una modalità di estrazione più semplice converte qualsiasi URL in testo Markdown utilizzabile.

### 8.4. Allegati

Immagini (analisi tramite modello di visione) e PDF (estrazione del testo) sono supportati come allegati, con compressione lato client e isolamento rigoroso per utente.

### 8.5. Spazi di conoscenza (RAG Spaces)

Create basi documentali personali caricando i vostri documenti (15+ formati: PDF, DOCX, PPTX, XLSX, CSV, EPUB...). Sincronizzazione automatica di cartelle Google Drive con rilevamento incrementale. Ricerca ibrida semantica + parole chiave. Una base di conoscenza di sistema (119+ Q/A) consente a LIA di rispondere alle domande sulle proprie funzionalità.

---

## 9. La proattività contestuale

### 9.1. Oltre la notifica

La proattività di LIA non è un sistema di avvisi configurato manualmente. È un **giudizio LLM contestualizzato** che aggrega in parallelo 7 fonti di contesto — calendario, meteo (con rilevamento dei cambiamenti: inizio/fine pioggia, calo di temperatura, allerta vento), attività, email, interessi, ricordi, diari — e lascia a un modello linguistico la decisione se ci sia qualcosa di genuinamente utile da comunicare.

Il sistema in due fasi separa la **decisione** (modello economico, temperatura bassa, output strutturato: "notificare" o "non notificare") dalla **generazione** (modello espressivo, personalità dell'assistente, lingua dell'utente).

### 9.2. Anti-spam per design

Quota giornaliera configurabile (1-8/giorno), finestra oraria personalizzabile, cooldown tra le notifiche, anti-ridondanza tramite iniezione della cronologia recente nel prompt di decisione, skip se l'utente è in conversazione attiva. La proattività è opt-in, ogni parametro è modificabile e la disattivazione preserva i dati.

### 9.3. Iniziativa conversazionale

Durante una conversazione, LIA non si limita a rispondere alla domanda posta. Dopo ogni esecuzione, un **agente di iniziativa** analizza i risultati e verifica proattivamente le informazioni correlate — se il meteo annuncia pioggia sabato, l'iniziativa consulta il calendario per segnalare eventuali attività all'aperto. Se un'email menziona un appuntamento, verifica la disponibilità. Interamente guidato dal prompt (nessuna logica codificata rigidamente), limitato alle azioni di lettura, arricchito dalla memoria e dai centri d'interesse dell'utente.

### 9.4. Azioni pianificate

Oltre alle notifiche, LIA esegue azioni ricorrenti programmate con gestione del fuso orario, retry automatico e disattivazione dopo fallimenti consecutivi. I risultati vengono notificati via push (FCM), SSE e Telegram.

---

## 10. La voce come interfaccia naturale

### 10.1. Input vocale

**Push-to-Talk**: tenete premuto il pulsante del microfono per parlare. Ottimizzato per il mobile con anti-long-press, gestione dei gesti tattili, annullamento tramite trascinamento.

**Parola chiave "OK Guy"**: rilevamento a mani libere eseguito **interamente nel vostro browser** tramite Sherpa-onnx WASM — nessun suono viene trasmesso a un server finché la parola chiave non viene rilevata. La trascrizione utilizza Whisper (99+ lingue, offline) nel rispetto della vostra lingua preferita.

**Ottimizzazioni di latenza**: riutilizzo del flusso del microfono, pre-connessione WebSocket, setup parallelo — il ritardo tra il rilevamento della parola chiave e l'inizio della registrazione è di ~50-100 ms.

### 10.2. Output vocale

Due modalità: Standard (Edge TTS, gratuito, alta qualità) e HD (OpenAI TTS o Gemini TTS, premium). Passaggio automatico da HD a Standard in caso di errore.

---

## 11. L'apertura come strategia

### 11.1. Standard aperti, nessun lock-in

| Standard                         | Utilizzo in LIA                                                                              |
| -------------------------------- | -------------------------------------------------------------------------------------------- |
| **MCP** (Model Context Protocol) | Connessione di strumenti esterni per utente, con OAuth 2.1, prevenzione SSRF, rate limiting  |
| **agentskills.io**               | Skill iniettabili con progressive disclosure (L1/L2/L3), generatore integrato                |
| **OAuth 2.1 + PKCE**             | Autenticazione delegata per tutti i connettori                                               |
| **OpenTelemetry**                | Osservabilità standardizzata                                                                 |
| **AGPL-3.0**                     | Codice sorgente completo, verificabile, modificabile                                         |

### 11.2. MCP: l'estensibilità senza limiti

Ogni utente può connettere i propri server MCP, estendendo le capacità di LIA ben oltre gli strumenti integrati. Le descrizioni di dominio vengono generate automaticamente tramite LLM per un routing intelligente. Le MCP Apps permettono di visualizzare widget interattivi (come Excalidraw per i diagrammi) direttamente nella chat. La **modalità iterativa (ReAct)** consente ai server con API complesse di essere gestiti da un agente dedicato che prima legge la documentazione e poi chiama gli strumenti con i parametri corretti — invece di pre-calcolare tutto nel piano statico.

### 11.3. Skill: competenze su misura

Le Skill (standard agentskills.io) permettono di iniettare istruzioni esperte. Una Skill di "briefing mattutino" può coordinare calendario, meteo, email e attività in un unico comando deterministico. Il generatore integrato vi guida nella creazione di Skill in linguaggio naturale.

### 11.4. Multi-canale

L'interfaccia web responsive è completata da un'integrazione Telegram nativa (conversazione testuale, messaggi vocali trascritti, pulsanti HITL inline, notifiche proattive) e notifiche push Firebase.

---

## 12. L'intelligenza che si auto-ottimizza

### 12.1. L'apprendimento bayesiano dei piani

A ogni piano validato ed eseguito con successo, LIA registra il pattern. Uno scoring bayesiano calcola la confidenza in ogni pattern. Sopra il 90 % di confidenza, il piano viene riutilizzato direttamente senza chiamata LLM — risparmi massicci di token e latenza. Il sistema parte con 50+ "golden pattern" predefiniti e si arricchisce continuamente.

### 12.2. Il routing semantico locale

Embeddings semantici multilingue (100+ lingue) permettono un routing semantico che migliora la precisione del rilevamento dell'intento del 48 % rispetto al routing puramente LLM.

### 12.3. L'anti-allucinazione a tre livelli

Il nodo di risposta dispone di un sistema anti-allucinazione a tre livelli: formattazione dei dati con limiti espliciti, direttive di sistema che impongono l'uso esclusivo di dati verificati e gestione esplicita dei casi limite (rifiuto, errore, assenza di risultati). Il LLM è vincolato a sintetizzare unicamente ciò che proviene dai risultati reali degli strumenti.

---

## 13. Il tessuto: come tutto si intreccia

La potenza di LIA non risiede nella somma delle sue funzionalità. Risiede nella loro **interazione** — il modo in cui ogni sottosistema rafforza gli altri per creare qualcosa che supera la somma delle parti.

### 13.1. Memoria + Proattività + Diari

LIA non si limita a sapere che avete una riunione domani. Grazie alla sua memoria, conosce la vostra ansia riguardo a quell'argomento. Grazie ai suoi diari, ha annotato che le presentazioni brevi funzionano meglio con quell'interlocutore. Grazie al suo sistema di interessi, ha individuato un articolo pertinente. La notifica proattiva integra tutte queste dimensioni in un messaggio personalizzato, coerente e utile — non un avviso generico.

### 13.2. HITL + Pattern Learning + Costi

Ogni interazione HITL alimenta l'apprendimento. La vostra approvazione di un piano lo iscrive nella memoria bayesiana. La volta successiva, verrà riutilizzato senza chiamata LLM: esperienza migliore (più rapida), costo inferiore (meno token), fiducia accresciuta (piano già validato). L'HITL non rallenta il sistema — lo **accelera** nel tempo.

### 13.3. RAG + Risposta

I vostri spazi di conoscenza arricchiscono direttamente le risposte di LIA. Se avete caricato le procedure della vostra azienda e ponete una domanda sul processo di validazione, LIA cerca nei vostri documenti e integra le informazioni pertinenti nella sua risposta. I costi di embedding sono tracciati per documento e per richiesta, visibili nella chat e nella dashboard.

### 13.4. Routing semantico + Filtraggio del catalogo + Trasparenza

Il routing semantico locale rileva i domini pertinenti. Il filtraggio del catalogo riduce del 96 % gli strumenti presentati al LLM. Il debug panel vi mostra esattamente questa selezione. Risultato: piani più precisi, meno costosi, che potete comprendere e verificare.

### 13.5. Voce + Telegram + Web + Sovranità

La stessa intelligenza è accessibile tramite tre canali complementari: il web per le operazioni complesse, Telegram per la mobilità, la voce per il vivavoce. La vostra memoria, i vostri diari, le vostre preferenze vi seguono da un canale all'altro — e tutto resta sul vostro server.

---

## 14. Cosa LIA non pretende di essere

### 14.1. LIA non è il "miglior chatbot"

Come generatore di testo conversazionale, GPT-5.4 o Claude Opus 4.6 utilizzati tramite la loro interfaccia nativa saranno probabilmente più fluidi di LIA — perché LIA non è un chatbot. È un sistema di orchestrazione che utilizza questi modelli come componenti.

### 14.2. LIA non ha le risorse dei GAFAM

Il team di integrazione di Gemini con Google Workspace conta migliaia di ingegneri e un accesso diretto alle API interne. LIA utilizza le stesse API pubbliche di qualsiasi sviluppatore. La copertura funzionale non sarà mai identica.

### 14.3. LIA non è "plug and play"

L'auto-hosting ha un prezzo: la configurazione iniziale, la manutenzione del server, la gestione degli aggiornamenti. LIA dispone di un sistema di setup semplificato (`task setup` poi `task dev`), ma non è semplice come iscriversi su chatgpt.com.

### 14.4. Perché questa onestà conta

Perché la fiducia si costruisce sulla verità, non sul marketing. LIA eccelle là dove ha scelto di eccellere: la sovranità, la trasparenza, la profondità relazionale, l'affidabilità in produzione e l'apertura. Sul resto, si appoggia ai migliori LLM del mercato — che orchestra piuttosto che cercare di sostituire.

---

## 15. Visione: dove va LIA

### 15.1. L'intelligenza emergente

La combinazione memoria psicologica + diari introspettivi + apprendimento bayesiano + interessi + proattività crea le condizioni per una forma di **intelligenza emergente**: nel corso dei mesi, LIA sviluppa una comprensione sempre più sfumata di chi siete, di cosa avete bisogno e di come presentarvelo. Non è intelligenza artificiale generale. È un'intelligenza **pratica e relazionale**, al servizio di una persona specifica.

### 15.2. L'architettura estensibile

Ogni componente è progettato per l'estensione senza riscrittura:

- **Nuovi connettori** (Slack, Notion, Trello) tramite l'astrazione per protocollo
- **Nuovi canali** (Discord, WhatsApp) tramite l'architettura BaseChannel
- **Nuovi agenti** senza modificare il cuore del sistema
- **Nuovi fornitori IA** tramite la factory LLM
- **Nuovi strumenti MCP** per semplice connessione utente

### 15.3. La convergenza

La visione a lungo termine di LIA è quella di un **sistema nervoso digitale personale**: un punto unico che orchestra l'intera vostra vita digitale, con la memoria di un assistente che vi conosce da anni, la proattività di un collaboratore attento, la trasparenza di uno strumento che comprendete e la sovranità di un sistema che possedete.

In un mondo in cui l'IA sarà ovunque, la domanda non sarà più "quale IA usare?" ma "**chi controlla la mia IA?**". LIA risponde: voi.

---

## Conclusione: perché LIA esiste

LIA non esiste perché il mondo è a corto di assistenti IA. Ne è saturo. ChatGPT, Gemini, Copilot, Claude — ciascuno è notevole a modo suo.

LIA esiste perché il mondo è a corto di un assistente IA che sia **vostro**. Veramente vostro. Sul vostro server, con i vostri dati, sotto il vostro controllo, con una trasparenza totale su ciò che fa e ciò che costa, una comprensione psicologica che va oltre i fatti e la libertà di scegliere quale modello di IA lo anima.

Non è un chatbot. Non è una piattaforma cloud. È un **compagno digitale sovrano** — ed è precisamente ciò che mancava.

**Your Life. Your AI. Your Rules.**

---

*Documento redatto sulla base del codice sorgente di LIA v1.13.8, di 190+ documenti tecnici, di 63 ADR, del changelog completo e di un'analisi del panorama concorrenziale IA di marzo 2026. Tutte le funzionalità descritte sono implementate e verificabili nel codice. I dati di mercato provengono da Gartner, IBM e dalle pubblicazioni ufficiali di OpenAI, Google, Microsoft e Anthropic.
