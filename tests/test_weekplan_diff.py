# -*- coding: utf-8 -*-
import datetime

import pytest

from conftest import CHILD, WID, plan
from skoleintra import pgWeekplans, sdiff, semail, sstate, ssummary


def items(version):
    return pgWeekplans.extractItems(plan(version), WID)


def test_extract_items_dates_text_and_homework():
    its = items('c')
    assert [(i['date'], i['subject']) for i in its] == [
        ('2026-11-02', u'Matematik'),
        ('2026-11-02', u'Dansk'),
        ('2026-11-05', u'Dansk'),
        ('2026-11-06', u'Matematik'),
    ]
    assert its[1]['text'] == u'Dagens danskarbejde\nBibliotek'
    assert its[3]['homework'] is True
    assert its[3]['text'].startswith(u'Lektie: Aflever ugeopgave nr.2')
    assert not any(i['homework'] for i in its[:3])


@pytest.mark.parametrize('label,day,expected', [
    (u'Fredag, 6. nov. 2026', None, '2026-11-06'),
    (u'Onsdag, 4. november 2026', None, '2026-11-04'),
    (u'', u'Torsdag', '2026-11-05'),       # kun ugedag + ugenummer
    (u'Ukendt', None, None),
])
def test_day_date(label, day, expected):
    d = {'LongFormattedDate': label}
    if day:
        d['Day'] = day
    assert pgWeekplans._dayDate(d, WID) == expected


def test_day_date_prefers_iso_field():
    d = {'Date': '2026-11-03T00:00:00', 'LongFormattedDate': u'Fredag, 6. nov. 2026'}
    assert pgWeekplans._dayDate(d, WID) == '2026-11-03'


def test_diff_a_to_b_adds_two_danish_items():
    diff = sdiff.diffItems(items('a'), items('b'))
    assert not diff['first']
    assert [(i['date'], i['subject'], i['text'].split('\n')[-1])
            for i in diff['added']] == [
        ('2026-11-02', u'Dansk', u'Bibliotek'),
        ('2026-11-05', u'Dansk', u'Stavevejen'),
    ]
    assert diff['changed'] == [] and diff['removed'] == []


def test_diff_b_to_c_adds_math_note_only():
    diff = sdiff.diffItems(items('b'), items('c'))
    assert len(diff['added']) == 1
    assert diff['added'][0]['subject'] == u'Matematik'
    assert u'divisionsopgave' in diff['added'][0]['text']
    assert diff['changed'] == [] and diff['removed'] == []


def test_diff_changed_and_removed():
    old = items('c')
    new = [dict(i) for i in old[:3]]
    new[2]['text'] = u'Dagens danskarbejde\nStavevejen side 12'
    diff = sdiff.diffItems(old, new)
    assert diff['added'] == []
    assert [c['new']['text'] for c in diff['changed']] == [
        u'Dagens danskarbejde\nStavevejen side 12']
    assert [r['subject'] for r in diff['removed']] == [u'Matematik']


def test_diff_first_version():
    diff = sdiff.diffItems(None, items('a'))
    assert diff['first'] and len(diff['added']) == 1


def test_summary_html_does_not_change_md5():
    title, html = pgWeekplans.formatWeekplan(plan('c'))
    m1 = semail.Message(CHILD, 'pln', html)
    m1.setTitle(title)
    m1.setMessageID(WID)
    m2 = semail.Message(CHILD, 'pln', html)
    m2.setTitle(title)
    m2.setMessageID(WID)
    m2.setSummaryHtml(u'<div>Nyt siden sidst: noget helt andet</div>')
    m1.prepareMessage()
    m2.prepareMessage()
    assert m1.mp['md5'] == m2.mp['md5']


def test_change_box_rule_based():
    diff = sdiff.diffItems(items('b'), items('c'))
    box = ssummary.changeBox(diff)
    assert u'Nyt siden sidst' in box
    assert u'Tilføjet' in box and u'Man 2/11' in box
    assert u'divisionsopgave' in box


def test_change_box_first_version_highlights_homework():
    diff = sdiff.diffItems(None, items('b'))
    box = ssummary.changeBox(diff)
    assert u'Ny ugeplan' in box
    assert u'Fre 6/11' in box and u'Lektie' in box
    # Almindelig undervisning gentages ikke i boksen
    assert u'Stavevejen' not in box


def test_change_box_with_ai_and_escaping():
    diff = sdiff.diffItems(items('b'), items('c'))
    ai = {'resume': u'Kun en orientering <b>fra</b> matematik.',
          'kategorier': {'0': 'info'}, 'tekster': {}}
    box = ssummary.changeBox(diff, ai, 'claude-opus-5-5')
    assert u'Kun en orientering &lt;b&gt;fra&lt;/b&gt; matematik.' in box
    assert u'claude-opus-5-5' in box


def _send_recorder(monkeypatch):
    sent = []

    def fake_send(self):
        sent.append(self)
        self.store()
    monkeypatch.setattr(semail.Message, 'send', fake_send)
    return sent


def test_handle_weekplan_sequence(monkeypatch):
    sent = _send_recorder(monkeypatch)

    pgWeekplans.handleWeekplan(CHILD, WID, plan('a'))
    pgWeekplans.handleWeekplan(CHILD, WID, plan('a'))   # uændret: ingen mail
    pgWeekplans.handleWeekplan(CHILD, WID, plan('b'))
    pgWeekplans.handleWeekplan(CHILD, WID, plan('c'))

    assert len(sent) == 3
    assert u'Ny ugeplan' in sent[0].mp['summary_html']
    assert u'Bibliotek' in sent[1].mp['summary_html']
    assert u'divisionsopgave' in sent[2].mp['summary_html']
    assert u'Bibliotek' not in sent[2].mp['summary_html']

    # Boksen er med i selve mailen, men html (og dermed md5) er uberørt
    eml = sent[2].asEmail().as_string()
    assert 'Nyt siden sidst' in eml
    assert 'Nyt siden sidst' not in sent[2].mp['html']

    stored = sstate.getWeekplan(CHILD, WID)
    assert len(stored['items']) == 4
    (cname, change), = sstate.lastChanges()
    assert cname == CHILD and len(change['diff']['added']) == 1


def test_state_is_filled_even_when_not_sent(monkeypatch, options):
    sent = _send_recorder(monkeypatch)
    pgWeekplans.handleWeekplan(CHILD, WID, plan('b'))
    # Ny kørsel (fx efter deploy) hvor state er tabt men mailen allerede sendt
    sstate.reset()
    import os
    os.remove(os.path.join(options.statedir, 'state.json'))
    pgWeekplans.handleWeekplan(CHILD, WID, plan('b'))
    assert len(sent) == 1
    assert sstate.getWeekplan(CHILD, WID) is not None


def test_active_items_and_prune(monkeypatch):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    sstate.putWeekplan(CHILD, u'40-2026', u'Uge 40', items('a'), 'y')
    today = datetime.date(2026, 11, 3)
    active = sstate.activeItems(today)
    assert [(i['date'], i['subject']) for i in active] == [
        ('2026-11-05', u'Dansk'), ('2026-11-06', u'Matematik')]
    sstate.prune(today)
    assert sstate.getWeekplan(CHILD, u'40-2026') is None
    assert sstate.getWeekplan(CHILD, WID) is not None


def test_state_survives_reload():
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('a'), 'x')
    sstate.reset()
    assert sstate.getWeekplan(CHILD, WID)['md5'] == 'x'


@pytest.mark.parametrize('text,expected', [
    (u'Tur til Eksperimentariet - vi tager fra skolen ca kl. 8.30. '
     u'Husk madpakke + drikkedunk', 'tur'),
    (u'Halloween dag hele dagen.\nMødetid kl. 8.00-12.50.', 'tur'),
    (u'Mødetid er fra kl. 8.00-12.50.', 'ændret_tid'),
    (u'Lav gerne 1 opgave hjemme til torsdag.', 'lektie'),
    (u'Lektier\nLæsebogen side 46-47', 'lektie'),
    (u'Skrivløshæftet afleveres.', 'aflevering'),
    (u'Husk idrætstøj og håndklæde', 'medbring'),
    (u'I kontext har vi lavet side 65 færdig.', 'info'),
])
def test_rule_categories(text, expected):
    assert ssummary.ruleCategory({'text': text}) == expected


def test_subject_and_day_labels():
    assert ssummary.subjectLabel(u'(Uden angivelse af fag)') == u''
    assert ssummary.dayAndSubject(
        {'date': '2026-11-03', 'subject': u'(Uden angivelse af fag)'}) == \
        u'Tir 3/11'
    assert ssummary.dayAndSubject(
        {'date': None, 'label': u'Generelt', 'subject': u'Dansk',
         'week': u'44-2026'}) == u'Uge 44 · Dansk'
