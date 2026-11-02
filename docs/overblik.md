# "Nyt siden sidst" og skoleoverblik i Home Assistant

fskintra sender en ugeplan igen, hver gang skolen retter i den. For at du ikke
selv skal finde forskellen, får hver ugeplan-mail nu en boks øverst:

* **Nyt siden sidst**: præcis hvilke punkter der er tilføjet, ændret eller
  fjernet siden sidste mail, fx *Tilføjet · Man 2/11 · Matematik: ...*
* **Ny ugeplan**: første gang en uges plan dukker op, fremhæves kun det, der
  kræver handling (lektier, afleveringer, ture, ting der skal med).

Derudover kan fskintra samle alt aktuelt for alle børn, fra i dag og frem, i
én sensor i Home Assistant, der vises som et markdown-kort.

Begge dele virker uden AI. Med en API-nøgle til Claude får boksen et kort
resumé, og overblikket får en overskrift og kortere tekster.

## Opsætning

Alt styres med miljøvariabler (se også `fskintra.env.example`):

| Variabel | Standard | Betydning |
|---|---|---|
| `FSKINTRA_ANTHROPIC_API_KEY` | (tom) | API-nøgle fra console.anthropic.com. Tom = ingen AI |
| `FSKINTRA_AI_MODEL` | `claude-opus-5-5` | Claude-model, fx `claude-haiku-5-5` for lav pris |
| `FSKINTRA_HA_URL` | (tom) | Fx `http://homeassistant.local:8123`. Tom = intet overblik |
| `FSKINTRA_HA_TOKEN` | (tom) | Long-lived access token (Profil → Sikkerhed i Home Assistant) |
| `FSKINTRA_HA_ENTITY` | `sensor.skoleintra_overblik` | Sensoren der opdateres |
| `FSKINTRA_HA_VERIFY_SSL` | `true` | `false` ved selvsigneret certifikat på det lokale net |

### API-nøgle til Claude

Et Claude.ai-abonnement giver ikke API-adgang; API'et afregnes separat og
forudbetalt:

1. Opret en konto på [console.anthropic.com](https://console.anthropic.com),
   indsæt fx 5 USD under *Billing*.
2. Opret gerne et separat *workspace* "fskintra" med en lav månedlig
   *spend limit*, så en lækket nøgle højst kan koste det beløb.
3. Opret en API-nøgle og sæt den som `FSKINTRA_ANTHROPIC_API_KEY`.

AI kaldes kun når der faktisk er nyt: én gang pr. ændret ugeplan og én gang
når overblikket ændrer sig (eller ved datoskift). Ugeplanernes tekst sendes
til Anthropics API. Fejler AI-kaldet (fx ingen forbindelse), sendes mailen
stadig, blot uden resumé.

### Home Assistant

Sensoren oprettes via Home Assistants REST API, og den opdateres ved **hver**
kørsel (også når intet er ændret), så den genopstår efter en genstart af Home
Assistant. Sensoren har disse attributter:

* `markdown`: overblikket, et afsnit pr. barn
* `seneste_aendring`: seneste ændring pr. barn
* `punkter`: liste over lektier, ture m.m. (til egne automationer)
* `opdateret`, `kilde` (`ai` eller `regler`)

Markdown-kort til et dashboard:

```yaml
type: vertical-stack
cards:
  - type: markdown
    title: Skole
    content: "{{ state_attr('sensor.skoleintra_overblik', 'markdown') }}"
  - type: markdown
    title: Seneste ændring
    content: "{{ state_attr('sensor.skoleintra_overblik', 'seneste_aendring') }}"
```

Overblikket er ikke historik værd, så udelad det gerne fra recorderen:

```yaml
recorder:
  exclude:
    entities:
      - sensor.skoleintra_overblik
```

## Test

```bash
# Genbyg og send kun overblikket ud fra tidligere hentede ugeplaner
python fskintra.py --overview-only -v
```

Tilstanden (seneste version af hver ugeplan, seneste ændring og det cachede
overblik) gemmes i `~/.skoleintra/<præfix>-state/state.json`. Slettes filen,
vises næste ændring blot som "Ny ugeplan".

Unit-tests:

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```
