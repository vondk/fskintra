# -*- coding: utf-8 -*-
import json

import pytest

from conftest import CHILD, WID, plan
from skoleintra import pgWeekplans, shass, smqtt, soverview, sstate


@pytest.fixture
def mqtt(monkeypatch, options):
    options.mqtthost = '192.168.1.25'
    options.mqttport = '1883'
    options.mqttuser = ''
    options.mqttpassword = ''
    calls = []

    def fake(msgs, **kwargs):
        calls.append((msgs, kwargs))
    monkeypatch.setattr(smqtt, '_publishMultiple', fake)
    return calls


def _by_topic(msgs):
    return dict((m['topic'], m) for m in msgs)


def test_messages_are_retained_discovery_state_and_attributes():
    attrs = {'friendly_name': u'Skoleoverblik', 'icon': 'mdi:school',
             'markdown': u'## Bianca 4B', 'kilde': u'ai'}
    msgs = _by_topic(smqtt.messages('sensor.skoleintra_overblik',
                                    u'x' * 300, attrs))
    assert all(m['retain'] and m['qos'] == 1 for m in msgs.values())

    cfg = json.loads(msgs['homeassistant/sensor/fskintra/'
                          'skoleintra_overblik/config']['payload'])
    assert cfg['unique_id'] == 'fskintra_skoleintra_overblik'
    assert cfg['default_entity_id'] == 'sensor.skoleintra_overblik'
    assert cfg['state_topic'] == 'fskintra/skoleintra_overblik/state'
    assert cfg['json_attributes_topic'] == \
        'fskintra/skoleintra_overblik/attributes'

    state = msgs['fskintra/skoleintra_overblik/state']['payload']
    assert len(state.decode('utf-8')) == 255

    sent = json.loads(msgs['fskintra/skoleintra_overblik/attributes']
                      ['payload'])
    assert sent == {'markdown': u'## Bianca 4B', 'kilde': u'ai'}


def test_publish_uses_host_port_and_auth(mqtt, options):
    options.mqttuser = 'fskintra'
    options.mqttpassword = 'hemmeligt'
    assert smqtt.publishOverview('sensor.skoleintra_overblik', u'ok', {})
    (msgs, kwargs), = mqtt
    assert kwargs['hostname'] == '192.168.1.25' and kwargs['port'] == 1883
    assert kwargs['auth'] == {'username': 'fskintra',
                              'password': 'hemmeligt'}
    assert len(msgs) == 3


def test_publish_anonymous_without_user(mqtt):
    smqtt.publishOverview('sensor.skoleintra_overblik', u'ok', {})
    assert mqtt[0][1]['auth'] is None


def test_publish_error_is_logged_not_raised(monkeypatch, options):
    options.mqtthost = '127.0.0.1'
    options.mqttport = '9'

    def boom(msgs, **kwargs):
        raise ConnectionRefusedError('nej')
    monkeypatch.setattr(smqtt, '_publishMultiple', boom)
    assert smqtt.publishOverview('sensor.x', u'x', {}) is False


def _fill_state():
    items = pgWeekplans.extractItems(plan('c'), WID)
    sstate.putWeekplan(CHILD, WID, u'Uge 45', items, 'x')


def test_overview_uses_mqtt_instead_of_rest(mqtt, monkeypatch, options):
    _fill_state()
    pushed, deleted, synced = [], [], []
    options.haurl, options.hatoken = 'http://ha:8123', 't'
    monkeypatch.setattr(shass, 'pushState',
                        lambda *a: pushed.append(a) or True)
    monkeypatch.setattr(shass, 'deleteState',
                        lambda e: deleted.append(e) or True)
    monkeypatch.setattr(soverview.ssync, 'sync',
                        lambda entries, today: synced.append(entries))

    assert soverview.update() is True
    assert pushed == []                       # ingen REST-sensor
    assert deleted == ['sensor.skoleintra_overblik']   # engangsoprydning
    assert len(mqtt) == 1 and synced          # MQTT + to-do/kalender

    soverview.update()
    assert deleted == ['sensor.skoleintra_overblik']   # kun én gang
    assert len(mqtt) == 2


def test_overview_without_mqtt_uses_rest(monkeypatch, options):
    _fill_state()
    pushed = []
    options.haurl, options.hatoken = 'http://ha:8123', 't'
    monkeypatch.setattr(shass, 'pushState',
                        lambda *a: pushed.append(a) or True)
    monkeypatch.setattr(soverview.ssync, 'sync', lambda entries, today: None)
    assert soverview.update() is True
    assert len(pushed) == 1


def test_mqtt_only_without_rest(mqtt, monkeypatch):
    _fill_state()
    monkeypatch.setattr(shass, 'deleteState',
                        lambda e: pytest.fail('ingen REST sat op'))
    assert soverview.update() is True
    assert len(mqtt) == 1
