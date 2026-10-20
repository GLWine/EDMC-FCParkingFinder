# 🎯 GOAL.md: Plugin EDMC Spansh Fleet Carrier Parking Finder

## ⚠️ Regole Operative per gli Agenti
1. **Esecuzione Sequenziale:** Esegui **un solo task alla volta** in ordine progressivo.
2. **Richiesta Conferma:** Dopo aver completato un singolo task, fermati e attendi la conferma esplicita dell'utente prima di passare al task successivo.
3. **Indipendenza Core:** Il modulo `parking_finder.py` deve rimanere completamente **standalone** (senza dipendenze EDMC dirette all'infuori della logica pura di ricerca e payload).
4. **Localizzazione EDMC:** Qualsiasi stringa di testo visibile nell'interfaccia deve usare la funzione `plugin_tl("...")` con il relativo commento marcatore `# LANG: ...` in `load.py`.
5. **Versionamento:** Durante la fase di sviluppo avanzare solo con la versione patch (`0.3.x`). La modifica del numero di versione minor/major sarà riservata alla release finale.
6. **Verifica documentazione a ogni task:** Dopo aver completato ciascun task, verificare se `GOAL.md`, `README.md` o `version` devono essere aggiornati e apportare gli aggiornamenti pertinenti. Aggiornare subito lo stato dei task in `GOAL.md`; completare gli aggiornamenti previsti dai punti 4.1 e 4.2 alla fine dell'obiettivo, senza anticiparli con informazioni incomplete.

---

## 📌 Obiettivo Finale (Goal)
* [ ] Il plugin funziona completamente: verifica la disponibilità di spazio nel sistema richiesto dall'utente, altrimenti cerca nei sistemi vicini entro 25 Ly tramite le API e i payload di Spansh, mantenendo la piena compatibilità con il sistema di traduzione ad hoc di EDMC e aggiornando documentazione (`README.md`) e versione (`version`, partendo dalla versione attuale `0.3.2`).

---

## ✅ Elementi Fatti
- [x] Struttura base del client Spansh (`spansh_client.py`) con gestione di timeout, eccezioni personalizzate e header di rete.
- [x] Costruzione del payload JSON per le query di ricerca sistemi per distanza ed entro il raggio di ricerca in `spansh_client.py`.
- [x] Predisposizione del sistema di traduzione nativo EDMC con `plugin_tl` e tag `# LANG:` nel file principale `load.py`.
- [x] Interfaccia grafica base e gestione multithread asincrona dei dati di gioco/journal in `load.py`.

---

## ⏳ Elementi da Fare (Nuovi)

### 1. Architettura Standalone (`parking_finder.py`)
- [x] **1.1** Rimuovere ogni dipendenza residua dalle API EDSM all'interno di `ParkingSystemFinder`.
- [ ] **1.2** Mantenere `parking_finder.py` del tutto privo di riferimenti alla GUI o alle funzioni di traduzione di EDMC, restituendo solo strutture dati "pure" (`dict`/`list`/`bool`) per consentirne l'uso standalone.
- [ ] **1.3** Integrare `SpanshClient` in `ParkingSystemFinder` come motore primario di ricerca.
- [ ] **1.4** Definire un modello di risposta unificato per `parking_finder.py` che contenga: nome sistema, distanza, lock da permesso, slot teorici/reali e dettagli corpi celesti.

### 2. Logica di Parcheggio & Verifica Slot
- [ ] **2.1** Costruire la query di verifica diretta sul sistema target inserito dall'utente.
- [ ] **2.2** Implementare la logica di fallback sferica: estendere la ricerca ai sistemi entro 25 Ly ordinati per distanza se il sistema target è pieno o bloccato da permesso.
- [ ] **2.3** Calcolare gli slot Fleet Carrier disponibili usando i dati Spansh: verificare per primo il totale di FC nel sistema e scartare subito i sistemi con almeno 128 FC, senza elaborare le assegnazioni ai corpi; altrimenti associare ogni FC al pianeta o alla stella con distanza dall'arrivo più simile, assegnandolo al successivo corpo disponibile se quello più vicino ha già 16 FC. Considerare un massimo di 16 FC per corpo e 128 FC per sistema.
- [ ] **2.4** Verificare ed escludere i sistemi richiedenti permesso tramite lista locale (`known_permits.json`) o flag restituiti da Spansh.

### 3. Localizzazione & Conformità EDMC (`load.py`)
- [ ] **3.1** Racchiudere ogni stringa utente nuova/aggiornata nella funzione `plugin_tl("...")`.
- [ ] **3.2** Aggiungere il marcatore `# LANG: <descrizione>` su ogni riga di testo visualizzabile per consentire l'estrazione automatica via script EDMC.
- [ ] **3.3** Mappare i risultati restituiti da `parking_finder.py` nelle label UI e nei tooltip localizzati di `load.py`.

### 4. Rilascio, Documentazione e Versione
- [ ] **4.1** Aggiornare il file `README.md` documentando il passaggio alle Spansh API, le nuove funzionalità e i dettagli di ricerca nel raggio di 25 Ly.
- [ ] **4.2** Incrementare il file `version` seguendo la progressione patch `0.x.x` (es. `0.4.3`) fino al completamento e alla release finale.

---

## 🔄 Elementi da Rifare e Ottimizzare

### 1. Refactoring Parser Spansh (`spansh_client.py` & `parking_finder.py`)
- [ ] **R1.1** Rifare il parsing dei risultati JSON di Spansh per isolare la struttura dati dei corpi celesti (pianeti/lune) e i dettagli di saturazione.
- [ ] **R1.2** Adattare la funzione `_clean_body_name` per gestire la nomenclatura dei corpi restituita dal payload Spansh.

### 2. Gestione Thread & Risposte UI (`load.py`)
- [ ] **R2.1** Refattorizzare il callback asincrono `_update_result` per gestire in modo sicuro le eccezioni sollevate da Spansh (`SpanshTimeoutError`, `SpanshAPIError`).
- [ ] **R2.2** Aggiornare la visualizzazione degli errori nell'interfaccia utente (es. timeout, rete offline, sistema non trovato) applicando le dovute stringhe localizzate.
