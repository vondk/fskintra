# -*- coding: utf-8 -*-
'''Skoleoverblikket hentet fra en anden fskintra, fx fskintra-hosted, i
stedet for at bygge det selv (--overview-from-url).

Den anden installation henter fra ForældreIntra, kalder AI og skriver
overblikket som JSON (samme format som FSKINTRA_OVERVIEW_JSON). Her hentes
JSON'en via et hemmeligt link (FSKINTRA_OVERVIEW_URL) og sendes til Home
Assistant: sensoren (REST eller MQTT) og to-do-listen og kalenderen med den
sædvanlige synkronisering. Der hentes intet fra ForældreIntra, der sendes
ingen mails, og AI kaldes ikke - det er sket hos den anden.

Punkternes id er de nøgler, synkroniseringen bruger (ssync.keyed). Punkter,
der er oprettet af en tidligere kørsel med egen hentning, genkendes derfor:
afkrydsning bevares, og slettede punkter genoprettes ikke.

Indholdet kommer udefra og stammer fra skolen. Det hentes kun over https,
uden at følge omdirigeringer, med tids- og størrelsesgrænse, og hvert felt
tjekkes. Adressen indeholder et token og skrives aldrig i loggen.
'''

import datetime
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import config
from . import soverview
from . import sstate
from . import ssummary
from . import ssync

TIMEOUT = 30  # sekunder
MAX_BYTES = 512 * 1024
MAX_ITEMS = 500
MAX_CHILDREN = 12
MAX_CHANGES = 200   # rækker pr. barn under "seneste ændring"
MAX_ID = 300
MAX_NAME = 100
MAX_SHORT = 500
MAX_TEXT = 5000
MAX_TITLE = 300
MAX_SUMMARY = 3000
CATEGORIES = frozenset(ssummary.CATEGORY_LABELS)
CHANGE_STATUS = {u'tilføjet': 'added', u'ændret': 'changed',
                 u'fjernet': 'removed'}

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_WEEK_RE = re.compile(r'^\d{1,2}-\d{4}$')

# Svar fra fskintra-hosted, der har en forklaring
HTTP_HINTS = {
    404: u'linket virker ikke - er der lavet et nyt, eller er det slået fra?',
    429: u'for mange forsøg - prøv igen senere',
    503: u'der er intet overblik endnu - vent på første hentning',
}


class FeedError(Exception):
    pass


def host(url):
    '''Værtsnavnet til loggen - aldrig stien, hvor tokenet står'''
    try:
        return urllib.parse.urlsplit(url).hostname or u'?'
    except ValueError:
        return u'?'


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    '''En omdirigering kunne sende tokenet et andet sted hen'''

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url):
    '''Hent og parse overblikket. Kaster FeedError med en forklaring, der
    ikke indeholder adressen'''
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json', 'User-Agent': 'fskintra'})
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            raw = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        hint = HTTP_HINTS.get(e.code)
        if 300 <= e.code < 400:
            hint = u'omdirigering følges ikke - tjek adressen'
        suffix = u' - ' + hint if hint else u''
        raise FeedError(u'HTTP %d%s' % (e.code, suffix))
    except urllib.error.URLError as e:
        raise FeedError(u'ingen forbindelse (%s)' % (e.reason,))
    except (OSError, ValueError) as e:
        raise FeedError(u'ingen forbindelse (%s)' % type(e).__name__)
    if len(raw) > MAX_BYTES:
        raise FeedError(u'svaret er større end %d KB' % (MAX_BYTES // 1024))
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise FeedError(u'svaret er ikke gyldig JSON')
    if not isinstance(data, dict):
        raise FeedError(u'svaret er ikke et skoleoverblik')
    version = data.get('version')
    if version != soverview.EXPORT_VERSION:
        raise FeedError(u'ukendt version %s af overblikket - opdatér '
                        u'fskintra' % (version if isinstance(version, int)
                                       else u'?'))
    return data


def _text(value, limit):
    '''En streng på højst limit tegn - alt andet bliver til tom streng'''
    return value[:limit].strip() if isinstance(value, str) else u''


def _list(value):
    return value if isinstance(value, list) else []


def _date(value):
    '''ISO-dato som streng - eller None'''
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return None
    return value


def entries(data, today):
    '''Overblikkets punkter som de punkter, soverview og ssync bruger - fra
    i dag og frem. Filen kan være fra en tidligere dag (pause, fejlede
    hentninger), så fortiden sorteres fra igen. Ugyldige punkter springes
    over'''
    iso = today.isoformat()
    res = []
    seen = set()
    for p in _list(data.get('punkter'))[:MAX_ITEMS]:
        if not isinstance(p, dict):
            continue
        key = _text(p.get('id'), MAX_ID)
        child = _text(p.get('barn'), MAX_NAME)
        category = p.get('kategori')
        if not key or not child or category not in CATEGORIES or \
                key in seen:
            continue
        date = _date(p.get('dato'))
        if p.get('dato') is not None and date is None:
            continue
        week = p.get('uge')
        week = week if isinstance(week, str) and _WEEK_RE.match(week) \
            else u''
        if date and date < iso:
            continue
        monday = sstate.weekMonday(week) if week else None
        if not date and monday and monday + datetime.timedelta(days=6) < \
                today:
            continue  # Ugens generelle plan for en overstået uge
        text = _text(p.get('tekst'), MAX_TEXT)
        short = _text(p.get('kort'), MAX_SHORT) or ssummary.oneLine(text, 160)
        if not short:
            continue
        seen.add(key)
        res.append({
            'key': key,
            'child': child,
            'date': date,
            'week': week,
            'label': u'',
            'subject': _text(p.get('fag'), MAX_NAME),
            'category': category,
            'short': short,
            'text': text or short,
        })
    return res


def changes(data):
    '''"Seneste ændring" som liste af (barn, ændring) i samme form som
    sstate.lastChanges(), så den vises som ved egen hentning'''
    res = []
    for ch in _list(data.get('seneste_aendring'))[:MAX_CHILDREN]:
        if not isinstance(ch, dict):
            continue
        child = _text(ch.get('barn'), MAX_NAME)
        if not child:
            continue
        if ch.get('ny_ugeplan') is True:
            diff = {'first': True}
        else:
            diff = {'added': [], 'changed': [], 'removed': []}
            for row in _list(ch.get('aendringer'))[:MAX_CHANGES]:
                if not isinstance(row, dict):
                    continue
                kind = CHANGE_STATUS.get(row.get('status'))
                text = _text(row.get('tekst'), MAX_TEXT)
                if kind is None or not text:
                    continue
                item = {'date': _date(row.get('dato')),
                        'subject': _text(row.get('fag'), MAX_NAME),
                        'text': text}
                diff[kind].append({'new': item, 'old': None}
                                  if kind == 'changed' else item)
        summary = _text(ch.get('resume'), MAX_SUMMARY)
        res.append((child, {
            'when': _text(ch.get('tidspunkt'), 40),
            'title': _text(ch.get('titel'), MAX_TITLE),
            'summary': {'resume': summary} if summary else None,
            'diff': diff,
        }))
    return res


def update(url, today=None):
    '''Hent overblikket og send det til Home Assistant. Returnerer True ved
    succes. Kan overblikket ikke hentes, ændres intet i Home Assistant.
    today: kun til tests (standard er dags dato)'''
    today = today or datetime.date.today()
    where = host(url)
    try:
        data = fetch(url)
    except FeedError as e:
        config.log(u'FEJL: kunne ikke hente skoleoverblikket fra %s: %s. '
                   u'Home Assistant er ikke ændret' % (where, e), 0)
        return False
    try:
        rows = entries(data, today)
        attributes = soverview.sensorAttributes(
            rows, changes(data), _text(data.get('opdateret'), 40),
            data.get('kilde') == u'ai', today)
        ok = soverview._publish(ssummary.ruleHeadline(rows), attributes)
        # Lektier -> to-do, ture -> kalender (kræver REST)
        ssync.sync(rows, today)
    except Exception as e:  # Skal give en pæn fejl, ikke en traceback
        config.log(u'FEJL: kunne ikke sende skoleoverblikket fra %s til '
                   u'Home Assistant: %r' % (where, e), 0)
        return False
    config.log(u'Skoleoverblik hentet fra %s: %d punkter' %
               (where, len(rows)), 2)
    return ok
