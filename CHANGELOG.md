# Changelog

Tutte le versioni sono state provate su un impianto reale: Hy-Gain T2X con
controller DCU-1, macOS, WSJT-X e N1MM+.

## 1.7.0

- Modalità compatta della finestra (Ctrl+K): caratteri e spaziature ridotti,
  preset e registro nascosti. Minimo da 940×616 a circa 520×320, e a 290×320
  nascondendo anche il quadrante.
- Voci di menu per nascondere quadrante e registro separatamente, "Sempre in
  primo piano" e "Riduci al minimo" (Ctrl+M).
- Posizione e dimensioni della finestra salvate alla chiusura e ripristinate
  all'avvio.
- Il quadrante scende fino a 110 pixel ridisegnandosi in scala.

## 1.6.0

- Filtro per bande: nuova scheda Impostazioni → Bande, per limitare l'azione
  alle sole bande la cui antenna sta davvero sul rotatore. Scorciatoia "Solo
  direttiva" per 20-17-15-12-10-6.
- La banda si ricava dalla frequenza dei messaggi Status di WSJT-X; le
  decodifiche, che non la contengono, ereditano l'ultima frequenza vista.
- Se il campo DX Call viene svuotato in WSJT-X, il riquadro Stazione DX si
  azzera: campi, azimut e bersaglio sul quadrante.
- Rimosso il riquadro dell'attività di banda, poco utile alla prova pratica.

## 1.5.0

- Il comando di arresto viene ripetuto più volte a distanza di qualche decimo
  di secondo: alcuni DCU-1 scartano i comandi ricevuti mentre stanno eseguendo
  la sequenza di avvio.
- `AM1;` non viene più inviato a rotore fermo, dove faceva sbloccare il freno
  senza motivo.
- Nuovo modo di arresto "solo set point": invia `AP1<posizione attuale>;` senza
  `AM1;`, fermando il rotore senza ciclare la meccanica.
- I messaggi provenienti dai thread di servizio passano per un segnale Qt:
  prima venivano scritti nel registro dal thread sbagliato, con rischio di
  chiusura improvvisa.

## 1.4.0

- Le sorgenti non abilitate per l'automatismo non cambiano più il puntamento
  mostrato né i campi Call e Grid.
- Il campo Call segue davvero la stazione ricevuta: la protezione contro la
  sovrascrittura si basa sulla digitazione reale e non sul focus, che Qt
  assegna al primo campo della finestra.
- Registro con versione, fermo meccanico e una riga per ogni stazione ricevuta.

## 1.3.0

- Pausa configurabile fra `AP1xxx;` e `AM1;`: senza, alcuni controller
  perdevano il comando di movimento e serviva un secondo click.
- Attesa dopo l'apertura della porta seriale, per gli adattatori USB che
  muovono DTR/RTS e fanno perdere i primi byte.
- Console per l'invio di comandi grezzi al controller (Rotore → Invia comando
  grezzo), con pulsanti rapidi per la diagnostica.
- Tre modi di arresto selezionabili.

## 1.2.0

- Lettura della posizione con `AI1;` per i controller che la supportano
  (Rotor-EZ, Green Heron RT-21), con pulsante di prova, polling e arresto
  automatico se la posizione letta entra nel margine di sicurezza.
- Documentato che il DCU-1 originale la posizione non la restituisce.

## 1.1.0

- Margine di sicurezza dal fermo meccanico: i comandi che vi cadono dentro
  vengono limitati al bordo, dal lato da cui si arriva, invece di mandare
  l'antenna in battuta. Zona protetta disegnata sul quadrante.
- Corretto il caso dell'azimut coincidente col fermo, che veniva raggiunto
  facendo tutto il giro all'indietro invece dei pochi gradi in avanti.

## 1.0.0

Prima versione: protocollo DCU-1, stima di posizione con modello del fermo
meccanico, decodifica UDP di WSJT-X e N1MM+, risoluzione DXCC con cty.dat e
tabella interna, rotta ortodromica da locatore Maidenhead, rosa dei venti
interattiva, auto-rotazione a soglia, modalità headless.
