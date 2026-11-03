# -*- coding: utf-8 -*-
import argparse
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skoleintra import config  # noqa: E402
from skoleintra import sstate  # noqa: E402

CHILD = u'Alma 5C'
WID = u'45-2026'

DANSK_HEAD = (u'<p><span style="color:#27ae60"><strong>Dagens danskarbejde'
              u'</strong></span></p>')
LEKTIE = (u'<p><strong><span style="color:#e74c3c">Lektie: Aflever '
          u'ugeopgave nr.2 - regnestykkerne på arket, der skal lægges '
          u'i mappen.</span></strong></p>')
MAT_MANDAG = (u'<p>Vi har arbejdet med en ny '
              u'divisionsopgave, som vi arbejder videre med.</p>')


def _lp(subject, content):
    return {'Subject': {'FormattedTitle': subject}, 'Content': content}


def _day(label, lessons):
    return {'LongFormattedDate': label, 'LessonPlans': lessons}


def plan(version):
    '''SelectedPlan-JSON i tre versioner af samme ugeplan:
    'a', 'b' og 'c' (tre versioner)'''
    mandag = []
    if version == 'c':
        mandag.append(_lp(u'Matematik', MAT_MANDAG))
    if version in ('b', 'c'):
        mandag.append(_lp(u'Dansk', DANSK_HEAD + u'<p>Bibliotek</p><p></p>'))
    torsdag = []
    if version in ('b', 'c'):
        torsdag.append(_lp(u'Dansk', DANSK_HEAD + u'<p>Stavevejen</p>'))
    return {
        'ClassOrGroup': u'4B',
        'FormattedWeek': WID,
        'GeneralPlan': {'LessonPlans': []},
        'DailyPlans': [
            _day(u'Mandag, 2. nov. 2026', mandag),
            _day(u'Tirsdag, 3. nov. 2026', []),
            _day(u'Onsdag, 4. nov. 2026', []),
            _day(u'Torsdag, 5. nov. 2026', torsdag),
            _day(u'Fredag, 6. nov. 2026', [_lp(u'Matematik', LEKTIE)]),
        ],
    }


@pytest.fixture(autouse=True)
def options(tmp_path, monkeypatch):
    ns = argparse.Namespace(
        verbosity=0,
        catchup=False,
        overviewonly=False,
        hostname='skole.m.skoleintra.dk',
        senderemail='afsender@example.net',
        email='modtager@example.net',
        anthropicapikey='',
        aimodel='claude-opus-5-5',
        haurl='',
        hatoken='',
        haentity='sensor.skoleintra_overblik',
        haverifyssl='true',
        mqtthost='',
        mqttport='1883',
        mqttuser='',
        mqttpassword='',
    )
    for name in ('cache', 'msg', 'state'):
        dn = tmp_path / name
        dn.mkdir()
        setattr(ns, name + 'dir', str(dn))
    monkeypatch.setattr(config, 'options', ns)
    sstate.reset()
    yield ns
    sstate.reset()
