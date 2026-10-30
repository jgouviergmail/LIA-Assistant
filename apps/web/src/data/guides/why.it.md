# LIA — L'Assistente IA che ti appartiene

> **Your Life. Your AI. Your Rules.**

**Versione**: 7.0
**Data**: 2026-10-23
**Applicazione**: LIA v4.2.0
**Licenza**: AGPL-3.0 (Open Source)

---

## Indice

1. [Perché LIA](#1-perché-lia)
2. [Cosa fa LIA per te](#2-cosa-fa-lia-per-te)
3. [A casa tua, per i tuoi cari](#3-a-casa-tua-per-i-tuoi-cari)
4. [Semplice da amministrare](#4-semplice-da-amministrare)
5. [Niente di nascosto](#5-niente-di-nascosto)
6. [Un'assistente che ti conosce](#6-unassistente-che-ti-conosce)
7. [Agisce lei, decidi tu](#7-agisce-lei-decidi-tu)
8. [Aperta](#8-aperta)
9. [Cosa LIA non è, e dove va](#9-cosa-lia-non-è-e-dove-va)

---

## 1. Perché LIA

ChatGPT, Gemini, Copilot o Claude sanno già agire per te: leggere le tue email, riempire la tua agenda, cercare sul web. Ma le tue conversazioni vivono sui loro server, non vedi cosa succede tra la tua domanda e la risposta, e il giorno in cui te ne vai, ciò che sanno di te resta da loro.

LIA prende un'altra strada. È un assistente personale che installi sul tuo server, che puoi capire da cima a fondo e che tieni sotto il tuo controllo. Non è un modello di IA in più: fa lavorare i modelli che scegli e organizza attorno a loro i tuoi servizi, la tua memoria e le tue regole.

Il meccanismo è spiegato nella [guida tecnica](/it/how). Il modo in cui il codice è stato scritto, da un'IA diretta e controllata da un essere umano, è raccontato nel [resoconto di esperienza](/it/story).

## 2. Cosa fa LIA per te

Le parli normalmente, per iscritto o a voce. L'interfaccia esiste in sei lingue (francese, inglese, tedesco, spagnolo, italiano, cinese) e la tua dettatura viene trascritta nella lingua del tuo account. Una ventina di agenti specializzati si dividono il lavoro: i tuoi dati personali, il web, la creazione, la casa connessa, la navigazione sui siti e l'anticipazione.

Un interruttore nella chat sceglie il suo modo di ragionare. La modalità **Pipeline**, predefinita, prepara tutti i passaggi, li verifica e poi li esegue in parallelo: è prevedibile e consuma da 4 a 8 volte meno token. La modalità **ReAct** procede passo dopo passo, più autonoma e più costosa, per una ricerca aperta; quando un passaggio richiede un vero calcolo, scrive alcune righe di Python e le lancia in una sandbox blindata, che esce sul web solo attraverso un unico proxy e senza le tue chiavi ([privacy](/it/faq#faq-privacy), [il percorso di un messaggio](/it/how#pipeline)).

Se scegli la visualizzazione a **schede** (le altre due modalità sono l'HTML semplice e il Markdown), le risposte che portano dati arrivano così: foto di un luogo, meteo fascia oraria per fascia oraria, itinerario, anteprima di un documento. Una scheda mostra ciò che la fonte ha fornito, senza inventare nulla, e rispondere a un'email dalla sua scheda prepara la richiesta senza inviare nulla.

### I tuoi servizi

Chiedi a LIA di spostare il tuo appuntamento di giovedì: prepara la modifica e te la mostra prima di inviarla. Legge, cerca, riassume, scrive, invia e inoltra le tue email (Gmail, Outlook, Apple Mail), legge i loro allegati, anche una foto o una scansione, e gestisce le bozze della tua casella, che invia solo dopo la tua conferma. Tiene la tua agenda e i tuoi contatti su Google, Microsoft o Apple, le tue attività su Google o Microsoft, legge i tuoi file Drive e ci scrive solo con il tuo consenso, accende le tue lampade Philips Hue.

Senza configurare nulla, hai Wikipedia, la lettura di pagine web, i luoghi vicini con orari e recensioni, il meteo a cinque giorni con la qualità dell'aria e i pollini, e gli itinerari a piedi, in bici, in auto o con i mezzi pubblici ([connettori](/it/faq#faq-connectors)). Con le tue chiavi, la ricerca web incrocia anche Brave Search e Perplexity, e cita le sue fonti. LIA sa anche navigare un sito per te, cliccare, compilare un modulo.

### La voce

Tieni premuto il microfono, oppure dici «Dis LIA» per parlare a mani libere. Questa parola di attivazione viene riconosciuta sul tuo dispositivo, nulla parte prima che venga sentita; per ora esiste solo in francese, in beta. «LIA, stop» interrompe la sua voce. La tua dettatura viene trascritta sul tuo server o da un motore remoto, secondo la tua impostazione.

La **modalità Live** apre una conversazione vocale in tempo reale con la tua chiave Gemini Live, GPT-Live o ElevenLabs. La voce tiene la conversazione e affida ogni richiesta a LIA, che la tratta come un messaggio normale; in Live diretto, legge i tuoi dati senza agire. Un silenzio mette la sessione in standby senza fatturare nulla, e sei tu a chiuderla. Un avatar parlante sperimentale può accompagnare la voce con la tua chiave Simli; finché la sua connessione resta aperta, vengono fatturati anche i silenzi. Ciò che gira con le tue chiavi ti viene mostrato, ma LIA non lo registra né lo conteggia ([la voce](/it/faq#faq-voice_mode)).

### Creare e conservare

LIA crea e ritocca immagini con il modello scelto dall'amministratore, senza passare a un'opzione più cara delle tue preferenze. Facoltativamente, arricchisce la tua descrizione, e un'immagine si ritrova chiedendogliela ([immagini](/it/faq#faq-image_generation)). Produce veri file (CSV, Excel, Word, PowerPoint, PDF), costruiti da un motore locale e consegnati con la loro data di scadenza, schemi Excalidraw, e legge le foto e i PDF che alleghi. Le applicazioni MCP mostrano i loro moduli direttamente nella chat.

Ciò che produce, lo conservi, lo invii per email con un clic, condividi un'immagine con una persona collegata alla tua istanza, o lo lasci scadere. Una risposta conservata lascia la conversazione con la tua richiesta e la sua data, ed entra in uno spazio di conoscenza dove LIA la ritroverà settimane dopo.

### Prendere l'iniziativa

Se glielo permetti, LIA non si limita ad aspettare. Ti scrive quando la tua agenda, il meteo, le tue attività, le tue email o i tuoi interessi lo giustificano, e può avviare di sua iniziativa una conversazione personale. Alla fine di una riunione, ti chiede com'è andata. Quando la tua casella o la tua agenda si muovono, può reagire in pochi minuti, e «Sorveglia» tiene d'occhio una mail attesa fino al suo arrivo. Se sabato è prevista pioggia, guarda le tue attività all'aperto. Ricorda ciò a cui tieni davvero, e un argomento che rifiuti non torna.

Le affidi un ticket: lo prende in carico al suo ritmo e ti restituisce un risultato da accettare. Per un compito complesso, delega a sub-agenti che lavorano in parallelo. Routine e promemoria seguono ritmi ricchi (un martedì su due, il secondo martedì del mese, fino a una data), e una vista della settimana mostra ciò che è realmente successo ([l'iniziativa](/it/how#proactivity)).

### Gli altri

LIA fa una vera telefonata al posto tuo, all'officina o a un'amica, e ti riporta un riassunto scritto. Prima ti dice chi chiama e perché, e aspetta il tuo via libera. Con qualcun altro, non accetta alcun impegno a tuo nome, della tua agenda rivela solo se sei disponibile, e conserva solo un breve riassunto che scade. Può anche chiamare te, su un numero che hai verificato, e lì niente è limitato: all'altro capo del filo hai i tuoi dati e tutte le sue funzioni, con le azioni che restano confermate come nella chat. Questa modalità esiste solo se il fornitore telefonico può raggiungere la tua istanza ([telefonia](/it/faq#faq-telephony)).

Sulla stessa istanza, due persone collegate vedono i loro assistenti parlarsi: tu approvi il messaggio esatto, l'altro assistente lo trasmette con la sua personalità, il tuo conferma la consegna. Ogni connessione apre solo le condivisioni scelte, in sola lettura. Si trova qualcuno solo tramite la sua identità esatta, un blocco resta silenzioso (l'altro riceve la stessa risposta di uno sconosciuto), e i messaggi inoltrati si cancellano dopo trenta giorni. La pagina **Relazioni** riunisce, per ogni persona, gli impegni, le chiamate, i ricordi e i messaggi, con una sintesi in cima, senza raccogliere nulla di nuovo. Sei tu a unire due identità, per esempio «Papà» e un numero, in modo reversibile e senza scrivere nulla nelle tue fonti.

Il tuo telefono diventa anche un registratore di riunioni. Quando lo fermi, LIA trascrive e redige un verbale nel formato adatto, ti dice quale e perché, e lo invia nella chat, in PDF e per email, poi lo archivia in uno spazio «Riunioni» dove ritroverai ciò che è stato deciso. Un'interruzione costa solo qualche secondo di audio, una registrazione fatta altrove si può importare, e la trascrizione può restare interamente sul tuo server.

### E ancora

Una radio personale, avviata quando vuoi, mescola la tua giornata a notizie con le loro fonti e mostra quanto spende ([radio](/it/faq#faq-radio)).

Il tuo telefono, iPhone o Android, o qualsiasi sistema capace di inviare dati in JSON può anche trasmettere a LIA i tuoi SMS, il tuo numero di passi e la tua frequenza cardiaca, ciascuno tramite un token dedicato e revocabile. Gli SMS entrano in un archivio privato e cifrato che legge solo con un'autorizzazione a parte, senza mai conservare i codici di accesso. Le misurazioni sulla salute restano da te, dove le cancelli quando vuoi; il loro uso da parte dell'assistente è disattivato per impostazione predefinita e, se attivato, le trasmette solo un riassunto fattuale, senza alcuna diagnosi medica.

La conversazione segue i tuoi altri dispositivi senza ricaricare la pagina.

## 3. A casa tua, per i tuoi cari

LIA è un server che installi una volta e condividi con la tua famiglia, i tuoi amici o il tuo team. Ogni account ha il suo profilo, la sua lingua, i suoi connettori, i suoi documenti privati e il suo rapporto con l'assistente. Memoria e diari sono separati da un account all'altro, e un account si apre solo con il consenso dell'amministratore: accedere con Google dimostra un indirizzo, non un'approvazione ([privacy](/it/faq#faq-privacy)). Ognuno vede il proprio consumo in tempo reale.

Un Raspberry Pi 5, un computer da circa 80 euro, basta per tutta la famiglia: LIA ci gira in produzione giorno e notte, monitoraggio compreso. Vanno bene anche un NAS, un piccolo server a noleggio o una macchina aziendale. Un modello di IA locale può ricoprire qualsiasi ruolo testuale, dalla conversazione ai compiti in background, e questa scelta si cambia ruolo per ruolo, senza ridistribuire.

I tuoi dati vivono nel database del tuo server. Li esporti (segreti esclusi), li salvi o ne chiedi la cancellazione, e i tuoi dispositivi collegati si possono revocare. La tua posizione viene conservata solo se lo scegli, senza cronologia. Un'email o una pagina web arriva etichettata come materiale da analizzare, non come un ordine da eseguire. I log del server conservano numeri e codici, non i tuoi contenuti, con un'eccezione: il messaggio d'errore di un servizio esterno in un formato sconosciuto può ancora citarne un frammento. Un limite da conoscere: un modello remoto riceve i dati utili alla sua parte della richiesta.

Sul telefono, un'unica app per store fa da finestra sul tuo server. Inserisci il suo indirizzo una volta, e su Android le sue notifiche non passano dall'editore dell'app; su iOS, un relay minimale sveglia il telefono con una frase fissa ([self-hosting](/it/faq#faq-self_hosting)).

Il **mondo di LIA** dà all'istanza una casa e un giardino condivisi. Ci passeggi con il tuo avatar, incontri gli altri, giochi a un cabinato arcade, ti siedi a un tavolo dove LIA ti porta la tua dashboard. La tua casa, i tuoi documenti e la tua assistente restano privati, e una stanza del mondo apre le stesse funzioni dell'app, con gli stessi diritti e le stesse conferme ([il mondo](/it/faq#faq-world)).

## 4. Semplice da amministrare

Un installer guidato (`./install.sh`) fa qualche domanda, in francese o in inglese, crea l'account amministratore senza scrivere segreti in chiaro, verifica che tutto funzioni davvero e riprende da dove si era fermato se un passaggio fallisce. Ogni passaggio è descritto in una guida passo passo. La prima configurazione richiede comunque un po' di tempo e qualche base tecnica. Un aggiornamento segue una procedura scritta che inizia con un backup, perché non si torna indietro una volta applicate le migrazioni ([self-hosting](/it/faq#faq-self_hosting)).

Poi, tutto si regola nell'interfaccia web, senza terminale né file di configurazione, da computer, tablet o telefono ([primi passi](/it/faq#faq-getting_started)). Un assistente completo deve potersi usare con la stessa semplicità di un'app per il grande pubblico. Ognuno ha il suo spazio di impostazioni, con una ricerca che capisce la tua lingua: collegare Google o Microsoft con una sola autorizzazione ([connettori](/it/faq#faq-connectors)), scegliere la personalità di LIA (professore, amico, coach, poeta…) e le sue voci, regolare l'aspetto, decidere cosa impara e quando ti interpella, aggiungere i tuoi server MCP, le tue skills e i tuoi spazi di conoscenza, che possono seguire una cartella Drive o un'etichetta Gmail. Scegli anche il tuo ritmo di scambi, frequenti o occasionali, perché LIA tragga il massimo dalla cache del fornitore.

Puoi anche regolare LIA parlandole: «Mostra le mie risposte come schede». Una lettura o una piccola impostazione reversibile avviene subito; una creazione, una cancellazione o una modifica sensibile mantiene la sua conferma. Una password o una chiave passano dal tuo browser, non dalla chat, e un comando non aggira alcuna protezione ([privacy](/it/faq#faq-privacy)). Poi LIA dice cosa è realmente successo, compreso un risultato parziale o un conflitto, senza pretendere di conoscere ogni effetto interno di uno strumento.

L'amministratore ha la sua scheda. Apre gli account, vede ciò che ognuno usa, fissa limiti per persona (token, messaggi, costo) e un budget giornaliero per tutta l'istanza. Attiva o spegne ogni funzione senza ridistribuire, e spegnere una funzione ferma la capacità senza cancellare ciò che esiste: senza memoria, LIA non impara più, ma ciò che sa resta leggibile. Sceglie i fornitori, un modello per ruolo e la sua profondità di ragionamento, con chiavi archiviate cifrate, e tiene il listino prezzi, che può modificare in Excel. Gestisce anche le personalità, le skills, la FAQ e la sintesi vocale dell'istanza; clonare una voce richiede prima un'attestazione di consenso iscritta nel log di audit. LIA, dal canto suo, sorveglia la propria salute, diagnostica i suoi incidenti e avvisa l'amministratore, che può anche interrogare il suo server in linguaggio naturale dalla chat.

L'accessibilità punta al livello AA delle WCAG 2.2, il colore non porta da solo il significato, e i controlli automatici completano la valutazione manuale senza sostituirla.

## 5. Niente di nascosto

Vedi quali modelli vengono chiamati, quanti token, quale costo e perché una certa decisione. Ogni messaggio mostra il suo costo in euro, una riga compressa sotto ogni risposta, una volta aperta, mostra ciò che è realmente successo, e quando uno dei tuoi server MCP tarda a prepararsi, LIA lo nomina invece di farti aspettare in silenzio. Se l'amministratore lo attiva, un pannello di debug mostra in diretta il piano, ogni strumento e ogni chiamata al modello. Nessun abbonamento che nasconde i costi: puoi mettere un modello economico dove basta, e LIA ottimizza da sola ciò che consuma. Tutto ciò che la piattaforma paga per te, chiamata, sessione live o sintesi vocale, entra nel tuo utilizzo, al prezzo che il fornitore fattura davvero. Il tuo parere su una risposta (👍 o 👎) resta nel tuo database, senza analytics di terzi.

LIA non ti presenta come fatto ciò che i suoi strumenti hanno rifiutato, e ciò che una schermata afferma sui tuoi dati è esatto o assente. Ogni protezione dichiarata poggia su un test che fallisce se essa scompare. L'audit tecnico completo, punti deboli compresi, è pubblico con il suo protocollo, e la FAQ ha una sezione per ogni funzione.

Ciò che LIA conclude su di te, lo correggi tu. Ricordi, diari e interessi si rileggono, si correggono o si cancellano, e la correzione vale ovunque. LIA conserva un rimando a ciò che l'ha portata a una conclusione, non una copia, quindi una conversazione cancellata non ricompare da nessuna parte. Ciò che crede di sapere sul tuo ritmo si ispeziona, si mette in pausa o si cancella in un pannello delle abitudini, spento finché non lo attivi, e le routine che propone aspettano il tuo consenso. Una regola tratta dalle tue istruzioni («rispondi più breve») diventa un ricordo che puoi modificare.

Infine, LIA tiene tre **registri**: ciò che ha fatto per te, ciò che ha consultato («la tua agenda», senza ciò che è stato cercato) e ogni scambio. Ciò che intraprende di sua iniziativa ha la sua scheda. Un'azione viene registrata prima di avvenire e chiusa solo su un risultato reale. I registri si leggono in grafici, si esportano per intero, possono essere sigillati con impronte che verifichi in prima persona, e LIA li usa per risponderti quando le chiedi cosa ha fatto ([i registri](/it/faq#faq-registers)). Con i parametri inviati ai modelli e le lacune del registro, fanno cinque forme di prova. Il regolamento europeo sull'IA non classifica automaticamente un assistente personale tra i sistemi ad alto rischio: queste prove sono una scelta di trasparenza, non una certificazione.

## 6. Un'assistente che ti conosce

Al di là dei fatti, LIA si costruisce una comprensione psicologica di te. Ogni ricordo porta un peso emotivo e un'importanza, e puoi consultare, fissare, correggere o cancellare tutto, oppure spegnere l'estrazione automatica.

Il **Psyche Engine** le dà uno stato interiore che evolve a ogni scambio, laddove i grandi assistenti mantengono una personalità fissa. Il rapporto si approfondisce, e le sue emozioni si leggono senza essere dette: un vocabolario che si fa più caldo, frasi che si accorciano sotto tensione, umorismo quando lo scambio è leggero. Regoli tu i suoi tratti caratteriali. Impara anche, ambito per ambito e in via sperimentale, dove è affidabile, a partire da prove e non dal proprio voto; dove le prove mancano, verifica, chiede o dichiara il suo limite. Fuori dalla chat, un compagno animato resta al tuo fianco sulla dashboard, dove l'hai messo.

Tiene i propri **diari** in prima persona, e da questi taccuini nasce un tuo ritratto che l'accompagna ovunque parli. Li leggi, li modifichi, segnali un errore o avvii un consolidamento; il ritratto in sé non si modifica direttamente, per restare coerente. Quando riaffiora un ricordo doloroso, passa in modalità protettiva: niente battute, niente minimizzazioni. E se le chiedi cosa sa fare, risponde attingendo a una base di conoscenza sulle proprie funzioni ([la memoria](/it/how#memory)).

## 7. Agisce lei, decidi tu

Prima di un'azione sensibile, LIA te la sottopone. Ciò che approvi è esattamente ciò che verrà eseguito, anche dopo diversi ritocchi, e la conferma mostra tutto ciò che sta per partire. Davanti a un'azione che non ha il diritto di fare da sola, ti chiede sul ticket; una routine che gira senza nessuno davanti allo schermo rifiuta l'azione e lo dice. Il codice di una skill gira in un container usa e getta, senza accesso ai tuoi file né alle tue chiavi, e senza rete al di fuori degli host autorizzati.

Si attiene a ciò che ha realmente ottenuto. La risposta si basa sui risultati reali degli strumenti, un'informazione introvabile viene dichiarata mancante, e un fallimento viene nominato insieme al servizio in causa. I calcoli, le durate tra due date e le conversioni di valuta passano da strumenti esatti.

Una domanda continua a essere elaborata se chiudi la scheda, e il pulsante stop la interrompe in un secondo. Il database viene salvato ogni notte e il ripristino è testato davvero; la copia fuori sede e gli allegati restano da prevedere a cura dell'operatore. Un monitoraggio completo fa parte dell'architettura fin dall'inizio; le sue metriche non contengono né nomi né ricerche, e ogni componente del server è fissato alla sua impronta ([privacy](/it/faq#faq-privacy), [osservare e misurare](/it/how#observability)).

L'operatore può affidare alcune decisioni precise a un motore dedicato, come scegliere il formato di un verbale. Quando questo motore è in dubbio, il compito torna all'elaborazione abituale, i permessi restano in LIA, e ogni uso è visibile e si può ritirare.

## 8. Aperta

LIA lavora con OpenAI, Anthropic, Google, DeepSeek, Perplexity, Qwen e, per i modelli locali, Ollama. Li combini ruolo per ruolo, e se uno cambia i prezzi o peggiora, passi subito a un altro ([i modelli](/it/how#llm)).

Parla standard aperti e pubblici invece di un protocollo fatto in casa, e la sua architettura è fatta per accogliere altri connettori, canali e fornitori. Con **MCP**, colleghi strumenti esterni senza scrivere codice. Un plugin in formato Agent Plugins si installa e si disinstalla in modo pulito. Le **skills** in formato agentskills.io aggiungono competenze scritte in linguaggio naturale; un generatore ti aiuta a crearne, una skill si installa da un indirizzo https o dalla libreria skills.sh e può mostrare una piccola applicazione nella chat o restituirti dei file. Una skill venuta da fuori lavora a parte, senza toccare i tuoi connettori, e ciò che costruisci in questo ecosistema ti segue. Una connessione di fiducia può trasmetterti una skill o un plugin: ne ricevi una copia disattivata, senza le sue credenziali, e attivarla ti impegna come se l'avessi creata tu.

I tuoi account si collegano tramite OAuth 2.1 senza che LIA conosca la loro password, e una passkey ti fa accedere senza alcuna password. Ogni versione pubblica l'inventario esatto di ciò che contiene e viene installata su macchine vergini prima di essere pubblicata ([sicurezza](/it/faq#faq-privacy)). Ogni decisione di architettura è scritta e archiviata sulle [mappe](/it/maps). Il codice è sotto AGPL-3.0: puoi sottoporlo ad audit, modificarlo, e deve restare aperto.

Ritrovi LIA nel browser, nell'app mobile con le sue notifiche push, e su Telegram, dove le conferme si fanno con dei pulsanti e dove risponde anche ai tuoi messaggi vocali. La stessa memoria ti segue ovunque.

## 9. Cosa LIA non è, e dove va

LIA non è un concorrente dei giganti del cloud. Per chiacchierare, un modello usato nella sua app sarà probabilmente più fluido. Non è un'intelligenza artificiale generale, ma un'intelligenza pratica e relazionale, al servizio di una persona. Le sue protezioni non garantiscono da sole la conformità al GDPR di un'installazione, che dipende anche da come viene gestita, e le tracce diagnostiche dei modelli, facoltative, possono conservare del contesto: richiedono una configurazione esplicita.

Ciò che le interessa è il tempo lungo. Memoria, diari, apprendimento e Psyche Engine si combinano perché, mese dopo mese, LIA ti capisca sempre meglio. Esiste perché mancava un assistente che fosse davvero tuo.
