# -*- coding: utf-8 -*-
'''Skoleoverblik: samler alle aktuelle punkter fra ugeplanerne (alle børn)
og sender dem til Home Assistant som én sensor med markdown i attributterne
og/eller skriver dem som JSON til en fil (FSKINTRA_OVERVIEW_JSON).

Overblikket genereres kun med AI når indholdet (eller datoen) har ændret
sig. Det seneste resultat caches i state-filen og sendes til Home
Assistant ved hver kørsel, så sensoren genopstår efter en HA-genstart.
'''

import datetime
import hashlib
import json
import os

from . import config
from . import sai
from . import sdiff
from . import shass
from . import smqtt
from . import sstate
from . import ssummary
from . import ssync

# Formatet af JSON-filen. Tælles op ved ændringer, der ikke er
# bagudkompatible (nye nøgler er bagudkompatible)
EXPORT_VERSION = 1


def _inputHash(items, today):
    data = json.dumps({'today': today.isoformat(), 'items': items,
                       'model': sai.model() if sai.isEnabled() else None},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def build(today=None):
    '''Byg overblikket. Returnerer (state, attributes)'''
    return _build(today or datetime.date.today())[:2]


def _build(today):
    '''Byg overblikket. Returnerer (state, attributes, entries)'''
    sstate.prune(today)
    items = sstate.activeItems(today)

    cache = sstate.getOverviewCache()
    inputHash = _inputHash(items, today)
    stale = cache.get('input_hash') != inputHash
    # Sidste AI-forsøg fejlede (fx API nede) - prøv igen ved denne kørsel
    retry = (not stale and cache.get('ai') is None and sai.isEnabled() and
             bool(items))
    if stale or retry:
        sstate.setOverviewCache(inputHash, sai.buildOverview(items))
        cache = sstate.getOverviewCache()
    ai = cache.get('ai')

    entries = ssummary.overviewEntries(items, ai)
    headline = (ai or {}).get('overskrift') or ssummary.ruleHeadline(entries)
    markdown = ssummary.renderOverview(entries, today)
    generated = cache.get('generated') or u''
    markdown += u'\n\n_Opdateret %s%s_' % (
        ssummary.fmtTimestamp(generated),
        u' · AI-resumé' if ai else u'')

    attributes = {
        'friendly_name': u'Skoleoverblik',
        'icon': 'mdi:school',
        'markdown': markdown,
        'seneste_aendring': ssummary.renderLastChanges(sstate.lastChanges()),
        'punkter': [{
            'barn': e['child'],
            'dato': e.get('date'),
            'fag': e['subject'],
            'kategori': e['category'],
            'tekst': e['short'],
        } for e in entries if e['category'] != 'info'],
        'opdateret': generated,
        'kilde': u'ai' if ai else u'regler',
    }
    return headline, attributes, entries


def _publish(state, attributes):
    '''Send sensoren til Home Assistant - via MQTT hvis sat op (overlever
    genstart af HA), ellers via REST'''
    entity = config.options.haentity
    if not smqtt.isEnabled():
        return shass.pushState(entity, state, attributes)
    if shass.isEnabled() and not sstate.getFlag('mqtt_migrated'):
        # Engangsoprydning: en tilstand oprettet via REST med samme entity_id
        # ville ellers give MQTT-entiteten et andet id (..._2)
        if shass.deleteState(entity):
            sstate.setFlag('mqtt_migrated')
    return smqtt.publishOverview(entity, state, attributes)


#
# JSON-fil (FSKINTRA_OVERVIEW_JSON)
#

def exportPath():
    '''Filen overblikket skrives til som JSON, eller tom streng. En relativ
    sti regnes fra FSKINTRA_ROOT'''
    value = (getattr(config.options, 'overviewjson', u'') or u'').strip()
    return os.path.join(config.ROOT, value) if value else u''


def _exportChanges():
    '''Seneste ændring pr. barn (nyeste først)'''
    res = []
    for cname, ch in sstate.lastChanges():
        diff = ch.get('diff') or {}
        first = bool(diff.get('first'))
        rows = []
        if diff and not first:
            rows = [{'status': status.lower(), 'dato': item.get('date'),
                     'fag': ssummary.subjectLabel(item.get('subject')),
                     'tekst': item.get('text', u'')}
                    for status, item, _old in sdiff.changeEntries(diff)]
        res.append({
            'barn': cname,
            'tidspunkt': ch.get('when'),
            'uge': ch.get('week'),
            'titel': ch.get('title') or u'',
            'resume': (ch.get('summary') or {}).get('resume'),
            'ny_ugeplan': first,
            'aendringer': rows,
        })
    return res


def exportData(state, attributes, entries, today):
    '''Overblikket som JSON-venlig dict.

    Hvert punkt har et stabilt id (barn|dato|fag|n - det samme som
    to-do/kalender-synkroniseringen til Home Assistant bruger), så en
    modtager kan genkende punktet, selv om teksten rettes i ugeplanen.
    Punkter uden dato (fx "Generelt") har dato null'''
    return {
        'version': EXPORT_VERSION,
        'dato': today.isoformat(),
        'opdateret': attributes.get('opdateret') or u'',
        'kilde': attributes.get('kilde'),
        'overskrift': state,
        'boern': sstate.children(),
        'punkter': [{
            'id': key,
            'barn': e['child'],
            'dato': e.get('date'),
            'uge': e.get('week'),
            'fag': ssummary.subjectLabel(e.get('subject')),
            'kategori': e['category'],
            'kort': e['short'],
            'tekst': e.get('text', u''),
        } for key, e in ssync.keyed(entries)],
        'seneste_aendring': _exportChanges(),
    }


def writeExport(path, data):
    '''Skriv JSON-filen atomisk (tmp-fil + os.replace), så en læser aldrig
    ser en halv fil. Returnerer True ved succes - fejl logges kun'''
    tmp = path + '.tmp'
    try:
        dn = os.path.dirname(path)
        if dn:
            os.makedirs(dn, exist_ok=True)
        with open(tmp, 'w', encoding='utf-8') as fd:
            json.dump(data, fd, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError) as e:
        config.log(u'ADVARSEL: kunne ikke skrive skoleoverblik til %s: %r' %
                   (path, e), 0)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False
    config.log(u'Skoleoverblik skrevet til %s' % path, 2)
    return True


def update(today=None):
    '''Byg overblikket og send det til Home Assistant og/eller skriv det
    som JSON. Må aldrig fejle.
    today: kun til tests (standard er dags dato)'''
    ha = shass.isEnabled() or smqtt.isEnabled()
    path = exportPath()
    if not (ha or path):
        config.log(u'Hverken Home Assistant eller FSKINTRA_OVERVIEW_JSON er '
                   u'sat op - springer overblik over', 2)
        return False
    try:
        today = today or datetime.date.today()
        state, attributes, entries = _build(today)
        ok = True
        if path:
            ok = writeExport(path, exportData(state, attributes, entries,
                                              today))
        if ha:
            ok = _publish(state, attributes) and ok
            # Lektier -> to-do, ture -> kalender (kræver REST, uafhængigt
            # af hvordan sensoren sendes)
            ssync.sync(entries, today)
        return ok
    except Exception as e:  # Overblikket må aldrig vælte en kørsel
        config.log(u'ADVARSEL: kunne ikke bygge skoleoverblik: %r' % e, 0)
        return False
