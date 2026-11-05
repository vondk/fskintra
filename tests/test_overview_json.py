# -*- coding: utf-8 -*-
'''Skoleoverblikket som JSON-fil (FSKINTRA_OVERVIEW_JSON)'''
import datetime
import json
import os

import pytest

from conftest import CHILD, WID, plan
from skoleintra import (config, pgWeekplans, sdiff, soverview, sstate,
                        ssync)

DAY = datetime.date(2026, 11, 2)
LEKTIE_ID = u'Alma 5C|2026-11-06|Matematik|0'


def items(version):
    return pgWeekplans.extractItems(plan(version), WID)


@pytest.fixture
def out(options, tmp_path):
    path = tmp_path / 'tenant' / 'overblik.json'
    options.overviewjson = str(path)
    return path


def read(path):
    with open(path, encoding='utf-8') as fd:
        return json.load(fd)


def test_update_writes_json_without_home_assistant(out):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    assert soverview.update(DAY) is True

    data = read(out)
    assert data['version'] == soverview.EXPORT_VERSION
    assert data['dato'] == u'2026-11-02'
    assert data['kilde'] == u'regler'
    assert data['overskrift'] == u'1 lektie'
    assert data['boern'] == [CHILD]
    assert data['opdateret']
    assert not os.path.exists(str(out) + '.tmp')

    ids = [p['id'] for p in data['punkter']]
    assert len(ids) == len(set(ids))
    lektie, = [p for p in data['punkter'] if p['kategori'] == 'lektie']
    assert lektie['id'] == LEKTIE_ID
    assert (lektie['barn'], lektie['dato'], lektie['uge'], lektie['fag']) \
        == (CHILD, u'2026-11-06', WID, u'Matematik')
    assert lektie['tekst'].startswith(u'Lektie: Aflever ugeopgave nr.2')
    assert lektie['kort'] == lektie['tekst']  # uden AI: hele teksten
    # Almindelig undervisning kommer også med (kategori info)
    assert any(p['kategori'] == 'info' and u'Stavevejen' in p['tekst']
               for p in data['punkter'])


def test_ids_are_the_same_as_home_assistant_sync_keys(out):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    soverview.update(DAY)
    _, _, entries = soverview._build(DAY)
    want = ssync.wanted(entries, DAY, ssync.TODO_CATEGORIES)
    assert set(want) == {LEKTIE_ID}
    assert LEKTIE_ID in [p['id'] for p in read(out)['punkter']]


def test_id_is_stable_when_the_text_changes(out):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    soverview.update(DAY)
    changed = items('c')
    for it in changed:
        if it['homework']:
            it['text'] = u'Lektie: Aflever ugeopgave nr.3'
    sstate.putWeekplan(CHILD, WID, u'Uge 45', changed, 'y')
    soverview.update(DAY)

    lektie, = [p for p in read(out)['punkter'] if p['kategori'] == 'lektie']
    assert lektie['id'] == LEKTIE_ID
    assert lektie['tekst'] == u'Lektie: Aflever ugeopgave nr.3'


def test_past_items_are_left_out(out):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    soverview.update(datetime.date(2026, 11, 7))
    data = read(out)
    assert data['punkter'] == []
    assert data['boern'] == [CHILD]  # barnet kendes stadig


def test_last_change_is_exported(out):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    diff = sdiff.diffItems(items('b'), items('c'))
    sstate.setLastChange(CHILD, WID, u'Uge 45', diff,
                         {'resume': u'Ny matematik mandag'})
    soverview.update(DAY)

    change, = read(out)['seneste_aendring']
    assert (change['barn'], change['uge'], change['titel']) == (
        CHILD, WID, u'Uge 45')
    assert change['resume'] == u'Ny matematik mandag'
    assert change['ny_ugeplan'] is False
    assert change['tidspunkt']
    assert change['aendringer'] == [{
        'status': u'tilføjet', 'dato': u'2026-11-02', 'fag': u'Matematik',
        'tekst': u'Vi har arbejdet med en ny divisionsopgave, som vi '
                 u'arbejder videre med.'}]


def test_first_weekplan_lists_no_changes(out):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('a'), 'x')
    sstate.setLastChange(CHILD, WID, u'Uge 45',
                         sdiff.diffItems(None, items('a')), None)
    soverview.update(DAY)
    change, = read(out)['seneste_aendring']
    assert change['ny_ugeplan'] is True
    assert change['aendringer'] == [] and change['resume'] is None


def test_relative_path_is_under_fskintra_root(options, monkeypatch,
                                              tmp_path):
    monkeypatch.setattr(config, 'ROOT', str(tmp_path) + os.sep)
    options.overviewjson = u'overblik.json'
    assert soverview.exportPath() == str(tmp_path / 'overblik.json')
    options.overviewjson = u'  '
    assert soverview.exportPath() == u''


def test_write_error_is_logged_not_raised(options, tmp_path, capsys):
    blocker = tmp_path / 'fil'
    blocker.write_text(u'x')
    options.overviewjson = str(blocker / 'overblik.json')
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    assert soverview.update(DAY) is False
    assert u'kunne ikke skrive skoleoverblik' in capsys.readouterr().err


def test_json_and_home_assistant_together(out, options, monkeypatch):
    options.haurl, options.hatoken = 'http://ha.local:8123', 't'
    published, synced = [], []
    monkeypatch.setattr(soverview, '_publish',
                        lambda state, attrs: published.append(state) or True)
    monkeypatch.setattr(ssync, 'sync',
                        lambda entries, today: synced.append(today))
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')

    assert soverview.update(DAY) is True
    assert published == [u'1 lektie'] and synced == [DAY]
    assert read(out)['overskrift'] == u'1 lektie'


def test_env_variable_is_read(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith('FSKINTRA_'):
            monkeypatch.delenv(name)
    root = tmp_path / 'root'
    root.mkdir()
    monkeypatch.setattr(config, 'ROOT', str(root) + os.sep)
    for k, v in (('LOGINTYPE', 'alm'), ('USERNAME', 'petjen'),
                 ('PASSWORD', 'x'), ('HOSTNAME', 'a.m.skoleintra.dk'),
                 ('RECIPIENT_EMAIL', 'a@example.net'),
                 ('SENDER_EMAIL', 'b@example.net'),
                 ('OVERVIEW_JSON', '/data/t1/overblik.json')):
        monkeypatch.setenv('FSKINTRA_' + k, v)
    config.parseArgs(['--config-file', str(tmp_path / 'findes-ikke.txt')])
    assert config.options.overviewjson == u'/data/t1/overblik.json'
