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
from . import sstate
from . import ssummary


def _inputHash(items, today):
    data = json.dumps({'today': today.isoformat(), 'items': items,
                       'model': sai.model() if sai.isEnabled() else None},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def build(today=None):
    '''Byg overblikket. Returnerer (state, attributes)'''
    today = today or datetime.date.today()
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
    return headline, attributes


def update():
    '''Byg overblikket og send det til Home Assistant. Må aldrig fejle'''
    if not shass.isEnabled():
        config.log(u'Home Assistant er ikke sat op - springer overblik over',
                   2)
        return False
    try:
        state, attributes = build()
        return shass.pushState(config.options.haentity, state, attributes)
    except Exception as e:  # Overblikket må aldrig vælte en kørsel
        config.log(u'ADVARSEL: kunne ikke bygge skoleoverblik: %r' % e, 0)
        return False
