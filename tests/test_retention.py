# -*- coding: utf-8 -*-
'''Opbevaring: hvad fskintra gemmer, og hvornår det slettes igen'''
import datetime
import json
import os

from conftest import CHILD, WID, plan
from skoleintra import pgWeekplans, sdiff, soverview, sstate

DAY = datetime.date(2026, 11, 2)
OTHER = u'Bo 2A'


def items(version):
    return pgWeekplans.extractItems(plan(version), WID)


def setChange(cname, when, resume=u'Ny matematik mandag'):
    '''Gem en "seneste ændring" med et bestemt tidspunkt'''
    diff = sdiff.diffItems(items('b'), items('c'))
    sstate.setLastChange(cname, WID, u'Uge 45', diff, {'resume': resume})
    sstate.load()['last_change'][cname]['when'] = when
    sstate.save()


def onDisk(options):
    with open(os.path.join(options.statedir, sstate.FILENAME),
              encoding='utf-8') as fd:
        return json.load(fd)


#
# "Seneste ændring" (state.json: last_change)
#

def test_prune_removes_old_last_change(options):
    setChange(CHILD, '2026-10-18T08:00:00')     # 15 dage før DAY
    setChange(OTHER, '2026-10-19T23:59:59')     # 14 dage før DAY
    assert sstate.prune(DAY) is True

    assert [c for c, _ in sstate.lastChanges()] == [OTHER]
    # Også væk fra disken - ikke kun skjult
    assert list(onDisk(options)['last_change']) == [OTHER]
    assert sstate.prune(DAY) is False           # intet mere at fjerne


def test_prune_keep_days(options):
    setChange(CHILD, '2026-10-30T08:00:00')
    assert sstate.prune(DAY, keepDays=3) is False
    assert sstate.prune(DAY, keepDays=2) is True
    assert sstate.lastChanges() == []


def test_prune_removes_last_change_without_valid_time(options):
    setChange(CHILD, None)
    sstate.load()['last_change'][OTHER] = u'ødelagt'
    sstate.save()
    assert sstate.prune(DAY) is True
    assert onDisk(options)['last_change'] == {}


def test_prune_keeps_weekplans_of_the_child(options):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    setChange(CHILD, '2026-01-01T08:00:00')
    sstate.prune(DAY)
    assert sstate.getWeekplan(CHILD, WID)['items'] == items('c')
    assert sstate.children() == [CHILD]


def test_overview_does_not_show_pruned_last_change(options, tmp_path):
    '''Hverken sensorens "seneste_aendring" eller JSON-filen må vise en
    ændring, der er udløbet - heller ikke i den kørsel, hvor den udløber'''
    out = tmp_path / 'overblik.json'
    options.overviewjson = str(out)
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    sstate.putWeekplan(OTHER, WID, u'Uge 45', items('c'), 'x')
    setChange(CHILD, '2026-10-01T08:00:00', resume=u'Gammelt resumé')
    setChange(OTHER, '2026-11-01T08:00:00', resume=u'Nyt resumé')

    _, attrs = soverview.build(DAY)
    assert u'Bo 2A' in attrs['seneste_aendring']
    assert u'Nyt resumé' in attrs['seneste_aendring']
    assert CHILD not in attrs['seneste_aendring']
    assert u'Gammelt resumé' not in attrs['seneste_aendring']

    assert soverview.update(DAY) is True
    with open(out, encoding='utf-8') as fd:
        text = fd.read()
    assert [c['barn'] for c in json.loads(text)['seneste_aendring']] == [OTHER]
    assert u'Gammelt resumé' not in text
    # Barnet og dets aktuelle punkter er der stadig
    assert json.loads(text)['boern'] == sorted([CHILD, OTHER])


def test_overview_drops_last_change_when_it_expires(options, tmp_path):
    out = tmp_path / 'overblik.json'
    options.overviewjson = str(out)
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    setChange(CHILD, '2026-11-01T08:00:00')

    soverview.update(DAY)
    with open(out, encoding='utf-8') as fd:
        assert len(json.load(fd)['seneste_aendring']) == 1
    soverview.update(DAY + datetime.timedelta(days=30))
    with open(out, encoding='utf-8') as fd:
        assert json.load(fd)['seneste_aendring'] == []
