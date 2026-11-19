# -*- coding: utf-8 -*-
'''--overview-from-url: skoleoverblikket fra en anden fskintra (fx
fskintra-hosted) til Home Assistant'''
import datetime
import http.server
import json
import os
import threading

import pytest

import fskintra
from conftest import CHILD, WID, plan
from skoleintra import (config, pgWeekplans, sdiff, soverview, sremote,
                        sstate, ssync)
from test_sync_and_threads import ha, writes  # noqa: F401 - fixture

DAY = datetime.date(2026, 11, 2)
LEKTIE_ID = u'Alma 5C|2026-11-06|Matematik|0'
TOKEN = u'hemmeligt-token-1234567890abcdefghijklmnopqrstu'


def items(version):
    return pgWeekplans.extractItems(plan(version), WID)


def exported(today=DAY, version='c', change=True):
    '''Overblikket, som den anden fskintra skriver det
    (FSKINTRA_OVERVIEW_JSON)'''
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items(version), 'x')
    if change:
        sstate.setLastChange(CHILD, WID, u'Uge 45',
                             sdiff.diffItems(items('b'), items(version)),
                             {'resume': u'Ny matematik mandag'})
    state, attributes, entries = soverview._build(today)
    return soverview.exportData(state, attributes, entries, today)


def point(**kw):
    p = {'id': u'Alma 5C|2026-11-06|Matematik|0', 'barn': CHILD,
         'dato': u'2026-11-06', 'uge': WID, 'fag': u'Matematik',
         'kategori': u'lektie', 'kort': u'Aflever opgave',
         'tekst': u'Lektie: Aflever opgave'}
    p.update(kw)
    return p


def feed(*points, **kw):
    data = {'version': 1, 'dato': u'2026-11-02', 'kilde': u'regler',
            'opdateret': u'2026-11-02T16:35:12', 'overskrift': u'x',
            'boern': [CHILD], 'punkter': list(points),
            'seneste_aendring': []}
    data.update(kw)
    return data


@pytest.fixture
def captured(options, monkeypatch):
    '''Sensoren, som den ville blive sendt til Home Assistant'''
    options.haurl, options.hatoken = 'http://ha.local:8123', 't'
    options.hatodo = options.hacalendar = 'off'
    sent = []
    monkeypatch.setattr(soverview, '_publish',
                        lambda state, attrs: sent.append((state, attrs)) or
                        True)
    return sent


def serve(monkeypatch, data):
    monkeypatch.setattr(sremote, 'fetch', lambda url: data)


#
# Samme sensor og samme synkronisering som ved egen hentning
#

def test_sensor_is_the_same_as_when_fskintra_fetches_itself(captured,
                                                            monkeypatch):
    data = exported()
    _, local, _ = soverview._build(DAY)
    sstate.reset()  # Den lokale har ingen ugeplaner - kun overblikket
    serve(monkeypatch, json.loads(json.dumps(data)))

    assert sremote.update(u'https://hosted.example/x.json', DAY) is True
    (state, attributes), = captured
    assert state == u'1 lektie'
    assert attributes == local
    assert u'Ny matematik mandag' in attributes['seneste_aendring']
    assert u'Tilføjet' in attributes['seneste_aendring']


def test_first_weekplan_is_shown_as_new(captured, monkeypatch):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('a'), 'x')
    sstate.setLastChange(CHILD, WID, u'Uge 45',
                         sdiff.diffItems(None, items('a')), None)
    state, attributes, entries = soverview._build(DAY)
    data = soverview.exportData(state, attributes, entries, DAY)
    sstate.reset()
    serve(monkeypatch, data)

    sremote.update(u'https://hosted.example/x.json', DAY)
    (_, remote), = captured
    assert remote['seneste_aendring'] == attributes['seneste_aendring']
    assert u'Ny ugeplan' in remote['seneste_aendring']


def test_ai_source_is_shown(captured, monkeypatch):
    serve(monkeypatch, feed(point(), kilde=u'ai'))
    sremote.update(u'https://hosted.example/x.json', DAY)
    (_, attributes), = captured
    assert attributes['kilde'] == u'ai'
    assert u'AI-resumé' in attributes['markdown']


def test_items_created_by_own_fetching_are_recognised(
        ha, monkeypatch):  # noqa: F811
    # Først hentede fskintra selv og oprettede to-do og kalender ...
    data = exported(change=False)
    _, _, entries = soverview._build(DAY)
    ssync.sync(entries, DAY)
    assert len(ha.todo) == 1
    ha.todo[0]['status'] = 'completed'   # krydset af
    ha.calls[:] = []

    # ... så kommer overblikket fra den anden fskintra (med AI-tekst)
    monkeypatch.setattr(soverview, '_publish', lambda s, a: True)
    for p in data['punkter']:
        if p['id'] == LEKTIE_ID:
            p['kort'] = u'Aflever ugeopgave nr. 2'
    serve(monkeypatch, data)
    assert sremote.update(u'https://hosted.example/x.json', DAY) is True
    # Intet oprettet igen, og det afkrydsede punkt er ikke rørt
    assert writes(ha) == []
    assert len(ha.todo) == 1 and ha.todo[0]['status'] == 'completed'


def test_new_items_are_synced_with_the_given_id(
        ha, monkeypatch):  # noqa: F811
    monkeypatch.setattr(soverview, '_publish', lambda s, a: True)
    serve(monkeypatch, feed(
        point(),
        point(id=u'Alma 5C|2026-11-03||0', dato=u'2026-11-03', fag=u'',
              kategori=u'tur', kort=u'Tur til Zoo', tekst=u'Tur til Zoo')))
    assert sremote.update(u'https://hosted.example/x.json', DAY) is True
    assert [t['summary'] for t in ha.todo] == [
        u'Alma · Matematik: Aflever opgave']
    assert [e['summary'] for e in ha.events] == [u'Alma: Tur til Zoo']
    assert set(sstate.getSync('todo')) == {LEKTIE_ID}
    assert set(sstate.getSync('calendar')) == {u'Alma 5C|2026-11-03||0'}


#
# Indholdet kommer udefra
#

def test_the_past_is_left_out_again(captured, monkeypatch):
    serve(monkeypatch, feed(
        point(id=u'a', dato=u'2026-11-01'),                 # i går
        point(id=u'b', dato=u'2026-11-02'),                 # i dag
        point(id=u'c', dato=None, uge=u'44-2026', kategori=u'info'),
        point(id=u'd', dato=None, uge=WID, kategori=u'info')))
    sremote.update(u'https://hosted.example/x.json', DAY)
    rows = sremote.entries(sremote.fetch(None), DAY)
    assert [r['key'] for r in rows] == [u'b', u'd']


@pytest.mark.parametrize('bad', [
    {'id': None}, {'id': u''}, {'id': 7}, {'barn': u''}, {'barn': None},
    {'kategori': u'hemmelig'}, {'kategori': None}, {'dato': u'i morgen'},
    {'dato': u'2026-13-40'}, {'dato': 20261106},
    {'kort': u'', 'tekst': u''}, {'kort': None, 'tekst': None},
])
def test_invalid_items_are_skipped(bad):
    rows = sremote.entries(feed(point(**bad), point(id=u'ok')), DAY)
    assert [r['key'] for r in rows] == [u'ok']


def test_duplicate_ids_and_non_dicts_are_skipped():
    rows = sremote.entries(feed(point(), point(kort=u'igen'), u'x', None,
                                [1]), DAY)
    assert [r['short'] for r in rows] == [u'Aflever opgave']


def test_long_text_is_cut_and_short_text_is_made_from_the_text():
    rows = sremote.entries(feed(point(tekst=u'x' * 10000, kort=None)), DAY)
    assert len(rows[0]['text']) == sremote.MAX_TEXT
    assert len(rows[0]['short']) == 160


def test_too_many_items_are_cut():
    many = [point(id=str(i)) for i in range(sremote.MAX_ITEMS + 5)]
    assert len(sremote.entries(feed(*many), DAY)) == sremote.MAX_ITEMS


@pytest.mark.parametrize('data', [
    feed(punkter=u'nej', seneste_aendring={'x': 1}),
    feed(seneste_aendring=[
        u'x', {'barn': None}, {'barn': CHILD, 'aendringer': u'nej'}]),
])
def test_wrong_types_give_an_empty_overview(captured, monkeypatch, data):
    serve(monkeypatch, data)
    assert sremote.update(u'https://hosted.example/x.json', DAY) is True
    (state, attributes), = captured
    assert state == u'Intet særligt at huske'
    assert attributes['punkter'] == []


def test_school_text_cannot_break_the_markdown(captured, monkeypatch):
    serve(monkeypatch, feed(point(kort=u'[klik](http://x) <b>**fed**</b>')))
    sremote.update(u'https://hosted.example/x.json', DAY)
    (_, attributes), = captured
    assert u'\\[klik\\]' in attributes['markdown']
    assert u'<b>' not in attributes['markdown']


#
# Hentning
#

class Feed(http.server.BaseHTTPRequestHandler):
    status = 200
    body = b''
    headers_ = {}
    paths = []

    def do_GET(self):
        Feed.paths.append(self.path)
        self.send_response(Feed.status)
        for k, v in Feed.headers_.items():
            self.send_header(k, v)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(Feed.body)))
        self.end_headers()
        self.wfile.write(Feed.body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Feed.status, Feed.body, Feed.headers_, Feed.paths = 200, b'', {}, []
    srv = http.server.HTTPServer(('127.0.0.1', 0), Feed)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield 'http://127.0.0.1:%d/overblik/%s.json' % (srv.server_port, TOKEN)
    srv.shutdown()


def test_fetch(server):
    Feed.body = json.dumps(feed(point())).encode('utf-8')
    assert sremote.fetch(server)['punkter'] == [point()]
    assert Feed.paths == ['/overblik/%s.json' % TOKEN]


@pytest.mark.parametrize('status, hint', [
    (404, u'slået fra'), (429, u'for mange'), (503, u'intet overblik'),
    (500, u'HTTP 500')])
def test_http_errors_are_explained_without_the_link(server, status, hint):
    Feed.status = status
    with pytest.raises(sremote.FeedError) as e:
        sremote.fetch(server)
    assert hint in str(e.value)
    assert TOKEN not in str(e.value)


def test_redirect_is_not_followed(server):
    Feed.status = 302
    Feed.headers_ = {'Location': '/andet-sted'}
    with pytest.raises(sremote.FeedError) as e:
        sremote.fetch(server)
    assert u'omdirigering' in str(e.value)
    assert Feed.paths == ['/overblik/%s.json' % TOKEN]


@pytest.mark.parametrize('body, msg', [
    (b'x' * (sremote.MAX_BYTES + 1), u'større end'),
    (b'<html>', u'ikke gyldig JSON'),
    (b'\xff\xfe', u'ikke gyldig JSON'),
    (b'[1, 2]', u'ikke et skoleoverblik'),
    (b'{"version": 2}', u'version 2'),
    (b'{"version": "1"}', u'version ?'),
])
def test_bad_answers_are_refused(server, body, msg):
    Feed.body = body
    with pytest.raises(sremote.FeedError) as e:
        sremote.fetch(server)
    assert msg in str(e.value)


def test_no_connection():
    with pytest.raises(sremote.FeedError) as e:
        sremote.fetch('http://127.0.0.1:9/overblik/%s.json' % TOKEN)
    assert u'ingen forbindelse' in str(e.value)
    assert TOKEN not in str(e.value)


def test_failed_fetch_leaves_home_assistant_alone(server, captured, capsys,
                                                  options):
    Feed.status = 404
    assert sremote.update(server, DAY) is False
    assert captured == []
    err = capsys.readouterr().err
    assert u'127.0.0.1' in err and u'HTTP 404' in err
    assert TOKEN not in err


#
# Opsætning og kørsel
#

@pytest.fixture
def env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith('FSKINTRA_'):
            monkeypatch.delenv(name)
    root = tmp_path / 'root'
    root.mkdir()
    monkeypatch.setattr(config, 'ROOT', str(root) + os.sep)
    monkeypatch.setattr(config, 'CONFIG_FN', str(root / 'skoleintra.txt'))
    monkeypatch.setenv('FSKINTRA_HA_URL', 'http://ha.local:8123')
    monkeypatch.setenv('FSKINTRA_HA_TOKEN', 'ha-token')
    monkeypatch.setenv('FSKINTRA_OVERVIEW_URL',
                       'https://hosted.example/overblik/%s.json' % TOKEN)
    return root


def parse(*argv):
    config.parseArgs(['--config-file', config.CONFIG_FN,
                      '--overview-from-url'] + list(argv))
    return config.options


def test_needs_neither_login_nor_smtp(env):
    opts = parse()
    assert opts.overviewurl == \
        'https://hosted.example/overblik/%s.json' % TOKEN
    assert (opts.haurl, opts.hatoken) == ('http://ha.local:8123', 'ha-token')
    assert opts.hatodo == 'todo.lektier'
    assert opts.statedir == str(env / 'state')
    assert os.path.isdir(opts.statedir)
    assert opts.anthropicapikey == u''
    assert not hasattr(opts, 'senderemail')


def test_profile_decides_where_the_state_is(env, monkeypatch):
    # Samme state.json som ved egen hentning: det, der er synkroniseret
    for k, v in (('LOGINTYPE', 'alm'), ('USERNAME', 'petjen'),
                 ('PASSWORD', 'x'), ('HOSTNAME', 'a.m.skoleintra.dk'),
                 ('CACHEPREFIX', 'aaskolen')):
        monkeypatch.setenv('FSKINTRA_' + k, v)
    assert parse().statedir == str(env / 'aaskolen-state')


def test_mqtt_alone_is_enough(env, monkeypatch):
    monkeypatch.delenv('FSKINTRA_HA_URL')
    monkeypatch.delenv('FSKINTRA_HA_TOKEN')
    monkeypatch.setenv('FSKINTRA_MQTT_HOST', '192.168.1.25')
    assert parse().mqtthost == '192.168.1.25'


@pytest.mark.parametrize('change, msg', [
    ({'FSKINTRA_OVERVIEW_URL': ''}, u'kræver, at FSKINTRA_OVERVIEW_URL'),
    ({'FSKINTRA_OVERVIEW_URL': 'http://hosted.example/overblik/%s.json'
      % TOKEN}, u'https-adresse'),
    ({'FSKINTRA_OVERVIEW_URL': 'https://user:%s@hosted.example/' % TOKEN},
     u'https-adresse'),
    ({'FSKINTRA_HA_TOKEN': ''}, u'kræver Home Assistant'),
])
def test_invalid_setup_is_refused_without_showing_the_link(env, monkeypatch,
                                                           capsys, change,
                                                           msg):
    for k, v in change.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(SystemExit) as e:
        parse()
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert msg in err
    assert TOKEN not in err


@pytest.mark.parametrize('flag', ['--catch-up', '--overview-only',
                                  '--check-login', '--purge'])
def test_cannot_be_combined(env, flag, capsys):
    with pytest.raises(SystemExit) as e:
        parse(flag)
    assert e.value.code == 2
    assert u'kan ikke kombineres' in capsys.readouterr().err


@pytest.mark.parametrize('url, ok', [
    ('https://hosted.example/overblik/x.json', True),
    ('https://hosted.example:8443/x', True),
    ('http://localhost:8000/x', True),
    ('http://127.0.0.1:8000/x', True),
    ('http://[::1]:8000/x', True),
    ('http://hosted.example/x', False),
    ('http://192.168.1.10/x', False),
    ('ftp://hosted.example/x', False),
    ('https://@hosted.example/x', False),
    ('https://hosted.example:99999/x', False),
    ('https:///x', False),
    ('https://hosted.example/x y', False),
    ('', False),
])
def test_valid_urls(url, ok):
    assert config.isValidOverviewUrl(url) is ok


def test_main_runs_and_exits_with_error_on_failure(env, monkeypatch):
    calls = []
    monkeypatch.setattr(sremote, 'update',
                        lambda url: calls.append(url) or True)
    fskintra.main(['--config-file', config.CONFIG_FN, '--overview-from-url'])
    assert calls == ['https://hosted.example/overblik/%s.json' % TOKEN]

    monkeypatch.setattr(sremote, 'update', lambda url: False)
    with pytest.raises(SystemExit) as e:
        fskintra.main(['--config-file', config.CONFIG_FN,
                       '--overview-from-url'])
    assert e.value.code == config.EXIT_ERROR
