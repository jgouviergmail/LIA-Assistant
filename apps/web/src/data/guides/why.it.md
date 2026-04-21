# LIA — L'Assistente IA che ti appartiene

> **Your Life. Your AI. Your Rules.**

**Versione** : 3.2
**Data** : 2026-04-20
**Applicazione** : LIA v1.17.0
**Licenza** : AGPL-3.0 (Open Source)

---

## Indice

1. [Il contesto](#1-il-contesto)
2. [Amministrazione semplice](#2-amministrazione-semplice)
3. [Cosa sa fare LIA](#3-cosa-sa-fare-lia)
4. [Un server per chi ami](#4-un-server-per-chi-ami)
5. [Sovrano e frugale](#5-sovrano-e-frugale)
6. [Trasparenza radicale](#6-trasparenza-radicale)
7. [Profondità emotiva](#7-profondità-emotiva)
8. [Affidabilità in produzione](#8-affidabilità-in-produzione)
9. [Apertura radicale](#9-apertura-radicale)
10. [Visione](#10-visione)

---

## 1. Il contesto

L'era degli assistenti IA agentici è arrivata. ChatGPT, Gemini, Copilot, Claude — ognuno propone un agente capace di agire nella tua vita digitale: inviare email, gestire l'agenda, cercare sul web, controllare i tuoi dispositivi.

Questi assistenti sono straordinari. Ma condividono tutti lo stesso modello: i tuoi dati vivono sui loro server, l'intelligenza è una scatola nera, e quando te ne vai, tutto resta lì.

LIA sceglie un percorso diverso. Non è un concorrente diretto dei grandi — è un **assistente IA personale che ospiti tu, che capisci, e che controlli tu**. LIA orchestra i migliori modelli di IA sul mercato, agisce nella tua vita digitale, e lo fa con qualità fondamentali che la distinguono.

---

## 2. Amministrazione semplice

### 2.1. Un'installazione guidata, poi zero attrito

L'auto-hosting ha una cattiva reputazione. LIA non pretende di eliminare ogni passaggio tecnico: la configurazione iniziale — impostare le chiavi API, configurare i connettori OAuth, scegliere l'infrastruttura — richiede un po' di tempo e qualche competenza di base. Ma ogni passaggio è **documentato nel dettaglio** in una guida di installazione passo dopo passo.

Una volta terminata questa fase, **tutto il quotidiano si gestisce da un'interfaccia web intuitiva**. Niente più terminale né file di configurazione.

### 2.2. Cosa può configurare ogni utente

Ogni utente ha il proprio spazio di configurazione, organizzato in due schede:

**Preferenze personali:**

- **Connettori personali**: collega i tuoi account Google, Microsoft o Apple in pochi clic tramite OAuth — email, calendario, contatti, attività, Google Drive. Oppure connetti Apple via IMAP/CalDAV/CardDAV. Chiavi API per i servizi esterni (meteo, ricerca)
- **Personalità**: scegli tra le personalità disponibili (professore, amico, filosofo, coach, poeta...) — ognuna influenza il tono, lo stile e il comportamento emotivo di LIA
- **Voce**: configura la modalità vocale — parola chiave di attivazione, sensibilità, soglia di silenzio, lettura automatica delle risposte
- **Notifiche**: gestisci le notifiche push e i dispositivi registrati
- **Canali**: collega Telegram per chattare e ricevere notifiche sul cellulare
- **Generazione di immagini**: attiva e configura la creazione di immagini tramite IA
- **Server MCP personali**: connetti i tuoi server MCP per estendere le capacità di LIA
- **Aspetto**: lingua, fuso orario, tema (5 palette, modalità scura/chiara), font (9 scelte), formato di visualizzazione delle risposte (schede HTML, HTML, Markdown)
- **Debug**: accedi al pannello di debug per ispezionare ogni scambio (se abilitato dall'amministratore)

**Funzionalità avanzate:**

- **Psyche Engine**: regola i tratti di personalità (Big Five) che modulano la reattività emotiva del tuo assistente
- **Memoria**: consulta, modifica, fissa o elimina i ricordi di LIA — attiva o disattiva l'estrazione automatica di informazioni
- **Diari personali**: configura l'estrazione di riflessioni dopo ogni conversazione e il consolidamento periodico
- **Interessi**: definisci i tuoi argomenti preferiti, configura la frequenza delle notifiche, le finestre orarie e le fonti (Wikipedia, Perplexity, ragionamento IA)
- **Notifiche proattive**: regola frequenza, finestra oraria e fonti di contesto (calendario, meteo, attività, email, interessi, memorie, diari)
- **Azioni pianificate**: crea automazioni ricorrenti eseguite dall'assistente
- **Skills**: attiva/disattiva competenze specializzate, crea le tue Skills personali
- **Spazi di conoscenza**: carica i tuoi documenti (PDF, Word, Excel, PowerPoint, EPUB, HTML e 15+ formati) o sincronizza una cartella di Google Drive — indicizzazione automatica con ricerca ibrida
- **Export dei consumi**: scarica i tuoi dati di consumo LLM e API in CSV

### 2.3. Cosa controlla l'amministratore

L'amministratore ha accesso a una terza scheda dedicata alla gestione dell'istanza:

**Utenti e accessi:**

- **Gestione utenti**: creare, attivare/disattivare account, visualizzare i servizi connessi e le funzionalità attivate per ogni utente
- **Limiti di utilizzo**: definire quote per utente (token LLM, chiamate API, generazioni di immagini) con monitoraggio in tempo reale e blocco automatico
- **Messaggi broadcast**: inviare messaggi importanti a tutti gli utenti o a una selezione, con data di scadenza opzionale
- **Export dei consumi globale**: esportare i consumi di tutti gli utenti in CSV

**IA e connettori:**

- **Configurazione LLM**: configurare le chiavi API dei provider (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), assegnare un modello per ogni ruolo nella pipeline, gestire i livelli di ragionamento — chiavi archiviate in forma cifrata
- **Attivazione/disattivazione connettori**: abilitare o disabilitare le integrazioni a livello globale (Google OAuth, Apple, Microsoft 365, Hue, meteo, Wikipedia, Perplexity, Brave Search). La disattivazione revoca le connessioni attive e notifica gli utenti
- **Tariffazione**: gestire i prezzi per modello LLM (costo per milione di token), per API Google Maps (Places, Routes, Geocoding), e per generazione di immagini — con storico dei prezzi

**Contenuti ed estensioni:**

- **Personalità**: creare, modificare, tradurre ed eliminare le personalità disponibili per tutti gli utenti — definire la personalità predefinita
- **Skills di sistema**: gestire le competenze specializzate a livello di istanza — import/export, attivazione/disattivazione, traduzione
- **Spazi di conoscenza di sistema**: gestire la base di conoscenza FAQ, monitorare lo stato dell'indicizzazione e le migrazioni di modelli
- **Voce globale**: configurare la modalità TTS predefinita (standard o HD) per tutti gli utenti
- **Debug di sistema**: configurazione dei log e della diagnostica

### 2.4. Un assistente, non un progetto tecnico

L'obiettivo di LIA non è trasformarti in un amministratore di sistema. È offrirti la potenza di un assistente IA completo **con la semplicità di un'app consumer**. L'interfaccia è installabile come applicazione nativa su computer, tablet e smartphone (PWA), e tutto è pensato per essere usato senza competenze tecniche nel quotidiano.

---

## 3. Cosa sa fare LIA

LIA agisce concretamente nella tua vita digitale grazie a 19+ agenti specializzati che coprono tutte le esigenze di tutti i giorni: gestione dei tuoi dati personali (email, calendario, contatti, attività, file), accesso alle informazioni esterne (ricerca web, meteo, luoghi, itinerari), creazione di contenuti (immagini, diagrammi), controllo della casa connessa, navigazione web autonoma, e anticipazione proattiva dei tuoi bisogni.

Scegli tu come ragiona LIA, tramite un semplice toggle (⚡) nell'intestazione della chat:

- **Modalità Pipeline** (predefinita) — Un vero capolavoro di ingegneria: LIA pianifica tutti i passaggi in anticipo, li valida semanticamente ed esegue gli strumenti in parallelo. Risultato: la stessa potenza di un agente autonomo, ma con 4-8 volte meno token consumati. La modalità più economica e prevedibile.
- **Modalità ReAct** (⚡) — L'assistente ragiona passo dopo passo: chiama uno strumento, analizza il risultato e decide cosa fare dopo. Più autonomo, più adattabile, ma più costoso in token. Ideale per ricerche esplorative o domande complesse il cui valore aggiunto giustifica il costo.

### 3.1. Conversazione naturale

Parla a LIA come faresti con un assistente umano — niente comandi da memorizzare, niente sintassi da rispettare. LIA capisce e risponde in 99+ lingue, con un'interfaccia disponibile in 6 lingue (francese, inglese, tedesco, spagnolo, italiano, cinese). Le risposte vengono visualizzate in schede HTML interattive, in HTML diretto, o in Markdown secondo le tue preferenze.

### 3.2. Servizi connessi personali

- **Email**: leggere, cercare, redigere, inviare, rispondere, inoltrare — via Gmail, Outlook o Apple Mail
- **Calendario**: consultare, creare, modificare, eliminare eventi — via Google Calendar, Outlook Calendar o Apple Calendar
- **Contatti**: cercare, creare, modificare contatti — via Google Contacts, Outlook Contacts o Apple Contacts
- **Attività**: gestire le tue liste di attività — via Google Tasks o Microsoft To Do
- **File**: accedere a Google Drive per cercare e leggere i tuoi documenti
- **Casa connessa**: controllare la tua illuminazione Philips Hue — accensione/spegnimento, luminosità, colori, scene, gestione per stanza

### 3.3. Intelligenza web e ambiente

- **Ricerca web**: ricerca multi-sorgente (Brave Search, Perplexity, Wikipedia) per risposte complete e con fonti citate
- **Meteo**: condizioni attuali e previsioni a 5 giorni, con rilevamento dei cambiamenti (inizio/fine pioggia, calo di temperatura, allerte vento)
- **Luoghi e attività commerciali**: ricerca di luoghi nelle vicinanze con dettagli, orari, recensioni
- **Itinerari**: calcolo di itinerari multi-modali (auto, a piedi, bici, trasporti pubblici) con geolocalizzazione automatica

### 3.4. Voce

LIA offre una modalità vocale completa:

- **Push-to-Talk**: tieni premuto il pulsante microfono per parlare, ottimizzato per il mobile
- **Parola chiave "OK Guy"**: rilevamento hands-free eseguito **interamente nel tuo browser** via Sherpa-onnx WASM — nessun audio viene trasmesso finché la parola chiave non viene rilevata
- **Sintesi vocale**: modalità standard (Edge TTS, gratuita) o HD (OpenAI TTS / Gemini TTS)
- **Messaggi vocali Telegram**: invia messaggi audio, LIA li trascrive e risponde

### 3.5. Creazione e media

- **Generazione di immagini**: crea immagini da una descrizione testuale, modifica foto esistenti
- **Diagrammi Excalidraw**: genera schemi e diagrammi direttamente nella conversazione
- **Allegati**: allega foto e PDF — LIA analizza il contenuto visivo ed estrae il testo dai documenti
- **MCP Apps**: widget interattivi direttamente nella chat (moduli, visualizzazioni, mini-applicazioni)

### 3.6. Proattività e iniziative

LIA non si limita a rispondere — anticipa:

- **Notifiche proattive**: LIA incrocia le tue fonti di contesto (calendario, meteo, attività, email, interessi) e ti notifica quando è davvero utile — con un sistema anti-spam integrato (quota giornaliera, finestra oraria, cooldown)
- **Iniziativa conversazionale**: durante uno scambio, LIA verifica proattivamente le informazioni correlate — se il meteo prevede pioggia sabato, consulta il tuo calendario per segnalarti eventuali attività all'aperto
- **Interessi**: LIA rileva progressivamente gli argomenti che ti appassionano e può inviarti contenuti pertinenti
- **Sotto-agenti**: per le attività complesse, LIA delega ad agenti effimeri specializzati che lavorano in parallelo

### 3.7. Navigazione web autonoma

Un agente di navigazione (Playwright/Chromium headless) può navigare su siti web, fare clic, compilare moduli, estrarre dati da pagine dinamiche — a partire da una semplice istruzione in linguaggio naturale. Una modalità di estrazione semplificata converte qualsiasi URL in testo utilizzabile.

### 3.8. Amministrazione server (DevOps)

Installando Claude CLI (Claude Code) direttamente sul server, gli amministratori possono diagnosticare la propria infrastruttura in linguaggio naturale dalla chat di LIA: consultare i log Docker, verificare lo stato dei container, monitorare lo spazio su disco, analizzare gli errori. Questa funzionalità è riservata agli account amministratore.

---

## 4. Un server per chi ami

### 4.1. LIA è un server web condiviso

A differenza degli assistenti cloud personali (un account = un utente), LIA è progettata come un **server centralizzato** che installi una volta sola e condividi con la tua famiglia, i tuoi amici, o il tuo team.

Ogni utente ha il proprio account con:

- Il suo profilo, le sue preferenze, la sua lingua
- **La sua personalità di assistente** con il suo umore, le sue emozioni e la sua relazione unica — grazie al Psyche Engine, ogni utente interagisce con un assistente che sviluppa un legame emotivo distinto
- La sua memoria, i suoi ricordi, i suoi diari personali — totalmente isolati
- I suoi connettori personali (Google, Microsoft, Apple)
- I suoi spazi di conoscenza privati

### 4.2. Gestione dei consumi per utente

L'amministratore mantiene il controllo sui consumi:

- **Limiti di utilizzo** configurabili per utente: numero di messaggi, token, costo massimo — al giorno, alla settimana, al mese, o in totale cumulativo
- **Quote visive**: ogni utente vede il proprio consumo in tempo reale con indicatori chiari
- **Attivazione/disattivazione dei connettori**: l'amministratore abilita o disabilita le integrazioni (Google, Microsoft, Hue...) a livello di istanza

### 4.3. La tua IA di famiglia

Immagina: un Raspberry Pi nel tuo salotto, e tutta la famiglia che gode di un assistente IA intelligente — ognuno con la propria esperienza personalizzata, i propri ricordi, il proprio stile di conversazione, e un assistente che sviluppa con lui la propria relazione emotiva. Il tutto sotto il tuo controllo, senza abbonamento cloud, senza dati che finiscono da terzi.

---

## 5. Sovrano e frugale

### 5.1. I tuoi dati restano da te

Quando usi ChatGPT, le tue conversazioni vivono sui server di OpenAI. Con Gemini, da Google. Con Copilot, da Microsoft.

Con LIA, **tutto rimane nel tuo PostgreSQL**: conversazioni, memoria, profilo psicologico, documenti, preferenze. Puoi esportare, fare backup, migrare o eliminare tutti i tuoi dati in qualsiasi momento. Il GDPR non è un vincolo — è una conseguenza naturale dell'architettura. I dati sensibili sono cifrati, le sessioni isolate, e il filtraggio automatico delle informazioni personalmente identificabili (PII) è integrato.

### 5.2. Basta anche un Raspberry Pi

LIA gira in produzione su un **Raspberry Pi 5** — un computer a scheda singola da 80 euro. 19+ agenti specializzati, uno stack di osservabilità completo, un sistema di memoria psicologica, il tutto su un micro-server ARM. Le immagini Docker multi-architettura (amd64/arm64) permettono il deployment su qualsiasi hardware: NAS Synology, VPS a pochi euro al mese, server aziendale, o cluster Kubernetes.

La sovranità digitale non è più un privilegio per le aziende — è un diritto accessibile a tutti.

### 5.3. Ottimizzato per la frugalità

LIA non si limita a girare su hardware modesto — **ottimizza attivamente** il consumo di risorse IA:

- **Filtraggio del catalogo**: solo gli strumenti pertinenti alla tua richiesta vengono presentati al LLM, riducendo drasticamente il numero di token consumati
- **Apprendimento di pattern**: i piani validati vengono memorizzati e riutilizzati senza richiamare il LLM
- **Message Windowing**: ogni componente vede solo il contesto strettamente necessario
- **Cache dei prompt**: sfruttamento della cache nativa dei provider per limitare i costi ricorrenti

Queste ottimizzazioni combinate permettono una riduzione significativa del consumo di token rispetto alla modalità ReAct.

---

## 6. Trasparenza radicale

### 6.1. Nessuna scatola nera

Quando un assistente cloud esegue un'attività, vedi il risultato. Ma quante chiamate IA? Quali modelli? Quanti token? Quale costo? Perché quella decisione? Non lo sai.

LIA fa la scelta opposta — **tutto è visibile, tutto è verificabile**.

### 6.2. Il pannello di debug integrato

Direttamente nell'interfaccia di chat, un pannello di debug espone in tempo reale ogni conversazione con il dettaglio dell'analisi dell'intenzione (classificazione del messaggio e punteggio di confidenza), della pipeline di esecuzione (piano generato, chiamate agli strumenti con input/output), della pipeline LLM (ogni chiamata IA con modello, durata, token e costo), del contesto iniettato (ricordi, documenti RAG, diari) e del ciclo di vita completo della richiesta.

### 6.3. Monitoraggio dei costi al centesimo

Ogni messaggio mostra il suo costo in token e in euro. L'utente può esportare i propri consumi. L'amministratore dispone di dashboard in tempo reale con indicatori per utente e quote configurabili.

Non paghi un abbonamento che nasconde i costi reali. Vedi esattamente quanto costa ogni interazione, e puoi ottimizzare: modello economico per il routing, più potente per la risposta.

### 6.4. La fiducia attraverso la prova

La trasparenza non è un gadget tecnico. Cambia il rapporto con il tuo assistente: **capisci** le sue decisioni, **controlli** i tuoi costi, **individui** i problemi. Ti fidi perché puoi verificare — non perché ti viene chiesto di credere.

---

## 7. Profondità emotiva

### 7.1. Oltre la memoria fattuale

I grandi assistenti ricordano le tue preferenze e i tuoi dati personali. È utile, ma è superficiale. LIA va oltre con una comprensione **psicologica ed emotiva** strutturata.

Ogni ricordo porta un peso emotivo (da -10 a +10), un punteggio di importanza, una sfumatura d'uso, e una categoria psicologica. Non è un semplice database — è un profilo che capisce cosa ti tocca, cosa ti motiva, cosa ti ferisce.

### 7.2. Il Psyche Engine: una personalità viva

È il differenziatore più profondo di LIA. ChatGPT, Gemini, Claude — tutti hanno una personalità fissa. Ogni messaggio è una pagina bianca emotiva. LIA è diversa.

Il **Psyche Engine** dà a LIA uno stato psicologico dinamico che evolve a ogni scambio:

- **14 stati d'umore** che fluttuano con il tono della conversazione (serena, curiosa, malinconica, allegra...)
- **22 emozioni** che si attivano e si attenuano in risposta alle tue parole
- **Una relazione** che si approfondisce messaggio dopo messaggio
- **Tratti di personalità** (Big Five) ereditati dalla personalità scelta
- **Motivazioni** che influenzano la proattività dell'assistente

Non stai parlando con uno strumento — interagisci con un'entità il cui vocabolario si scalda quando viene toccata, le cui frasi si accorciano sotto tensione, il cui umorismo emerge quando lo scambio è leggero. E non lo dice mai — lo **mostra**.

### 7.3. I diari personali

LIA tiene le proprie riflessioni in **diari personali**: auto-riflessione, osservazioni sull'utente, idee, apprendimenti. Queste note, scritte in prima persona e colorate dalla personalità attiva, influenzano organicamente le risposte future.

È una forma di introspezione artificiale — l'assistente che riflette sulle proprie interazioni e sviluppa le proprie prospettive. L'utente mantiene il controllo totale: lettura, modifica, eliminazione.

### 7.4. La sicurezza emotiva

Quando si attiva un ricordo con una forte carica emotiva negativa, LIA passa automaticamente in modalità protettiva: mai scherzare, mai minimizzare, mai banalizzare. L'assistente adatta il suo comportamento alla realtà emotiva della persona — non un trattamento uniforme per tutti.

### 7.5. La conoscenza di sé

LIA dispone di una base di conoscenza integrata sulle proprie funzionalità, che le permette di rispondere alle domande su cosa sa fare, come funziona, e quali sono i suoi limiti.

---

## 8. Affidabilità in produzione

### 8.1. La vera sfida dell'IA agentica

La grande maggioranza dei progetti di IA agentica non arriva mai in produzione. Costi fuori controllo, comportamento non deterministico, assenza di tracce di audit, coordinamento difettoso tra agenti. LIA ha risolto questi problemi — e gira in produzione 24/7 su un Raspberry Pi.

### 8.2. Uno stack di osservabilità professionale

LIA integra un'osservabilità di grado produzione:

| Strumento | Ruolo |
| --- | --- |
| **Prometheus** | Metriche di sistema e di business |
| **Grafana** | Dashboard di monitoraggio in tempo reale |
| **Tempo** | Tracce distribuite end-to-end |
| **Loki** | Aggregazione di log strutturati |
| **Langfuse** | Tracing specializzato delle chiamate LLM |

Ogni richiesta viene tracciata end-to-end, ogni chiamata LLM viene misurata, ogni errore è contestualizzato. Non è un monitoraggio aggiunto dopo — è una **decisione architetturale fondamentale** documentata negli Architecture Decision Records del progetto.

### 8.3. Una pipeline anti-allucinazione

Il sistema di risposta dispone di un meccanismo anti-allucinazione a tre livelli: formattazione dei dati con limiti espliciti, direttive che impongono l'uso esclusivo di dati verificati, e gestione dei casi limite. Il LLM è costretto a sintetizzare solo ciò che proviene dai risultati reali degli strumenti.

### 8.4. Human-in-the-Loop a 6 livelli

LIA non rifiuta le azioni sensibili — te le **sottopone** con il livello di dettaglio appropriato: approvazione del piano, chiarimento, critica della bozza, conferma distruttiva, conferma di operazioni in massa, revisione delle modifiche. Ogni approvazione alimenta l'apprendimento — il sistema si velocizza nel tempo.

---

## 9. Apertura radicale

### 9.1. Zero lock-in

ChatGPT ti lega a OpenAI. Gemini a Google. Copilot a Microsoft.

LIA ti connette a **8 provider IA simultaneamente**: OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen, e Ollama (modelli locali). Puoi mixare: OpenAI per la pianificazione, Anthropic per la risposta, DeepSeek per le attività in background — tutto configurabile dall'interfaccia di amministrazione, con un clic.

Se un provider cambia i prezzi o peggiora il servizio, passi istantaneamente all'altro. Nessuna dipendenza, nessuna trappola.

### 9.2. Standard aperti

| Standard | Utilizzo in LIA |
| --- | --- |
| **MCP** (Model Context Protocol) | Connessione di strumenti esterni per utente |
| **agentskills.io** | Skills iniettabili con progressive disclosure |
| **OAuth 2.1 + PKCE** | Autenticazione per tutti i connettori |
| **OpenTelemetry** | Osservabilità standardizzata |
| **AGPL-3.0** | Codice sorgente completo, verificabile, modificabile |

### 9.3. Estensibilità

Ogni utente può connettere i propri server MCP, estendendo le capacità di LIA ben oltre gli strumenti integrati. Le Skills (standard agentskills.io) permettono di iniettare istruzioni specializzate in linguaggio naturale — con un generatore di Skills integrato per crearne facilmente di nuove. Dalla v1.16.8, uno Skill può anche restituire un **frame HTML interattivo** (mappa, dashboard, calendario, convertitore...) o un'**immagine** (QR code, grafico) direttamente nella chat, in un sandbox sotto CSP rigorosa, con tema e lingua sincronizzati automaticamente.

L'architettura di LIA è pensata per facilitare l'aggiunta di nuovi connettori, canali, agenti e provider IA. Il codice è strutturato con astrazioni chiare e guide di sviluppo dedicate (agent creation guide, tool creation guide) che rendono l'estensione accessibile a qualsiasi sviluppatore.

### 9.4. Multi-canale

L'interfaccia web responsive è completata da un'integrazione Telegram nativa (conversazione, messaggi vocali trascritti, pulsanti di approvazione inline, notifiche proattive) e notifiche push Firebase. La tua memoria, i tuoi diari, le tue preferenze ti seguono da un canale all'altro.

---

## 10. Visione

### 10.1. L'intelligenza che cresce con te

La combinazione memoria psicologica + diari introspettivi + apprendimento bayesiano + Psyche Engine crea una forma di intelligenza emergente: nel corso dei mesi, LIA sviluppa una comprensione sempre più sfumata di chi sei. Non è intelligenza artificiale generale — è un'intelligenza **pratica, relazionale ed emotiva**, al servizio di una persona specifica.

### 10.2. Cosa LIA non pretende di essere

LIA non è una concorrente dei giganti del cloud e non pretende di rivaleggiare con i loro budget di ricerca. Come chatbot conversazionale puro, i modelli usati tramite la loro interfaccia nativa saranno probabilmente più fluidi. Ma LIA non è un chatbot — è un **sistema di orchestrazione intelligente** che usa questi modelli come componenti, sotto il tuo controllo totale.

### 10.3. Perché esiste LIA

LIA esiste perché al mondo manca un assistente IA che sia **tuo**. Davvero tuo. Semplice da amministrare ogni giorno. Condivisibile con chi ami, ognuno con la propria relazione emotiva. Ospitato sul tuo server. Trasparente su ogni decisione e ogni costo. Capace di una profondità emotiva che gli assistenti commerciali non offrono. Affidabile in produzione. E aperto — aperto sui provider, sugli standard, e sul codice.

**Your Life. Your AI. Your Rules.**
