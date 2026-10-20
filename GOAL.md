# Goal: EDMC Spansh Fleet Carrier Parking Finder

## Regole operative
1. Procedere in ordine, completando un solo task per volta; dopo ogni task fermarsi e attendere la conferma esplicita dell'utente.
2. Mantenere `parking_finder.py` indipendente da rete, UI e API EDMC: il core riceve dati e produce risultati strutturati.
3. Rispettare la separazione dei componenti:
   - `load.py`: bootstrap e lifecycle EDMC; inoltra eventi e input ai componenti dedicati.
   - `spansh_client.py`: richieste Spansh, payload e gestione degli errori del provider.
   - `parking_service.py`: acquisisce e normalizza i dati, invoca il core e inoltra risultati/errori.
   - `parking_finder.py`: logica pura per valutare i dati ricevuti.
   - `parking_ui.py`: widget, input e presentazione localizzata; non implementa protocollo Spansh o logica di parcheggio.
4. Per ogni nuova stringa visibile, usare `plugin_tl("...")` in `parking_ui.py` e aggiungere un commento `# LANG: ...`. Il contesto di traduzione resta `load.py`.
5. `version` è l'unica fonte della versione del plugin; `load.py` la legge all'avvio. Mantenere `0.x.x` durante la pre-release e riservare `1.0.0` alla release finale. Aggiornare la versione per release o traguardi funzionali concordati, non per modifiche esclusivamente documentali o di pianificazione.
6. Aggiornare `README.md` per descrivere solo comportamenti effettivamente implementati e verificati. Aggiornare lo stato qui dopo ogni task completato.
7. Prima di chiudere ogni task, controllare se il lavoro completato è una release o un traguardo funzionale: aggiornare `version` quando lo è, lasciarla invariata per modifiche solo documentali/pianificazione e indicare sempre nel riepilogo finale il valore precedente e quello finale con la motivazione.

## Obiettivo
Dato un sistema di riferimento, mostrare il sistema più vicino entro 25 Ly nel quale la capacità teorica di parcheggio non risulti esaurita e che non sia noto come soggetto a permesso. Rendere esplicito quando il risultato è solo teorico: non dichiarare disponibilità reale/confermata senza dati sufficienti sull'occupazione dei Fleet Carrier. Presentare risultati ed errori nell'interfaccia EDMC con traduzioni compatibili.

## Stato già implementato
- [x] Client Spansh con payload per ricerca sistemi entro un raggio, timeout ed errori espliciti.
- [x] Core standalone rispetto a rete e UI: filtra candidati entro raggio, esclude i record che Spansh segnala come soggetti a permesso e ordina i candidati per distanza.
- [x] Calcolo della capacità teorica: 16 slot per corpo, massimo 128 per sistema, basato sul numero di corpi fornito.
- [x] Integrazione provider/core tramite `parking_service.py`, con normalizzazione dei record e inoltro degli errori.
- [x] UI separata in `parking_ui.py`, input manuale, aggiornamento del sistema corrente dal journal e ricerca asincrona.
- [x] Localizzazione delle stringhe UI con `plugin_tl` e marcatori `# LANG`; contesto di traduzione `load.py`.
- [x] `load.py` legge la versione dal file `version`.
- [x] La ricerca Spansh dei sistemi vicini applica `needs_permit: false`; non esiste una lista locale, un servizio di aggiornamento o una GitHub Action per i permessi.
- [x] README descrive la capacità corrente come teorica e segnala che query target dedicata e assegnazione live degli slot non sono implementate.

## Roadmap (un task per volta)

### 1. Contratto unificato dei risultati
- [x] Definire e documentare la struttura di risultato condivisa tra core, service e UI.
- [x] Includere almeno nome sistema, distanza, stato/motivo di accesso, capacità teorica, disponibilità confermata opzionale e dettagli dei corpi.
- [x] Distinguere esplicitamente i dati mancanti da zero slot confermati; non presentare una stima teorica come disponibilità reale.
- [x] Aggiungere test del contratto e della compatibilità con i record attuali.

### 2. Valutazione del target e fallback
- [x] Garantire che il sistema richiesto venga identificato con corrispondenza esatta e valutato prima degli altri candidati.
- [x] Verificare come la risposta reale di Spansh rappresenta il sistema di riferimento; usare il provider e i payload supportati, senza presumere un endpoint target dedicato.
- [x] Se il target non è idoneo, valutare i candidati forniti entro 25 Ly in ordine crescente di distanza.
- [x] Definire e testare gli esiti per target assente, pieno secondo i dati disponibili e non accessibile. Target assente e non accessibile attivano il fallback; un target con carrier Spansh pari alla capacità teorica viene saltato. L'occupazione resta una stima del provider, non una disponibilità confermata.

### 3. Capacità e disponibilità
- [x] Verificare, con fixture rappresentative dei payload Spansh, quali dati di Fleet Carrier, corpi e saturazione sono effettivamente disponibili. La documentazione e le risposte reali espongono `body_count`, `bodies` e `stations`; i carrier sono riconoscibili dal tipo `Drake-Class Carrier`. Non è presente un campo di saturazione o di slot liberi, quindi il conteggio è una stima derivata.
- [x] Mantenere la capacità teorica (16 per corpo, massimo 128 per sistema) distinta dalla disponibilità confermata; esporre separatamente la stima basata sui carrier elencati da Spansh.
- [x] Implementare l'assegnazione stimata ai corpi e il conteggio dei carrier Spansh. Confrontare le distanze di arrivo radiali in km, assegnare ogni carrier con distanza valida al corpo più vicino con meno di 16 assegnazioni e passare al successivo quando raggiunge 16; omettere e registrare a livello debug le carrier senza distanza. Se `updated_at` indica dati più vecchi di 24 ore, marcarli obsoleti e registrarlo a livello debug, ma scartare comunque i sistemi stimati pieni. Questa è un'euristica, non una posizione/occupazione confermata; la capacità totale resta limitata a 128.
- [x] Se Spansh non fornisce la lista delle stazioni, mantenere occupazione e disponibilità stimate come sconosciute e non scartare il sistema per supposizione; la disponibilità confermata resta sempre sconosciuta.
- [x] Testare limiti, corpi mancanti, saturazione per corpo, sistema pieno e dati incompleti.

### 4. Filtro permessi Spansh
- [x] Applicare il filtro `needs_permit: false` nella ricerca Spansh insieme al raggio e all'ordinamento.
- [x] Normalizzare il flag `needs_permit` dei record Spansh nel contratto e mantenere il controllo dei record esplicitamente limitati nel core.
- [x] Rimuovere lista locale `known_permits.json`, updater EDMC, servizio e script di sincronizzazione, workflow GitHub e relativi test.
- [x] Testare il payload della ricerca e la normalizzazione del flag restituito dall'API.
- [x] Documentare che il provider può omettere il target e che il plugin non può conoscere il motivo dell'omissione.

### 5. UI, localizzazione e errori
- [x] Mappare il contratto dei risultati in `parking_ui.py`, mostrando in modo distinto capacità teorica, disponibilità confermata o stato sconosciuto.
- [x] Mostrare lo stato e il motivo di accesso previsti dal contratto; distinguere accesso consentito, limitato e sconosciuto senza trattare l'assenza del flag Spansh come conferma di accessibilità.
- [x] Presentare nomi e dettagli dei corpi come informazioni del provider o del journal, senza descriverli come posizione verificata del Fleet Carrier se i dati non dimostrano una corrispondenza effettiva.
- [x] Tradurre ogni nuovo testo visibile con `plugin_tl` e `# LANG` nel componente UI.
- [x] Distinguere nella UI gli errori di timeout/rete/API dagli esiti validi senza risultati, mantenendo l'aggiornamento Tkinter sul thread UI.
- [x] Rigenerare `L10n/en.template` con `script/find_localised_strings.py` quando cambiano le stringhe UI e usare l'opzione `--compare-lang` per verificare il template; aggiornare le traduzioni mantenute dal progetto e la documentazione necessaria.

### 6. Verifica e rilascio
- [x] Aggiungere test del core per permessi, ordinamento per distanza, limite di raggio, capacità ai limiti e dati mancanti o non validi.
- [x] Aggiungere test del client Spansh con risposte simulate per payload, timeout, errori HTTP, JSON non valido e strutture di risposta supportate.
- [ ] Ampliare i test del service per i record normalizzati, il contratto condiviso e i casi di dati incompleti.
- [ ] Aggiungere test UI per risultati teorici, disponibilità sconosciuta o confermata, accesso sconosciuto o limitato, nessun risultato ed errori; verificare che gli aggiornamenti Tkinter avvengano sul thread UI.
- [ ] Verificare che messaggi e dettagli non vengano presentati come disponibilità o posizione confermata senza dati che lo dimostrino.
- [ ] Eseguire i controlli mirati e la suite disponibile prima di dichiarare completato ciascun comportamento.
- [ ] Aggiornare README e stato del goal alle funzionalità realmente verificate.
- [ ] Aggiornare `version` quando una modifica costituisce un rilascio o un traguardo funzionale concordato.
