# -*- coding: utf-8 -*-
'''Skoleoverblik: samler alle aktuelle punkter fra ugeplanerne (alle børn)
og sender dem til Home Assistant som én sensor med markdown i attributterne.

Overblikket genereres kun med AI når indholdet (eller datoen) har ændret
sig. Det seneste resultat caches i state-filen og sendes til Home
Assistant ved hver kørsel, så sensoren genopstår efter en HA-genstart.
'''

import datetime
import hashlib
import json

from . import config
from . import sai
from . import shass
from . import smqtt
from . import sstate
from . import ssummary
from . import ssync


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


def update(today=None):
    '''Byg overblikket og send det til Home Assistant. Må aldrig fejle.
    today: kun til tests (standard er dags dato)'''
    if not (shass.isEnabled() or smqtt.isEnabled()):
        config.log(u'Home Assistant er ikke sat op - springer overblik over',
                   2)
        return False
    try:
        today = today or datetime.date.today()
        state, attributes, entries = _build(today)
        ok = _publish(state, attributes)
        # Lektier -> to-do, ture -> kalender (kræver REST, uafhængigt af
        # hvordan sensoren sendes)
        ssync.sync(entries, today)
        return ok
    except Exception as e:  # Overblikket må aldrig vælte en kørsel
        config.log(u'ADVARSEL: kunne ikke bygge skoleoverblik: %r' % e, 0)
        return False
