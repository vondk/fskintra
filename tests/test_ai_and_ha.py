# -*- coding: utf-8 -*-
import datetime
import http.server
import json
import threading
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from conftest import CHILD, WID, plan
from skoleintra import pgWeekplans, sai, sdiff, shass, soverview, sstate


def items(version):
    return pgWeekplans.extractItems(plan(version), WID)


def active(version):
    '''Punkter som sstate.activeItems leverer dem til overblikket'''
    return [dict(i, child=CHILD, week=WID, weektitle=u'Uge 45')
            for i in items(version)]


class FakeClient:
    '''Erstatning for anthropic.Anthropic - returnerer et fast svar eller
    kaster en fejl, og husker kaldene'''

    def __init__(self, reply=None, error=None, stop_reason='end_turn'):
        self.calls = []
        self.reply = reply
        self.error = error
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(
            create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        content = []
        if self.reply is not None:
            content.append(SimpleNamespace(type='text',
                                           text=json.dumps(self.reply)))
        return SimpleNamespace(
            stop_reason=self.stop_reason, content=content,
            model=kwargs['model'],
            usage=SimpleNamespace(input_tokens=100, output_tokens=20))


@pytest.fixture
def fake_ai(monkeypatch, options):
    options.anthropicapikey = 'sk-ant-test'
    holder = {}

    def install(**kw):
        client = FakeClient(**kw)
        monkeypatch.setattr(sai, '_clientFactory', lambda key: client)
        holder['client'] = client
        return client
    return install


def test_disabled_without_key():
    diff = sdiff.diffItems(items('a'), items('b'))
    assert sai.summarizeChange(CHILD, u'Uge 45', diff, items('b')) is None
    assert sai.buildOverview(active('b')) is None


def test_summarize_change_request_and_result(fake_ai):
    client = fake_ai(reply={'resume': u'To nye punkter i dansk.',
                            'punkter': [{'id': 0, 'kategori': 'info'},
                                        {'id': 1, 'kategori': 'info'},
                                        {'id': 7, 'kategori': 'lektie'}]})
    diff = sdiff.diffItems(items('a'), items('b'))
    res = sai.summarizeChange(CHILD, u'Uge 45', diff, items('b'))
    assert res['resume'] == u'To nye punkter i dansk.'
    assert res['kategorier'] == {'0': 'info', '1': 'info'}  # id 7 ignoreres

    call, = client.calls
    assert call['model'] == 'claude-opus-5-5'
    assert call['output_config']['effort'] == 'low'
    assert call['output_config']['format']['type'] == 'json_schema'
    assert call['fallbacks'] == 'default'
    assert call['betas'] == ['server-side-fallback-2026-07-01']
    prompt = call['messages'][0]['content']
    assert u'[0] TILFØJET · Man 2/11 · Dansk' in prompt
    assert u'Resten af ugeplanen' in prompt and u'Lektie: Aflever' in prompt


def test_haiku_has_no_fallbacks(fake_ai, options):
    options.aimodel = 'claude-haiku-5-5'
    client = fake_ai(reply={'overskrift': u'x', 'punkter': []})
    sai.buildOverview(active('b'))
    assert 'fallbacks' not in client.calls[0]
    assert 'betas' not in client.calls[0]


@pytest.mark.parametrize('kw', [
    {'error': anthropic.APIConnectionError(
        request=httpx2.Request('POST', 'https://api.anthropic.com'))},
    {'error': anthropic.APITimeoutError(
        request=httpx2.Request('POST', 'https://api.anthropic.com'))},
    {'error': RuntimeError('uventet')},
    {'reply': {'overskrift': u'x', 'punkter': []}, 'stop_reason': 'refusal'},
    {'reply': {'overskrift': u'x', 'punkter': []},
     'stop_reason': 'max_tokens'},
    {'reply': None},
])
def test_failures_return_none(fake_ai, kw):
    fake_ai(**kw)
    assert sai.buildOverview(active('b')) is None


def test_invalid_json_returns_none(fake_ai):
    client = fake_ai(reply={})
    client.reply = None

    def bad(**kwargs):
        return SimpleNamespace(stop_reason='end_turn', model='m', usage=None,
                               content=[SimpleNamespace(type='text',
                                                        text='ikke json')])
    client.beta.messages.create = bad
    assert sai.buildOverview(active('b')) is None


class _Handler(http.server.BaseHTTPRequestHandler):
    requests = []
    status = 200

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        _Handler.requests.append((self.path, dict(self.headers),
                                  json.loads(body)))
        self.send_response(_Handler.status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{}')

    def log_message(self, *args):
        pass


@pytest.fixture
def ha(options):
    _Handler.requests = []
    _Handler.status = 200
    server = http.server.HTTPServer(('127.0.0.1', 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    options.haurl = 'http://127.0.0.1:%d/' % server.server_port
    options.hatoken = 'hemmeligt-token'
    yield _Handler
    server.shutdown()


def test_push_state(ha):
    assert shass.pushState('sensor.skoleintra_overblik', u'x' * 300,
                           {'markdown': u'æøå'})
    (path, headers, body), = ha.requests
    assert path == '/api/states/sensor.skoleintra_overblik'
    assert headers['Authorization'] == 'Bearer hemmeligt-token'
    assert len(body['state']) == 255
    assert body['attributes']['markdown'] == u'æøå'


def test_push_state_http_error_is_logged_not_raised(ha):
    ha.status = 401
    assert shass.pushState('sensor.x', u'x', {}) is False


def test_push_state_unreachable(options):
    options.haurl = 'http://127.0.0.1:9'
    options.hatoken = 't'
    assert shass.pushState('sensor.x', u'x', {}) is False


def test_overview_rule_based():
    sstate.putWeekplan(CHILD, WID, u'Ugeplan for 4B - uge 45-2026',
                       items('c'), 'x')
    state, attrs = soverview.build(datetime.date(2026, 11, 2))
    assert state == u'1 lektie'
    md = attrs['markdown']
    assert md.startswith(u'## Alma 5C')
    assert u'**Lektier og afleveringer**\n- Fre 6/11 · Matematik: Lektie' in md
    assert u'**Øvrigt**' in md and u'Stavevejen' in md
    assert attrs['kilde'] == u'regler'
    assert [p['kategori'] for p in attrs['punkter']] == ['lektie']


def test_overview_ai_is_cached_until_input_changes(fake_ai):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    reply = {'overskrift': u'Fre: aflever ugeopgave nr. 2 (matematik)',
             'punkter': [{'id': 3, 'kategori': 'aflevering',
                          'tekst': u'Aflever ugeopgave nr. 2'}]}
    client = fake_ai(reply=reply)
    day = datetime.date(2026, 11, 2)

    state, attrs = soverview.build(day)
    assert state == reply['overskrift']
    assert u'- Fre 6/11 · Matematik: Aflever ugeopgave nr. 2' in \
        attrs['markdown']
    assert attrs['kilde'] == u'ai'

    soverview.build(day)                       # samme input: ingen nyt kald
    assert len(client.calls) == 1
    soverview.build(day + datetime.timedelta(days=1))   # ny dag: nyt kald
    assert len(client.calls) == 2


def test_overview_retries_ai_after_failure(fake_ai):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    client = fake_ai(error=RuntimeError('nede'))
    day = datetime.date(2026, 11, 2)
    state, attrs = soverview.build(day)
    assert attrs['kilde'] == u'regler'
    client.error = None
    client.reply = {'overskrift': u'Nu virker det', 'punkter': []}
    state, attrs = soverview.build(day)
    assert state == u'Nu virker det' and len(client.calls) == 2


def test_update_pushes_to_ha(ha):
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items('c'), 'x')
    assert soverview.update() is True
    (path, _, body), = ha.requests
    assert path == '/api/states/sensor.skoleintra_overblik'
    assert u'## Alma 5C' in body['attributes']['markdown']
    assert 'seneste_aendring' in body['attributes']


def test_update_without_ha_does_nothing():
    assert soverview.update() is False
