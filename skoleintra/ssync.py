# -*- coding: utf-8 -*-
'''Synkronisering af ugeplanernes punkter til Home Assistant:

* Lektier, afleveringer og ting der skal med -> to-do-liste
  (FSKINTRA_HA_TODO, standard todo.lektier), så de kan krydses af.
* Ture, særlige dage og ændrede mødetider -> kalender
  (FSKINTRA_HA_CALENDAR, standard calendar.skole) som heldagsbegivenheder.

fskintra husker selv (i state-filen) hvad det har oprettet, og rører kun
det. Principper:
* Punkter du har krydset af, ændres aldrig.
* Punkter du selv har slettet, genoprettes ikke.
* Forsvinder et kommende punkt fra ugeplanen, fjernes det igen (to-do: kun
  hvis det ikke er krydset af).
* Afkrydsede to-do-punkter fjernes når forfaldsdatoen er passeret.
  Fortidige kalenderbegivenheder bevares som historik.
* En fejl i ét kald logges, og punktet prøves igen ved næste kørsel.
'''

import datetime

from . import config
from . import shass
from . import sstate
from . import ssummary

TODO_CATEGORIES = ('lektie', 'aflevering', 'medbring')
CALENDAR_CATEGORIES = ('tur', 'ændret_tid')
MAX_SUMMARY = 80  # fuld tekst står i beskrivelsen


def _entity(option):
    value = getattr(config.options, option, u'') or u''
    return u'' if value == u'off' else value


def isEnabled():
    return shass.isEnabled() and bool(_entity('hatodo') or
                                      _entity('hacalendar'))


def keyed(entries):
    '''Liste af (nøgle, punkt). Nøglen (barn|dato|fag|n) er stabil når
    teksten ændres, så punktet opdateres i stedet for at blive oprettet
    igen. n tæller op hvis samme fag optræder flere gange samme dag'''
    seen = {}
    res = []
    for e in entries:
        base = (e['child'], e.get('date') or u'', e['subject'])
        n = seen.get(base, 0)
        seen[base] = n + 1
        res.append((u'%s|%s|%s|%d' % (base + (n,)), e))
    return res


def wanted(entries, today, categories):
    '''Ønskede punkter: rette kategori og dato fra i dag og frem'''
    iso = today.isoformat()
    return dict((key, e) for key, e in keyed(entries)
                if e['category'] in categories and e.get('date') and
                e['date'] >= iso)


def _who(e):
    return e['child'].split()[0]


def summary(e):
    '''Fx "Hugo · Dansk: Læsebogen side 46-47" eller "Hugo: Tur til ..."'''
    text = e['short']
    if e['category'] == 'medbring' and not text.lower().startswith(u'husk'):
        text = u'Husk: ' + text
    subject = ssummary.subjectLabel(e['subject'])
    if subject:
        s = u'%s · %s: %s' % (_who(e), subject, text)
    else:
        s = u'%s: %s' % (_who(e), text)
    return ssummary.oneLine(s, MAX_SUMMARY)


def description(e):
    week = (e.get('week') or u'').split('-')[0]
    return u'%s\n\n%s · ugeplan uge %s (fskintra)' % (
        e['text'], e['child'], week)


def _call(what, domain, service, data, returnResponse=False):
    try:
        return True, shass.callService(domain, service, data, returnResponse)
    except Exception as e:  # Synk må aldrig vælte en kørsel
        config.log(u'ADVARSEL: Home Assistant %s.%s fejlede (%s): %r' %
                   (domain, service, what, e), 0)
        return False, None


def _exists(entity):
    try:
        if shass.entityExists(entity):
            return True
        config.log(u'Home Assistant: %s findes ikke - springer over' %
                   entity, 1)
    except Exception as e:
        config.log(u'ADVARSEL: kunne ikke tjekke %s i Home Assistant: %r' %
                   (entity, e), 0)
    return False


#
# To-do
#

def _todoItems(entity):
    ok, resp = _call(u'hent', 'todo', 'get_items',
                     {'entity_id': entity,
                      'status': ['needs_action', 'completed']}, True)
    if not ok:
        return None
    items = ((resp or {}).get(entity) or {}).get('items') or []
    return dict((it['uid'], it) for it in items if it.get('uid'))


def syncTodo(entity, want, today):
    '''Synkronisér ønskede punkter til to-do-listen. Returnerer antal
    ændringer (tilføjet, rettet, fjernet)'''
    synced = sstate.getSync('todo')
    items = _todoItems(entity)
    if items is None:
        return 0
    iso = today.isoformat()
    changes = 0

    for key, rec in list(synced.items()):
        if rec.get('deleted'):
            # Slettet af brugeren - glem det når datoen er passeret
            if key not in want and rec.get('due', u'') < iso:
                del synced[key]
            continue
        item = items.get(rec.get('uid'))
        if item is None:
            rec['deleted'] = True  # Slettet af brugeren: genopret ikke
            continue
        done = item.get('status') == 'completed'
        if key in want:
            if done:
                continue
            e = want[key]
            new = {'summary': summary(e), 'due': e['date'],
                   'description': description(e)}
            if any(rec.get(k) != v for k, v in new.items()):
                ok, _ = _call(new['summary'], 'todo', 'update_item', {
                    'entity_id': entity, 'item': rec['uid'],
                    'rename': new['summary'], 'due_date': new['due'],
                    'description': new['description']})
                if ok:
                    rec.update(new)
                    changes += 1
        elif rec.get('due', u'') < iso:
            # Forfaldent: ryd op i afkrydsede, lad de andre stå
            if done:
                ok, _ = _call(rec.get('summary'), 'todo', 'remove_item',
                              {'entity_id': entity, 'item': rec['uid']})
                if ok:
                    del synced[key]
                    changes += 1
        elif done:
            del synced[key]  # Ikke længere i ugeplanen, men krydset af
        else:
            # Kommende punkt er forsvundet fra ugeplanen
            ok, _ = _call(rec.get('summary'), 'todo', 'remove_item',
                          {'entity_id': entity, 'item': rec['uid']})
            if ok:
                del synced[key]
                changes += 1

    added = []
    for key, e in want.items():
        if key in synced:
            continue
        rec = {'summary': summary(e), 'due': e['date'],
               'description': description(e)}
        ok, _ = _call(rec['summary'], 'todo', 'add_item', {
            'entity_id': entity, 'item': rec['summary'],
            'due_date': rec['due'], 'description': rec['description']})
        if ok:
            added.append((key, rec))
            changes += 1

    if added:
        # add_item returnerer ikke uid - find de nye punkter
        items = _todoItems(entity) or {}
        known = set(r.get('uid') for r in synced.values())
        for key, rec in added:
            for uid, it in items.items():
                if (uid not in known and it.get('summary') == rec['summary']
                        and it.get('due') == rec['due']):
                    rec['uid'] = uid
                    known.add(uid)
                    synced[key] = rec
                    break
            else:
                config.log(u'ADVARSEL: kunne ikke finde nyt to-do-punkt %r' %
                           rec['summary'], 0)
    return changes


#
# Kalender
#

def _window(iso):
    d = datetime.date.fromisoformat(iso)
    nxt = d + datetime.timedelta(days=1)
    return {'start_date_time': u'%s 00:00:00' % d.isoformat(),
            'end_date_time': u'%s 00:00:00' % nxt.isoformat()}


def syncCalendar(entity, want, today):
    '''Synkronisér ønskede punkter til kalenderen som heldagsbegivenheder.
    Begivenheder findes igen via titel og dato (HA giver ingen uid)'''
    synced = sstate.getSync('calendar')
    iso = today.isoformat()
    changes = 0

    for key, rec in list(synced.items()):
        if key in want:
            e = want[key]
            new = {'summary': summary(e), 'date': e['date'],
                   'description': description(e)}
            if any(rec.get(k) != v for k, v in new.items()):
                data = {'entity_id': entity, 'summary': rec['summary'],
                        'new_summary': new['summary'],
                        'description': new['description']}
                data.update(_window(rec['date']))
                ok, _ = _call(new['summary'], 'calendar', 'update_event',
                              data)
                if ok:
                    rec.update(new)
                    changes += 1
        elif rec.get('date', u'') < iso:
            del synced[key]  # Fortidig: bevares i kalenderen som historik
        else:
            data = {'entity_id': entity, 'summary': rec['summary']}
            data.update(_window(rec['date']))
            ok, _ = _call(rec['summary'], 'calendar', 'delete_event', data)
            if ok:
                del synced[key]
                changes += 1

    for key, e in want.items():
        if key in synced:
            continue
        rec = {'summary': summary(e), 'date': e['date'],
               'description': description(e)}
        end = (datetime.date.fromisoformat(e['date']) +
               datetime.timedelta(days=1)).isoformat()
        ok, _ = _call(rec['summary'], 'calendar', 'create_event', {
            'entity_id': entity, 'summary': rec['summary'],
            'description': rec['description'],
            'start_date': rec['date'], 'end_date': end})
        if ok:
            synced[key] = rec
            changes += 1
    return changes


def sync(entries, today=None):
    '''Synkronisér overblikkets punkter til to-do og kalender. Må aldrig
    fejle'''
    if not isEnabled():
        return
    today = today or datetime.date.today()
    try:
        for option, kind, cats, func in (
                ('hatodo', 'todo', TODO_CATEGORIES, syncTodo),
                ('hacalendar', 'calendar', CALENDAR_CATEGORIES,
                 syncCalendar)):
            entity = _entity(option)
            if not entity or not _exists(entity):
                continue
            n = func(entity, wanted(entries, today, cats), today)
            config.log(u'Home Assistant: %s synkroniseret (%d ændringer)' %
                       (entity, n), 2)
    except Exception as e:
        config.log(u'ADVARSEL: synkronisering til Home Assistant '
                   u'fejlede: %r' % e, 0)
    finally:
        sstate.save()
