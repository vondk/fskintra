# -*- coding: utf-8 -*-
'''Vedvarende tilstand til 'Nyt siden sidst' og skoleoverblikket.

Gemmes som JSON i <statedir>/state.json (fx ~/.skoleintra/aaskolen-state/).
Filen skrives atomisk (tmp-fil + os.replace), så et nedbrud midt i en
kørsel aldrig efterlader en halv fil.

Struktur:
  {
    "version": 1,
    "weekplans": {BARN: {UGE: {"title", "items", "md5", "updated"}}},
    "last_change": {BARN: {"when", "week", "title", "diff", "summary"}},
    "overview": {"input_hash", "ai", "generated"},
    "sync": {"todo": {NØGLE: {...}}, "calendar": {NØGLE: {...}}}
  }
'''

import datetime
import json
import os

from . import config

VERSION = 1
FILENAME = 'state.json'

_state = None


def _path():
    return os.path.join(config.options.statedir, FILENAME)


def _empty():
    return {'version': VERSION, 'weekplans': {}, 'last_change': {},
            'overview': {}, 'sync': {}, 'flags': {}}


def load():
    '''Indlæs (og cache) tilstanden. En manglende eller ødelagt fil giver en
    tom tilstand - det betyder blot at næste ændring vises som "ny ugeplan"'''
    global _state
    if _state is not None:
        return _state
    state = _empty()
    try:
        with open(_path(), encoding='utf-8') as fd:
            data = json.load(fd)
        if isinstance(data, dict) and data.get('version') == VERSION:
            for key in state:
                if key in data and isinstance(data[key], dict):
                    state[key] = data[key]
    except FileNotFoundError:
        pass
    except (ValueError, OSError) as e:
        config.log(u'ADVARSEL: kunne ikke læse %s (%s) - starter forfra' %
                   (_path(), e), 0)
    _state = state
    return _state


def save():
    if _state is None:
        return
    fn = _path()
    tmp = fn + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fd:
        json.dump(_state, fd, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, fn)


def reset():
    '''Glem den cachede tilstand (bruges af tests)'''
    global _state
    _state = None


def _now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def weekMonday(wid):
    '''Mandag i ugen wid ('45-2026') eller None hvis wid er ugyldig'''
    try:
        week, year = (int(x) for x in wid.split('-'))
        return datetime.date.fromisocalendar(year, week, 1)
    except (ValueError, AttributeError):
        return None


def getWeekplan(cname, wid):
    return load()['weekplans'].get(cname, {}).get(wid)


def putWeekplan(cname, wid, title, items, md5):
    plans = load()['weekplans'].setdefault(cname, {})
    old = plans.get(wid)
    if old and old.get('md5') == md5 and old.get('items') == items:
        return  # Intet nyt
    plans[wid] = {'title': title, 'items': items, 'md5': md5,
                  'updated': _now()}
    save()


def setLastChange(cname, wid, title, diff, summary):
    load()['last_change'][cname] = {
        'when': _now(), 'week': wid, 'title': title,
        'diff': diff, 'summary': summary}
    save()


def lastChanges():
    '''Liste af (barn, ændring) - nyeste først'''
    changes = load()['last_change'].items()
    return sorted(changes, key=lambda kv: kv[1].get('when', ''), reverse=True)


def prune(today, keepDays=14):
    '''Fjern ugeplaner hvis uge sluttede for mere end keepDays dage siden'''
    changed = False
    limit = today - datetime.timedelta(days=keepDays)
    for cname, plans in load()['weekplans'].items():
        for wid in list(plans):
            monday = weekMonday(wid)
            if monday and monday + datetime.timedelta(days=6) < limit:
                del plans[wid]
                changed = True
    if changed:
        save()


def activeItems(today):
    '''Alle punkter fra i dag og frem (plus 'Generelt' for indeværende og
    kommende uger), for alle børn. Hvert punkt får ekstra nøglerne child,
    week og weektitle. Sorteret efter barn, dato'''
    res = []
    iso = today.isoformat()
    for cname in sorted(load()['weekplans']):
        plans = load()['weekplans'][cname]
        for wid in sorted(plans, key=lambda w: weekMonday(w) or today):
            monday = weekMonday(wid)
            if monday and monday + datetime.timedelta(days=6) < today:
                continue  # Hele ugen er overstået
            for item in plans[wid].get('items', []):
                if item.get('date') and item['date'] < iso:
                    continue
                entry = dict(item)
                entry['child'] = cname
                entry['week'] = wid
                entry['weektitle'] = plans[wid].get('title', u'')
                res.append(entry)
    return res


def getOverviewCache():
    return load()['overview']


def setOverviewCache(inputHash, ai):
    load()['overview'] = {'input_hash': inputHash, 'ai': ai,
                          'generated': _now()}
    save()


def getSync(kind):
    '''Det fskintra selv har oprettet i Home Assistant ('todo' eller
    'calendar') - nøgle -> post. Ændringer gemmes med save()'''
    return load()['sync'].setdefault(kind, {})


def getFlag(name):
    return bool(load()['flags'].get(name))


def setFlag(name, value=True):
    load()['flags'][name] = bool(value)
    save()
