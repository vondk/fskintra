# -*- coding: utf-8 -*-
'''Skoleoverblikket som rigtig Home Assistant-entitet via MQTT discovery.

Slås til med FSKINTRA_MQTT_HOST (fx 192.168.1.25). Discovery-konfiguration,
state og attributter sendes som *retained* beskeder, så brokeren gemmer dem
og Home Assistant genskaber sensoren med det samme efter en genstart -
modsat POST /api/states, hvor sensoren forsvinder indtil næste kørsel.

Kræver at Home Assistants MQTT-integration har discovery slået til (standard,
prefix "homeassistant").
'''

import json
import os

from . import config

DISCOVERY_PREFIX = 'homeassistant'
NODE_ID = 'fskintra'
OBJECT_ID = 'skoleintra_overblik'
BASE_TOPIC = 'fskintra/' + OBJECT_ID
MAX_STATE_LEN = 255

# Attributter som Home Assistant ikke tillader via json_attributes_topic -
# de sættes i stedet i discovery-konfigurationen
BLOCKED_ATTRIBUTES = ('friendly_name', 'icon', 'unit_of_measurement',
                      'device_class', 'entity_picture')


def isEnabled():
    return bool(getattr(config.options, 'mqtthost', u''))


def _publishMultiple(msgs, **kwargs):
    import paho.mqtt.publish
    paho.mqtt.publish.multiple(msgs, **kwargs)


def topics():
    return {
        'config': '%s/sensor/%s/%s/config' % (DISCOVERY_PREFIX, NODE_ID,
                                              OBJECT_ID),
        'state': BASE_TOPIC + '/state',
        'attributes': BASE_TOPIC + '/attributes',
    }


def discoveryConfig(entityId):
    t = topics()
    return {
        'name': u'Skoleoverblik',
        'unique_id': 'fskintra_' + OBJECT_ID,
        'default_entity_id': entityId,
        'state_topic': t['state'],
        'json_attributes_topic': t['attributes'],
        'icon': 'mdi:school',
        'device': {
            'identifiers': [NODE_ID],
            'name': u'fskintra',
            'manufacturer': u'fskintra',
            'model': u'ForældreIntra',
        },
    }


def messages(entityId, state, attributes):
    '''Liste af retained beskeder: discovery, attributter og state'''
    t = topics()
    attrs = dict((k, v) for k, v in attributes.items()
                 if k not in BLOCKED_ATTRIBUTES)
    payloads = (
        (t['config'], discoveryConfig(entityId)),
        # Attributter før state, så HA har dem når state skifter
        (t['attributes'], attrs),
        (t['state'], (state or u'')[:MAX_STATE_LEN]),
    )
    res = []
    for topic, payload in payloads:
        if not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False)
        res.append({'topic': topic, 'payload': payload.encode('utf-8'),
                    'qos': 1, 'retain': True})
    return res


def publishOverview(entityId, state, attributes):
    '''Send overblikket til MQTT. Returnerer True ved succes. Fejl logges
    men kastes aldrig videre'''
    if not isEnabled():
        return False
    host = config.options.mqtthost
    try:
        port = int(getattr(config.options, 'mqttport', '') or 1883)
    except ValueError:
        port = 1883
    user = getattr(config.options, 'mqttuser', u'') or u''
    auth = None
    if user:
        auth = {'username': user,
                'password': getattr(config.options, 'mqttpassword', u'') or
                None}
    try:
        _publishMultiple(messages(entityId, state, attributes),
                         hostname=host, port=port, auth=auth,
                         client_id='fskintra-%d' % os.getpid(), keepalive=30)
    except ImportError:
        config.log(u'ADVARSEL: Python-pakken paho-mqtt er ikke installeret '
                   u'- kan ikke sende skoleoverblik via MQTT', 0)
        return False
    except Exception as e:  # Må aldrig vælte en kørsel
        config.log(u'ADVARSEL: kunne ikke sende skoleoverblik til MQTT på '
                   u'%s:%d: %r' % (host, port, e), 0)
        return False
    config.log(u'MQTT: %s udgivet via %s:%d' % (entityId, host, port), 2)
    return True
