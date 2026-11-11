# -*- coding: utf-8 -*-
'''--prune-markers / FSKINTRA_PRUNE_MARKERS_DAYS: oprydning i msg/'''
import json
import os
import time

import pytest

import fskintra
from skoleintra import (config, pgDialogue, pgFrontpage, pgHomework,
                        semail, snotifications, sretention)

DAY = 86400
CHILD = u'Alma 5C'
ALL = {'frp', 'msg', 'doc', 'pht', 'hwk', 'pln'}
PROFILE_ENV = {
    'FSKINTRA_LOGINTYPE': 'alm',
    'FSKINTRA_USERNAME': 'petjen',
    'FSKINTRA_PASSWORD': 'hemmelig',
    'FSKINTRA_HOSTNAME': 'aaskolen.m.skoleintra.dk',
    'FSKINTRA_RECIPIENT_EMAIL': 'foraelder@example.net',
    'FSKINTRA_SENDER_EMAIL': 'afsender@example.net',
}


@pytest.fixture
def opts(options):
    options.prunemarkersdays = 30
    options.catchup = True          # store() uden at sende
    options.storemessages = 'marker'
    return options


def marker(opts, tp, mid=None, text=u'indhold', date='2025-01-10'):
    '''Opret markeringen for en sendt besked. Returnerer kataloget'''
    msg = semail.Message(CHILD, tp, u'<p>%s</p>' % text)
    msg.setTitle(text)
    if mid:
        msg.setMessageID(*mid)
    msg.mp['date'] = date
    msg.store()
    dn = os.path.join(opts.msgdir, msg.getLongMessageID())
    assert os.path.isdir(dn)
    return dn


def age(path, days, now=None):
    t = (now or time.time()) - days * DAY
    os.utime(path, (t, t))


def tracked(opts, days=400):
    '''Lad som om "sidst set" har været noteret uafbrudt i days dage'''
    stamp = os.path.join(opts.msgdir, sretention.SEEN_STAMP)
    with open(stamp, 'w') as fd:
        fd.write('%r\n' % (time.time() - days * DAY))


def names(opts):
    return sorted(n for n in os.listdir(opts.msgdir) if not n.startswith('.'))


#
# "Sidst set" noteres af hasSentMessage
#

def test_lookup_marks_marker_as_seen(opts):
    dn = marker(opts, 'frp', ('17',))
    age(dn, 100)
    assert semail.hasSentMessage(tp='frp', mid='17') == [dn]
    assert time.time() - os.path.getmtime(dn) < 60


def test_lookup_does_not_touch_without_the_option(opts):
    '''Standard: fskintra ændrer intet ved eksisterende markeringer'''
    dn = marker(opts, 'frp', ('17',))
    age(dn, 100)
    opts.prunemarkersdays = None
    assert semail.hasSentMessage(tp='frp', mid='17') == [dn]
    del opts.prunemarkersdays
    assert semail.hasSentMessage(tp='frp', mid='17') == [dn]
    assert time.time() - os.path.getmtime(dn) > 99 * DAY


def test_has_been_sent_marks_as_seen(opts):
    dn = marker(opts, 'doc', ('abc',), text=u'Referat.pdf')
    age(dn, 100)
    again = semail.Message(CHILD, 'doc', u'<p>Referat.pdf</p>')
    again.setTitle(u'Referat.pdf')
    again.setMessageID('abc')
    assert again.maybeSend() is False
    assert time.time() - os.path.getmtime(dn) < 60


#
# pruneMarkers
#

def test_prunes_what_has_not_been_seen(opts):
    gone = marker(opts, 'frp', ('1',), text=u'fjernet opslag')
    kept = marker(opts, 'frp', ('2',), text=u'står der stadig')
    age(gone, 31)
    age(kept, 31)
    tracked(opts)
    semail.hasSentMessage(tp='frp', mid='2')    # stadig på forsiden
    assert sretention.pruneMarkers(30, ALL) == 1
    assert names(opts) == [os.path.basename(kept)]


def test_old_date_in_name_is_not_enough(opts):
    '''Et dokument fra 2019, der stadig ligger i klassens mappe, må ikke
    sendes igen - datoen i navnet siger intet om, hvorvidt det er væk'''
    dn = marker(opts, 'doc', ('abc',), date='2019-08-12')
    tracked(opts)
    for _run in range(3):
        semail.hasSentMessage(tp='doc', mid='abc')
        assert sretention.pruneMarkers(30, ALL) == 0
    assert os.path.isdir(dn)


def test_nothing_is_pruned_until_tracking_has_run_long_enough(opts):
    '''Første kørsel med flaget: alle gamle markeringer har en gammel
    mtime, men den siger endnu intet om "sidst set"'''
    dn = marker(opts, 'frp', ('1',))
    age(dn, 500)
    now = time.time()
    assert sretention.pruneMarkers(30, ALL, now) == 0
    assert sretention.pruneMarkers(30, ALL, now + 29 * DAY) == 0
    assert os.path.isdir(dn)
    assert sretention.pruneMarkers(30, ALL, now + 30 * DAY + 1) == 1


def test_tracking_starts_over_after_a_long_pause(opts):
    '''Har kørslerne (eller flaget) holdt pause længere end grænsen, er
    "sidst set" ikke blevet noteret i mellemtiden'''
    dn = marker(opts, 'frp', ('1',))
    now = time.time()
    sretention.pruneMarkers(30, ALL, now)
    sretention.pruneMarkers(30, ALL, now + 20 * DAY)
    # 45 dages pause
    assert sretention.pruneMarkers(30, ALL, now + 65 * DAY) == 0
    assert sretention.pruneMarkers(30, ALL, now + 90 * DAY) == 0
    assert os.path.isdir(dn)
    assert sretention.pruneMarkers(30, ALL, now + 96 * DAY) == 1


def test_only_types_of_sections_that_ran(opts):
    frp = marker(opts, 'frp', ('1',))
    pht = marker(opts, 'pht', ('album',))
    age(frp, 100)
    age(pht, 100)
    tracked(opts)
    assert sretention.pruneMarkers(30, {'frp', 'msg'}) == 1
    assert names(opts) == [os.path.basename(pht)]


def test_full_copies_are_removed_with_the_marker(opts):
    opts.storemessages = 'full'
    dn = marker(opts, 'frp', ('1',))
    assert any(fn.endswith('.eml') for fn in os.listdir(dn))
    age(dn, 31)
    tracked(opts)
    assert sretention.pruneMarkers(30, ALL) == 1
    assert names(opts) == []


def test_leaves_other_entries_alone(opts):
    for name in ('noter.txt', 'ikke-en-markering',
                 '2025-01-10--frp--' + 'a' * 32 + '--9.tmp'):
        path = os.path.join(opts.msgdir, name)
        os.mkdir(path)
        age(path, 400)
    tracked(opts)
    assert sretention.pruneMarkers(30, ALL) == 0
    assert len(names(opts)) == 3


def test_stamp_is_not_mistaken_for_a_marker(opts):
    marker(opts, 'frp', ('1',))
    sretention.pruneMarkers(30, ALL)
    assert os.path.isfile(os.path.join(opts.msgdir, sretention.SEEN_STAMP))
    assert len(semail.hasSentMessage()) == 1
    assert len(semail.hasSentMessage(tp='frp')) == 1


#
# Afsnittene noterer "sidst set" for det, de finder
#

def test_frontpage_item_still_listed_is_kept(opts, monkeypatch):
    html = (u'<div class="sk-news-item" data-feed-item-id="17">'
            u'<div class="sk-news-item-author"><span>Lærer</span>'
            u'<span class="sk-news-item-for">til</span> 5C</div>'
            u'<div class="sk-news-item-timestamp">2. jan. 2025 10:00</div>'
            u'<div class="sk-news-item-content"><p>Husk gymnastiktøj</p>'
            u'</div></div>')
    from skoleintra import sbs4
    monkeypatch.setattr(pgFrontpage, 'getMsgsForChild',
                        lambda cname: pgFrontpage.parseFrontpage(
                            cname, sbs4.beautify(html)))
    pgFrontpage.skoleFrontpage.run([CHILD])
    dn, = [os.path.join(opts.msgdir, n) for n in names(opts)]
    tracked(opts)

    age(dn, 200)                        # opslaget har hængt der længe
    pgFrontpage.skoleFrontpage.run([CHILD])
    assert sretention.pruneMarkers(30, ALL) == 0
    assert names(opts) == [os.path.basename(dn)]

    age(dn, 31)                         # ... og er nu fjernet af skolen
    assert sretention.pruneMarkers(30, ALL) == 1


def conversations(monkeypatch, convs):
    data = json.dumps({'Conversations': convs}) + ' ' * 100
    from skoleintra import sbs4
    bs = sbs4.beautify(u'<div class="sk-l-content-wrapper"><div></div></div>')
    bs.find('div', 'sk-l-content-wrapper').div['data-message'] = data
    return bs


def test_whole_thread_is_kept_while_the_thread_is_listed(opts, monkeypatch):
    '''Kommer der et nyt svar i en gammel tråd, hentes hele tråden. De
    ældre beskeders markeringer skal derfor leve lige så længe som tråden'''
    first = marker(opts, 'msg', ('T1', '100'), text=u'første')
    last = marker(opts, 'msg', ('T1', '105'), text=u'seneste')
    other = marker(opts, 'msg', ('T2', '50'), text=u'anden tråd')
    for dn in (first, last, other):
        age(dn, 100)
    tracked(opts)

    bs = conversations(monkeypatch, [{'ThreadId': 'T1',
                                      'LatestMessageId': 105}])
    assert pgDialogue.parseMessages(CHILD, bs) == []
    assert sretention.pruneMarkers(30, ALL) == 1
    assert names(opts) == sorted(os.path.basename(d) for d in (first, last))


def test_homework_lookup_of_all_markers_does_not_count_as_seen(opts):
    from skoleintra import sbs4
    dn = marker(opts, 'hwk', ('45-2026',))
    age(dn, 100)
    tracked(opts)
    bs = sbs4.beautify(u'<div class="sk-white-box"><b>x</b></div>')
    pgHomework.formatHomework(CHILD, bs)
    assert sretention.pruneMarkers(30, ALL) == 1


#
# Flag og miljøvariabel
#

@pytest.fixture
def env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith('FSKINTRA_'):
            monkeypatch.delenv(name)
    for k, v in PROFILE_ENV.items():
        monkeypatch.setenv(k, v)
    root = tmp_path / 'root'
    root.mkdir()
    monkeypatch.setattr(config, 'ROOT', str(root) + os.sep)
    return root


def test_off_by_default(env):
    config.parseArgs([])
    assert config.options.prunemarkersdays is None


def test_flag_and_env(env, monkeypatch):
    config.parseArgs(['--prune-markers', '90'])
    assert config.options.prunemarkersdays == 90
    monkeypatch.setenv('FSKINTRA_PRUNE_MARKERS_DAYS', '365')
    config.parseArgs([])
    assert config.options.prunemarkersdays == 365
    config.parseArgs(['--prune-markers', '30'])     # flaget vinder
    assert config.options.prunemarkersdays == 30


def test_minimum_is_locked():
    assert config.MIN_PRUNE_MARKERS_DAYS == 30


@pytest.mark.parametrize('value', ['0', '1', '14', '29', '-30', 'x'])
def test_value_below_minimum_is_refused(env, monkeypatch, capsys, value):
    with pytest.raises(SystemExit) as e:
        config.parseArgs(['--prune-markers=' + value])
    assert e.value.code == 2
    assert u'mindst 30' in capsys.readouterr().err

    monkeypatch.setenv('FSKINTRA_PRUNE_MARKERS_DAYS', value)
    with pytest.raises(SystemExit) as e:
        config.parseArgs([])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert 'FSKINTRA_PRUNE_MARKERS_DAYS' in err and u'mindst 30' in err


def old_marker(env):
    dn = env / 'msg' / ('2025-01-10--frp--' + 'a' * 32 + '--1')
    dn.mkdir(parents=True)
    age(str(dn), 100)
    stamp = env / 'msg' / sretention.SEEN_STAMP
    stamp.write_text('%r\n' % (time.time() - 400 * DAY))
    return dn


def run(monkeypatch, argv, full=True):
    '''En normal kørsel, hvor ingen afsnit finder noget'''
    monkeypatch.setattr(snotifications, 'checkForUpdates',
                        lambda: (full, (None, None)))
    monkeypatch.setattr(snotifications, 'saveState', lambda state: None)
    from skoleintra import schildren
    monkeypatch.setattr(schildren, 'getChildren', lambda: [])
    fskintra.main(argv)


def test_runs_at_the_end_of_a_normal_run(env, monkeypatch):
    dn = old_marker(env)
    run(monkeypatch, [])                    # uden flag: intet slettes
    assert dn.exists()
    run(monkeypatch, ['--prune-markers', '30'])
    assert not dn.exists()


def test_env_runs_at_the_end_of_a_normal_run(env, monkeypatch):
    dn = old_marker(env)
    monkeypatch.setenv('FSKINTRA_PRUNE_MARKERS_DAYS', '30')
    run(monkeypatch, [])
    assert not dn.exists()


def test_deselected_section_is_not_pruned(env, monkeypatch):
    dn = old_marker(env)
    run(monkeypatch, ['--prune-markers', '30', '--section', ',-frp'])
    assert dn.exists()


def test_not_pruned_when_the_run_does_not_complete(env, monkeypatch):
    dn = old_marker(env)
    run(monkeypatch, ['--prune-markers', '30'], full=False)
    assert dn.exists()

    def fail(cnames):
        raise SystemExit(config.EXIT_SITE_ERROR)
    monkeypatch.setattr(config.PAGE_SECTIONS[0], 'run', fail)
    with pytest.raises(SystemExit):
        run(monkeypatch, ['--prune-markers', '30'])
    assert dn.exists()
