ForældreIntra til Email
=======================

ForældreIntra er en del af SkoleIntra, der brugers af næsten alle danske folkeskoler til kommunikation mellem skole og hjem. ```fskintra``` logger på ForældreIntra og konverterer indholdet til almindelige emails.


Hvordan?
========

Se i underkataloget ```docs``` eller på [ dokumentationshjemmesiden](https://svalgaard.github.io/fskintra/) for information om, hvordan du installerer ```fskintra```.


Opbevaring af data
==================

### Markeringer af sendte mails (`--prune-markers`)

Hver sendt mail giver et katalog `dato--type--md5--id` i `msg/`. Det er
det, der forhindrer, at samme indhold sendes to gange, og som standard
slettes de aldrig. Med `--prune-markers DAYS` (eller
`FSKINTRA_PRUNE_MARKERS_DAYS`) slettes en markering, når indholdet **ikke
har været at se på ForældreIntra i `DAYS` dage**. Mindste værdi er **30**;
lavere værdier afvises, og fskintra stopper med en fejl.

**Hvorfor "sidst set" og ikke datoen i navnet?** ForældreIntras sider har
ingen tidsgrænse. fskintra behandler alt, siden viser, hver gang:

| Side | Hvad vises | Hvor langt tilbage |
| --- | --- | --- |
| Forside (`frp`) | Alle opslag på opslagstavlen | Til skolen fjerner opslaget - ofte måneder |
| Beskeder (`msg`) | Listen af samtaler. Er den seneste besked i en tråd ny, hentes **hele** tråden | Så længe tråden står på listen; en tråd kan være flere år gammel |
| Dokumenter (`doc`) | Alle dokumenter i klassens mappe og undermapper | Til de slettes - typisk hele skoleforløbet |
| Billeder (`pht`) | Alle album og alle billeder i dem | Til de slettes - typisk hele skoleforløbet |
| Ugeplaner (`pln`), lektier (`hwk`) | De uger, siden viser | Få uger |

Der findes derfor **ingen** sikker aldersgrænse målt på datoen: slettes
markeringen for et tre år gammelt dokument, der stadig ligger i mappen,
sendes det som nyt ved næste kørsel. I stedet fornyer fskintra en
markerings tidsstempel, hver gang indholdet findes på siden, og sletter kun
dem, der ikke er fundet i `DAYS` dage. Indhold, der stadig vises, sendes
altså ikke igen, uanset hvor gammelt det er.

Tabellen er udledt af, hvordan fskintra læser siderne (`pgFrontpage`,
`pgDialogue`, `pgDocuments`, `pgPhotos`) - den er ikke målt på en bestemt
skoles ForældreIntra, og skoler rydder op forskelligt.

**Hvad dækker minimum på 30 dage?** Indhold, der kun er væk midlertidigt og
dukker op igen: fejlsider hos ForældreIntra, et barn der en periode ikke
vises, eller et afsnit der ikke kan hentes. Dukker indholdet op igen efter
mere end `DAYS` dage, sendes det som nyt. Værd at vide, før du vælger:

* **Gamle tråde, der får et nyt svar.** Viser listen af samtaler ikke
  længere en tråd, bliver dens markeringer ikke fornyet. Kommer der et svar
  i den efter mere end `DAYS` dage, sendes hele tråden igen - ikke kun det
  nye svar. Vælg en høj værdi (fx 365), hvis det er vigtigt.
* **Lektier** (`hwk`), der står på listen i mere end `DAYS` dage, kan blive
  sendt én gang til.
* **Sommerferien** er ca. 7 uger. Bruger skolen samme opslag eller album
  igen efter ferien, kræver det mere end 30 dage. 90 dage er et fornuftigt
  valg.

Derudover gælder:

* Intet slettes de første `DAYS` dage efter, at flaget er taget i brug -
  først da ved fskintra, hvad der er set, og hvad der ikke er. Det samme
  gælder efter en pause i kørslerne på mere end `DAYS` dage.
* Der ryddes kun op sidst i en kørsel, der er gennemført, og kun for de
  afsnit, der er med i kørslen (`--section`).
* Med `FSKINTRA_STORE_MESSAGES=full` slettes kopien af mailen sammen med
  markeringen.


Hvem?
=====

```fskintra``` er skrevet/opdateres af
[Jens Svalgaard Kohrt](http://svalgaard.net/jens/) - github AT svalgaard.net

Ændringer og forslag er bl.a. kommet fra
* [Aske Olsson](https://github.com/dvaske)
* [Jacob Kjeldahl](https://github.com/kjeldahl)
* [Michael Legart](https://github.com/legart)
* Kasper Lund
* [Lars Jakobsen](https://github.com/LaJako)
* [Jesper Rønn-Jensen](https://github.com/jesperronn)
* [Benny Simonsen](https://github.com/bennyslbs)

Bemærk at ```fskintra``` *ikke* er udviklet af itslearning (der laver selve ForældreIntra), men er et uofficielt program fra en tredjepart. Hvis du oplever fejl kan du indsende en fejlrapport på vores [Github side](https://github.com/svalgaard/fskintra/issues).
