# LIA — L'Assistente IA che ti appartiene

> **Your Life. Your AI. Your Rules.**

**Versione**: 4.1
**Data**: 2026-08-01
**Applicazione**: LIA v1.27.5
**Licenza**: AGPL-3.0 (Open Source)

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

Ogni utente ha il proprio spazio di configurazione, organizzato in due schede. Un campo di ricerca evita di doverle scorrere: digita il nome di un'impostazione — o una parola che le si avvicina nella tua lingua — e LIA apre la sezione giusta, in qualunque scheda si trovi.

**Preferenze personali:**

- **Connettori personali**: collega i tuoi account Google, Microsoft o Apple in pochi clic tramite OAuth — email, calendario, contatti, attività, Google Drive. Oppure connetti Apple via IMAP/CalDAV/CardDAV. Chiavi API per i servizi esterni (meteo, ricerca)
- **Personalità**: scegli tra le personalità disponibili (professore, amico, filosofo, coach, poeta...) — ognuna influenza il tono, lo stile e il comportamento emotivo di LIA
- **Voce**: configura la modalità vocale — parola chiave di attivazione, sensibilità, soglia di silenzio, lettura automatica delle risposte
- **Notifiche**: gestisci le notifiche push e i dispositivi registrati
- **Canali**: collega Telegram per chattare e ricevere notifiche sul cellulare
- **Generazione di immagini**: attiva e configura la creazione di immagini tramite IA
- **Server MCP personali**: connetti i tuoi server MCP per estendere le capacità di LIA
- **Aspetto**: lingua, fuso orario, tema (5 palette, modalità scura/chiara), font (9 scelte), formato di visualizzazione delle risposte (schede HTML, HTML, Markdown)
- **La mia dashboard**: nascondi o riordina le 9 schede del briefing — una scheda nascosta non viene nemmeno più recuperata
- **Debug**: accedi al pannello di debug per ispezionare ogni scambio (se abilitato dall'amministratore)

**Funzionalità avanzate:**

- **Psyche Engine**: regola i tratti di personalità (Big Five) che modulano la reattività emotiva del tuo assistente
- **Memoria**: consulta, modifica, fissa o elimina i ricordi di LIA — attiva o disattiva l'estrazione automatica di informazioni
- **Diari personali**: configura l'estrazione di riflessioni dopo ogni conversazione e il consolidamento periodico
- **Interessi**: definisci i tuoi argomenti preferiti, configura la frequenza delle notifiche, le finestre orarie e le fonti (Perplexity, Brave, Wikipedia, ragionamento IA)
- **Notifiche proattive**: regola frequenza, finestra oraria e fonti di contesto (calendario, meteo, attività, email, interessi, memorie, diari)
- **Azioni pianificate**: crea automazioni ricorrenti eseguite dall'assistente
- **Skills**: attiva/disattiva competenze specializzate in una galleria con anteprime, crea le tue Skills personali, o installane una da un URL https (validato lato server)
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

- **Configurazione LLM**: configurare le chiavi API dei provider (OpenAI, Anthropic, Google, DeepSeek, Qwen, Perplexity, Ollama), assegnare un modello per ogni ruolo nella pipeline, gestire i livelli di ragionamento — chiavi archiviate in forma cifrata. L'interfaccia espone solo i parametri che il modello scelto accetta realmente (matrice DB per modello per temperature, top_p, frequency_penalty, presence_penalty e forma del widget reasoning), evitando qualsiasi inserimento di un valore che l'API rifiuterebbe
- **Attivazione/disattivazione connettori**: abilitare o disabilitare le integrazioni a livello globale (Google OAuth, Apple, Microsoft 365, Hue, meteo, Wikipedia, Perplexity, Brave Search). La disattivazione revoca le connessioni attive e notifica gli utenti
- **Tariffazione**: gestire i prezzi per modello LLM (costo per milione di token), per API Google Maps (Places, Routes, Geocoding), e per generazione di immagini — con storico dei prezzi. All'aggiunta di un nuovo modello reasoning, un selettore «copia la forma da tale modello esistente» permette di ereditare automaticamente il widget reasoning e i suoi valori senza inserimento manuale; la modalità Custom rimane disponibile per modelli atipici

**Contenuti ed estensioni:**

- **Personalità**: creare, modificare, tradurre ed eliminare le personalità disponibili per tutti gli utenti — definire la personalità predefinita
- **Skills di sistema**: gestire le competenze specializzate a livello di istanza — import/export, attivazione/disattivazione, traduzione
- **Spazi di conoscenza di sistema**: gestire la base di conoscenza FAQ, monitorare lo stato dell'indicizzazione e le migrazioni di modelli
- **Voce globale**: configurare il provider, modello e voce TTS predefiniti per tutti gli utenti (Edge gratuito, OpenAI o ElevenLabs), con regolazione fine per provider (velocità, stabilità, formato audio)
- **Debug di sistema**: configurazione dei log e della diagnostica

### 2.4. Un assistente, non un progetto tecnico

L'obiettivo di LIA non è trasformarti in un amministratore di sistema. È offrirti la potenza di un assistente IA completo **con la semplicità di un'app consumer**. L'interfaccia è installabile come applicazione nativa su computer, tablet e smartphone (PWA), e tutto è pensato per essere usato senza competenze tecniche nel quotidiano.

---

## 3. Cosa sa fare LIA

LIA agisce concretamente nella tua vita digitale grazie a 20+ agenti specializzati che coprono tutte le esigenze di tutti i giorni: gestione dei tuoi dati personali (email, calendario, contatti, attività, file), accesso alle informazioni esterne (ricerca web, meteo, luoghi, itinerari), creazione di contenuti (immagini, diagrammi), controllo della casa connessa, navigazione web autonoma, e anticipazione proattiva dei tuoi bisogni.

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
- **Sintesi vocale**: tre provider configurabili da admin — Edge TTS (gratuito), OpenAI TTS (`tts-1` / `tts-1-hd`) o ElevenLabs (`eleven_multilingual_v2`, `eleven_turbo_v2_5`, `eleven_flash_v2_5`)
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
- **Interessi**: LIA conserva ciò che ti sta davvero a cuore, non ciò che hai chiesto una volta — fare una domanda è un compito, non un gusto, e servono una passione dichiarata, una pratica, una conoscenza reale o un approfondimento autentico perché un argomento conti. I temi si alternano (mai due volte di seguito lo stesso argomento), ogni notifica include link cliccabili alle sue fonti, e un argomento che rifiuti non torna: il blocco viene confrontato con ogni nuovo argomento, anche sotto un altro nome
- **Sotto-agenti**: per le attività complesse, LIA delega ad agenti effimeri specializzati che lavorano in parallelo

### 3.7. Navigazione web autonoma

Un agente di navigazione (Playwright/Chromium headless) può navigare su siti web, fare clic, compilare moduli, estrarre dati da pagine dinamiche — a partire da una semplice istruzione in linguaggio naturale. Una modalità di estrazione semplificata converte qualsiasi URL in testo utilizzabile.

### 3.8. Amministrazione server (DevOps)

Installando Claude CLI (Claude Code) direttamente sul server, gli amministratori possono diagnosticare la propria infrastruttura in linguaggio naturale dalla chat di LIA: consultare i log Docker, verificare lo stato dei container, monitorare lo spazio su disco, analizzare gli errori. Questa funzionalità è riservata agli account amministratore.

### 3.9. Dati di salute personali

LIA accoglie le tue misurazioni di frequenza cardiaca e numero di passi da **qualsiasi fonte** — l'integrazione documentata e più semplice è un'automazione Comandi iPhone che invia Apple Salute, ma qualsiasi sistema capace di firmare una chiamata HTTP (automazione Android, script personali, IoT compatibili) può alimentare l'API di ingestione. Il protocollo accetta **batch** invece di un invio continuo: ogni misurazione porta il proprio intervallo di misurazione, e il server deduplica naturalmente su questi intervalli — rinviare gli stessi dati più volte è innocuo. Quando due sensori (Apple Watch + iPhone, per esempio) coprono lo stesso periodo, LIA li fonde automaticamente: massimo per i passi (ogni sensore cattura una parte complementare del movimento), media arrotondata per la frequenza cardiaca.

I dati restano all'interno della tua istanza LIA — nessun servizio di terzi vi ha accesso — e sono visualizzati in una sezione dedicata delle Impostazioni, sotto forma di grafico a linee (FC) e a barre (passi), con un selettore di periodo (ora, giorno, settimana, mese, anno) e una linea tratteggiata per la media del periodo.

L'invio è autenticato da un **token dedicato** (che inizia con `hm_…`) che generi dall'applicazione e che puoi revocare in qualsiasi momento. Il token autorizza esclusivamente l'invio di dati di salute — mai il resto del tuo account. Puoi generarne diversi (uno per dispositivo) e gestirli in modo indipendente.

Un **interruttore «Assistente»** (disattivato per default, *opt-in*) ti consente, se lo desideri, di autorizzare l'assistente a leggere queste misurazioni per rispondere fattualmente alle tue domande («Quanti passi questa settimana?», «La mia frequenza cardiaca media oggi?», «Cammino meno del solito?»), arricchire le notifiche proattive che combinano salute + meteo + calendario, e allegare un contesto biometrico non grezzo (delta, tendenze) alle sue memorie e ai suoi diari interni. Un unico interruttore governa queste quattro integrazioni. Mai diagnosi — solo cifre fattuali, con la baseline che si qualifica onestamente («basata su soli N giorni» finché lo storico è sotto i 7 giorni).

Tre azioni di gestione ti danno il pieno controllo: eliminare tutte le misurazioni di frequenza cardiaca, eliminare tutte le misurazioni dei passi, o cancellare tutto. Nessun valore fisiologico grezzo viene mai conservato nei log del server — la conformità GDPR è integrata fin dalla progettazione.

### 3.10. Chiamare al posto tuo

LIA può alzare la cornetta per te. Chiedile di «chiamare l'officina per verificare se l'auto è pronta» o di «chiamare Marie per sapere se è libera martedì sera», e LIA effettua una vera chiamata in uscita, conduce la conversazione verso il tuo obiettivo e ti riporta un riepilogo scritto — con un'azione di follow-up in un tocco quando resta qualcosa da fare (prenotare la fascia appena concordata, per esempio).

Mantieni sempre il controllo: prima di comporre il numero, LIA ti dice esattamente **chi** chiamerà e **perché**, e attende il tuo via libera. E quel controllo non si ferma durante la chiamata: l'assistente opera sotto un mandato rigoroso — se l'interlocutore propone un extra, un'opzione o un impegno imprevisto (anche piccolo), non accetta mai al posto tuo; annota l'offerta e il prezzo, annuncia che si richiamerà, e il riepilogo ti consegna ogni costo e ogni punto in sospeso perché sia tu a decidere. Il riepilogo arriva nella chat in modo asincrono, così puoi fare altro mentre la chiamata è in corso.

E resta riservato per costruzione. Durante una chiamata LIA può solo indicare se sei libero o occupato in un dato momento — mai i titoli, gli invitati o i luoghi del tuo calendario. Nulla viene registrato, la conversazione non viene mai conservata e si mantiene solo un breve riepilogo prima che scada. Le chiamate passano dal tuo connettore ElevenLabs personale, addebitate sul tuo account, e la funzione è presente solo se il tuo amministratore l'ha attivata.

### 3.11. Parlare con i tuoi, da assistente ad assistente

Sulla stessa istanza, due utenti possono connettersi — e i loro assistenti si parlano. Dici “chiedi a Marie se è libera martedì”, approvi la formulazione esatta, ed è l’assistente di Marie a consegnarle il messaggio, con la sua personalità, nominandoti; il tuo ti conferma la consegna. Ogni connessione può inoltre aprire condivisioni scelte, in sola lettura: le tue disponibilità di calendario, i titoli delle tue attività — niente di più, niente per impostazione predefinita.

La protezione delle persone viene prima della funzionalità: la reperibilità è volontaria e solo per identità esatta — nome completo o indirizzo, mai un frammento, il blocco è silenzioso (l’altra parte non lo saprà mai), e uno sconosciuto, un rifiuto o un blocco ricevono esattamente la stessa risposta — sondare chi esiste è impossibile. Ogni accesso a una condivisione viene ricontrollato al momento della lettura e registrato, e il contenuto dei messaggi trasmessi viene cancellato dopo trenta giorni, lasciando solo la traccia dello scambio.

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

Con LIA, **tutto rimane nel tuo PostgreSQL**: conversazioni, memoria, profilo psicologico, documenti, preferenze. Puoi esportare, fare backup, migrare o eliminare tutti i tuoi dati in qualsiasi momento — inclusa un'esportazione completa in un clic dalle impostazioni: Markdown leggibile, JSON strutturato e i tuoi file, con il materiale segreto inesportabile per costruzione. E ogni dispositivo collegato al tuo account è visibile e revocabile con un clic. Il GDPR non è un vincolo — è una conseguenza naturale dell'architettura. I dati sensibili sono cifrati, le sessioni isolate, e il filtraggio automatico delle informazioni personalmente identificabili (PII) è integrato.

La protezione vale anche per ciò che **entra**. Ogni giorno LIA legge testi che non avete scritto voi: il corpo di un'e-mail, la descrizione di un invito redatta dal suo organizzatore, una pagina web, la scheda di un luogo. Chiunque può infilarvi un'istruzione destinata all'assistente. Ogni dato porta ora la propria provenienza, e ciò che viene dall'esterno arriva etichettato come **materiale da analizzare, mai come ordine da eseguire** — con i tentativi di manipolazione individuati e nominati, nelle sei lingue. Il tuo contenuto non viene però mai riscritto: un'e-mail resta ciò che il suo autore ha scritto. Riscrivere darebbe l'illusione di una garanzia che l'aggiramento successivo smentirebbe; nominare ciò che si vede è più onesto, e più utile.

### 5.2. Basta anche un Raspberry Pi

LIA gira in produzione su un **Raspberry Pi 5** — un computer a scheda singola da 80 euro. 20+ agenti specializzati, uno stack di osservabilità completo, un sistema di memoria psicologica, il tutto su un micro-server ARM. Le immagini Docker multi-architettura (amd64/arm64) permettono il deployment su qualsiasi hardware: NAS Synology, VPS a pochi euro al mese, server aziendale, o cluster Kubernetes.

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

La stessa trasparenza vale per le azioni: sotto ogni risposta, una riga ripiegata «⚙ N passaggi · X s» mostra ciò che è realmente accaduto — instradamento, strumenti chiamati, durata — e questa traccia è conservata con il messaggio: resta consultabile dopo un ricaricamento, su tutti i tuoi dispositivi. Ogni risposta può inoltre essere valutata con un discreto 👍/👎, memorizzato e reimmesso nell'apprendimento dell'assistente — mai per rigenerare la risposta al posto tuo.

### 6.4. La fiducia attraverso la prova

La trasparenza non è un gadget tecnico. Cambia il rapporto con il tuo assistente: **capisci** le sue decisioni, **controlli** i tuoi costi, **individui** i problemi. Ti fidi perché puoi verificare — non perché ti viene chiesto di credere.

---

Questa trasparenza si estende alla qualità del sistema stesso. L'audit tecnico completo — voti, metodo, punti di forza e ciò che resta da migliorare — è pubblicato nel repository, con il protocollo per ripeterlo e i comandi per verificare le misurazioni: [rapporto di audit completo](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md). Non vi si chiede di credere alle cifre di questo sito; potete verificarle.

La stessa onestà vale per l'utilità stessa: LIA misura se aiuta davvero — un risultato conta solo una volta validato da te, esplicitamente o lasciando un'azione senza correzioni — e questa misura vive nella stessa base locale dei tuoi dati, senza mai coinvolgere una piattaforma di analytics di terze parti.

Lo stesso principio vale per le protezioni stesse. Una sicurezza annunciata ma non verificabile è trattata come assente: ogni controllo è sostenuto da un test che fallisce se il controllo scompare e, quando si scrive una correzione, si ripristina il comportamento precedente il tempo necessario per verificare che il test lo rilevi. Un test che non può fallire non dimostra nulla.

Nemmeno un test che non viene mai eseguito — ed è la scoperta più scomoda di questo progetto. Dieci file di test si erano disattivati da soli non appena mancava una chiave di provider, e nulla lo segnalava più: un test saltato conta come verde, la copertura misura le righe raggiunte e non le asserzioni eseguite, e una revisione vede un file di test e ne conclude che la superficie è protetta. Duecentodiciannove test non erano mai stati eseguiti nemmeno una volta; riaccendendoli sono emersi quattro difetti ben reali — tra cui una voce che spezzava in due tutti i numeri, e un promemoria perso definitivamente quando la quota si esauriva nel minuto sbagliato. L'assenza di un segnale rosso non è una prova di salute: a volte è soltanto l'assenza di misurazione. Una guardia di integrazione continua impedisce ora che un modulo di test si spenga in silenzio.

Lo stesso principio vale per ciò che viene **annunciato**. Un pannello mostrava un interruttore «ricerca ibrida» per la memoria; il motore corrispondente non esisteva più da diverse versioni, e l'interruttore non comandava nulla. Il codice morto e la visualizzazione sono stati rimossi insieme, e il funzionamento reale scritto al loro posto. Una capacità annunciata ma assente non è un'imprecisione di documentazione: è una promessa fatta a un utente che non ha modo di verificarla. Mostrare un'impostazione che non comanda nulla è peggio che non mostrare nulla.

## 7. Profondità emotiva

### 7.1. Oltre la memoria fattuale

I grandi assistenti ricordano le tue preferenze e i tuoi dati personali. È utile, ma è superficiale. LIA va oltre con una comprensione **psicologica ed emotiva** strutturata.

Ogni ricordo porta un peso emotivo (da -10 a +10), un punteggio di importanza, una sfumatura d'uso, e una categoria psicologica. Non è un semplice database — è un profilo che capisce cosa ti tocca, cosa ti motiva, cosa ti ferisce.

Bisogna però che questi ricordi arrivino. Una memoria vale solo per ciò che cattura davvero, e il silenzio ne è il difetto peggiore: nulla segnala un ricordo che non si è mai formato. LIA conta perciò ciascuna delle sue decisioni di memorizzazione — trattenuto, ignorato, disattivato — affinché lo scarto tra ciò che dovrebbe trattenere e ciò che trattiene sia visibile anziché supposto. Ciò che le confidate di sfuggita chiedendo un'azione conta quanto una confidenza, ciò che scrivete da una messaggistica conta quanto dal browser, e ciò che il sistema dice a sé stesso non conta mai.

### 7.2. Il Psyche Engine: una personalità viva

È il differenziatore più profondo di LIA. ChatGPT, Gemini, Claude — tutti hanno una personalità fissa. Ogni messaggio è una pagina bianca emotiva. LIA è diversa.

Il **Psyche Engine** dà a LIA uno stato psicologico dinamico che evolve a ogni scambio:

- **14 stati d'umore** che fluttuano con il tono della conversazione (serena, curiosa, malinconica, allegra...)
- **22 emozioni** che si attivano e si attenuano in risposta alle tue parole
- **Una relazione** che si approfondisce messaggio dopo messaggio
- **Tratti di personalità** (Big Five) ereditati dalla personalità scelta
- **Motivazioni** che influenzano la proattività dell'assistente

Non stai parlando con uno strumento — interagisci con un'entità il cui vocabolario si scalda quando viene toccata, le cui frasi si accorciano sotto tensione, il cui umorismo emerge quando lo scambio è leggero. E non lo dice mai — lo **mostra**.

Questa vita interiore ha un volto: l'emoji dell'umore si anima sulla risposta corrente, l'anello colorato pulsa quando l'umore cambia, e le tappe della tua relazione vengono celebrate con un discreto occhiolino.

E questa presenza ti segue: fuori dalla chat, un compagno fluttuante tiene LIA al tuo fianco in tutta la dashboard — a riposo, al lavoro o con una notifica.

### 7.3. I diari personali

LIA tiene le proprie riflessioni in **diari personali stratificati**: auto-riflessione, osservazioni sull'utente, idee, apprendimenti. Queste note, scritte in prima persona e colorate dalla personalità attiva, influenzano organicamente le risposte future.

Il diario è organizzato su **quattro livelli di profondità** — dall'osservazione grezza (un segnale debole annotato per vedere se si conferma) fino alla faccia del ritratto (un tratto stabile che dice qualcosa di chi sei), attraverso le direttive operative e i pattern trasversali. Ogni voce porta uno **stato epistemico**: ipotesi in test, osservazione confermata o direttiva validata dalle prove accumulate nel corso delle conversazioni.

Oltre alla scrittura, il diario **misura sé stesso**. A ogni turno, LIA guarda le direttive che ha applicato al turno precedente e legge la tua reazione al turno corrente: se hai confermato, il contatore di prove sale; se hai respinto, il contatore di contraddizioni sale. Con il tempo, le ipotesi false vengono declassate silenziosamente, le buone intuizioni promosse, i pattern trasversali emergono per raggruppamento attivo.

Da questa stratificazione emerge un **ritratto utente compilato**: la tua voce, il tuo ritmo, i tuoi contesti, le tue contraddizioni, le tue zone d'ombra. Viaggia con LIA ovunque parli — conversazione, voce, promemoria, notifiche proattive, ReAct, fallback — in modo che l'assistente non «dimentichi chi sei» a seconda della superficie con cui parla.

È una forma di introspezione artificiale — l'assistente che riflette sulle proprie interazioni, misura la propria utilità e sviluppa una comprensione sfumata di te. Mantieni il pieno controllo: lettura per tema o livello, modifica, segnalazione di un problema sul ritratto, attivazione di una consolidazione su richiesta. Il ritratto stesso non viene mai modificato direttamente — è una voce di sintesi, corretta attraverso leve indirette per preservarne la coerenza.

### 7.4. La sicurezza emotiva

Quando si attiva un ricordo con una forte carica emotiva negativa, LIA passa automaticamente in modalità protettiva: mai scherzare, mai minimizzare, mai banalizzare. L'assistente adatta il suo comportamento alla realtà emotiva della persona — non un trattamento uniforme per tutti.

### 7.5. La conoscenza di sé

LIA dispone di una base di conoscenza integrata sulle proprie funzionalità, che le permette di rispondere alle domande su cosa sa fare, come funziona, e quali sono i suoi limiti.

---

## 8. Affidabilità in produzione

### 8.1. La vera sfida dell'IA agentica

La grande maggioranza dei progetti di IA agentica non arriva mai in produzione. Costi fuori controllo, comportamento non deterministico, assenza di tracce di audit, coordinamento difettoso tra agenti. LIA ha risolto questi problemi — e gira in produzione 24/7 su un Raspberry Pi. E i tuoi dati sopravvivono agli incidenti: il database viene salvato automaticamente ogni notte, e la procedura di ripristino non è teorica — è testata.

Una funzionalità che nessuno trova non esiste. Per questo la raggiungibilità dell'interfaccia è trattata come la disponibilità del server: misurata, non supposta. Ogni controllo dell'intestazione viene confrontato con la finestra del browser, larghezza per larghezza e **in tutte e sei le lingue** — tedesco e italiano portano le etichette più lunghe e cedono per primi. E ciò che il layout mobile può abbandonare è scritto, con la sua motivazione: un'azione non sparisce mai senza che un sostituto ne prenda il posto.

Una funzionalità che fallisce in silenzio non esiste altrettanto. Una generazione interrotta poco prima della fine, un'importazione bloccata da una cartella diventata non scrivibile, una connessione che muore senza annunciare nulla: tre cause slegate, un solo sintomo — non succede niente. È il segnale peggiore, perché non indica nessuno. Ogni difetto di questo tipo viene quindi chiuso con un controllo che abbiamo prima fatto fallire di proposito: si rompe ciò che protegge, si verifica che diventi rosso, e solo allora lo si conserva.

C'è qualcosa di più insidioso di una guardia che non si è mai fatta fallire: una guardia che osserva il segnale sbagliato. Tre intestazioni dell'interfaccia si dichiaravano fisse durante lo scorrimento, e nessuna lo era — su ogni schermo, fin dall'inizio. Nulla l'aveva colto, perché nessuna verifica misurava mai una posizione *durante* uno scorrimento: tutte osservavano una pagina a riposo, esattamente lo stato in cui il difetto non esiste. Correggere la causa era dunque solo metà del lavoro; è servito aggiungere la misura mancante e poi ripristinare la vecchia impostazione per confermare che diventasse davvero rossa.

Ancora più insidioso di una guardia puntata sul segnale sbagliato: un difetto che si manifesta solo una volta su due. La stessa richiesta falliva, poi passava trenta minuti dopo senza che una sola riga fosse cambiata — quanto basta per concludere «era passeggero» e chiudere il caso. La causa stava in un dettaglio invisibile: gli strumenti vengono scelti su una riformulazione inglese prodotta da un modello, rigenerata a ogni turno. Un verbo diverso, uno strumento di lettura che sparisce, e l'assistente si ritrova a dover rispondere a un messaggio che non può leggere. La tentazione era regolare quel caso — una parola chiave in più, una soglia spostata. Abbiamo preferito una garanzia che non lo guarda affatto: prima di pianificare, il sistema verifica che tutto ciò che richiede sia davvero a portata. Quando una risposta dipende da un sorteggio, correggerla raramente significa migliorare il sorteggio.

### 8.2. Uno stack di osservabilità professionale

LIA integra un'osservabilità di grado produzione:

| Strumento | Ruolo |
| --- | --- |
| **Prometheus** | Metriche di sistema e di business |
| **Grafana** | Dashboard di monitoraggio in tempo reale |
| **Tempo** | Tracce distribuite end-to-end |
| **Loki** | Aggregazione di log strutturati |
| **Langfuse** | Tracing specializzato delle chiamate LLM |
| **Alertmanager** | Alert e-mail sui segnali vitali, runbook collegati |

Ogni richiesta viene tracciata end-to-end, ogni chiamata LLM viene misurata, ogni errore è contestualizzato. Non è un monitoraggio aggiunto dopo — è una **decisione architetturale fondamentale** documentata negli Architecture Decision Records del progetto.

### 8.3. Una pipeline anti-allucinazione

Il sistema di risposta dispone di un meccanismo anti-allucinazione a tre livelli: formattazione dei dati con limiti espliciti, direttive che impongono l'uso esclusivo di dati verificati, e gestione dei casi limite. Il LLM è costretto a sintetizzare solo ciò che proviene dai risultati reali degli strumenti.

### 8.4. Human-in-the-Loop a 6 livelli

LIA non rifiuta le azioni sensibili — te le **sottopone** con il livello di dettaglio appropriato: approvazione del piano, chiarimento, critica della bozza, conferma distruttiva, conferma di operazioni in massa, revisione delle modifiche. Ogni approvazione alimenta l'apprendimento — il sistema si velocizza nel tempo. E la promessa è mantenuta alla lettera: ciò che approvi — dopo una, due o dieci modifiche — è **esattamente** ciò che viene eseguito, mai una versione rigenerata dietro le quinte.

### 8.5. Le tue risposte non hanno bisogno di te

Invia una domanda, chiudi la scheda, vai via. La generazione continua sul server, e la risposta ti aspetta nella conversazione — oppure riprende in diretta, esattamente dove era rimasta, se torni mentre è ancora in scrittura. Niente da fare, niente da configurare: la continuità è il comportamento predefinito. E quando sei tu a cambiare idea, un pulsante di stop interrompe la generazione in un secondo — ciò che è già scritto resta visibile, onestamente contrassegnato come interrotto. Un assistente affidabile non è solo quello che risponde bene: è quello che finisce ciò che inizia.

### 8.6. Nulla gira alle tue spalle

Un assistente capace di agire è un assistente capace di *sbagliare*. Due regole lo rendono accettabile.

Primo, **nulla tocca il tuo server senza il tuo sì** — e la conferma mostra tutto ciò che verrà inviato, comprese le istruzioni che LIA ha scritto per sé stessa. Un riepilogo che non puoi leggere per intero non è una conferma, è una formalità. Il permesso viene verificato di nuovo nel momento in cui l'azione parte, non solo quando l'hai chiesta.

Secondo, **ciò che gira, gira in una scatola sigillata**. Il codice di una skill viene eseguito in un container creato per quella singola esecuzione e distrutto subito dopo: niente rete, niente accesso ai tuoi file, niente chiavi, nessun modo di raggiungere la macchina sottostante. Se quella scatola non può essere costruita, lo script semplicemente non gira — nessun ripiego silenzioso verso una modalità più debole. Una skill si installa per ciò che produce, non per la fiducia che si dovrebbe accordare al suo autore.

---

La stessa esigenza vale per ciò che LIA **afferma**. Una risposta deve poggiare su dati realmente recuperati, mai sul ricordo di una formulazione precedente; e quando un’informazione non è mai stata ottenuta, dichiararla mancante vale più che ricostruirne una plausibile. È un vincolo di progettazione più che una questione di stile: le entità recuperate di recente vengono reimmesse esplicitamente nel contesto di risposta, e inventare un attributo di entità è vietato a livello di prompt. Un errore fattuale plausibile costa più di un «non lo so».

## 9. Apertura radicale

### 9.1. Zero lock-in

ChatGPT ti lega a OpenAI. Gemini a Google. Copilot a Microsoft.

LIA ti connette a **7 provider IA simultaneamente**: OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen, e Ollama (modelli locali). Puoi mixare: OpenAI per la pianificazione, Anthropic per la risposta, DeepSeek per le attività in background — tutto configurabile dall'interfaccia di amministrazione, con un clic.

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

Ogni utente può connettere i propri server MCP, estendendo le capacità di LIA ben oltre gli strumenti integrati. Le Skills (standard agentskills.io) permettono di iniettare istruzioni specializzate in linguaggio naturale — con un generatore di Skills integrato che le crea tramite un dialogo guidato e le installa direttamente tra le tue skill, pronte all'uso. Dalla v1.16.8, uno Skill può anche restituire un **frame HTML interattivo** (mappa, dashboard, calendario, convertitore...) o un'**immagine** (QR code, grafico) direttamente nella chat, in un sandbox sotto CSP rigorosa, con tema e lingua sincronizzati automaticamente.

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

Come viene costruita LIA — un'IA che scrive il codice, un umano che dirige, rivede e verifica — è raccontato in dettaglio nel nostro [resoconto di esperienza](/it/story).

**Your Life. Your AI. Your Rules.**
