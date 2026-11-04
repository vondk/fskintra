# -*- coding: utf-8 -*-
'''SMTP: login må kun ske over en krypteret forbindelse med et gyldigt
certifikat, og marker-mode gemmer ingen kopi af mailen'''
import os
import smtplib
import ssl

import pytest

from conftest import CHILD
from skoleintra import semail


class FakeSMTP:
    instances = []
    starttlsError = None

    def __init__(self, host, port, context=None):
        self.host, self.port, self.context = host, port, context
        self.calls = []
        FakeSMTP.instances.append(self)

    def starttls(self, context=None):
        self.calls.append(('starttls', context))
        if FakeSMTP.starttlsError:
            raise FakeSMTP.starttlsError

    def login(self, user, password):
        self.calls.append(('login', user))

    def sendmail(self, frm, to, msg):
        self.calls.append(('sendmail', to))

    def close(self):
        self.calls.append(('close',))

    def quit(self):
        self.calls.append(('quit',))


@pytest.fixture
def smtp(monkeypatch, options):
    FakeSMTP.instances = []
    FakeSMTP.starttlsError = None
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', FakeSMTP)
    options.smtphostname = 'smtp.example.net'
    options.smtpport = 587
    options.smtpusername = 'bruger'
    options.smtppassword = 'kode'
    options.smtpverifyssl = 'true'
    return FakeSMTP


def _names(server):
    return [c[0] for c in server.calls]


def test_starttls_with_verified_certificate_before_login(smtp):
    server = semail.smtpConnect()
    assert _names(server) == ['starttls', 'login']
    ctx = server.calls[0][1]
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname


def test_failed_starttls_never_sends_login(smtp):
    smtp.starttlsError = smtplib.SMTPNotSupportedError('ingen STARTTLS')
    with pytest.raises(smtplib.SMTPNotSupportedError):
        semail.smtpConnect()
    (server,) = smtp.instances
    assert 'login' not in _names(server)
    assert _names(server)[-1] == 'close'


def test_port_465_uses_ssl_with_context_and_no_starttls(smtp, options):
    options.smtpport = 465
    server = semail.smtpConnect()
    assert server.port == 465
    assert server.context.verify_mode == ssl.CERT_REQUIRED
    assert _names(server) == ['login']


def test_no_login_means_no_starttls(smtp, options):
    options.smtpusername = options.smtppassword = ''
    server = semail.smtpConnect()
    assert server.calls == []


def test_verify_ssl_false_still_encrypts(smtp, options):
    options.smtpverifyssl = 'false'
    server = semail.smtpConnect()
    ctx = server.calls[0][1]
    assert _names(server) == ['starttls', 'login']
    assert ctx.verify_mode == ssl.CERT_NONE


@pytest.mark.parametrize('mode,files', [('full', 2), ('marker', 0)])
def test_store_messages_mode(options, mode, files):
    options.storemessages = mode
    msg = semail.Message(CHILD, 'pln', u'<p>Lektie: læs side 4</p>')
    msg.setTitle(u'Ugeplan')
    assert msg.store()
    dn = os.path.join(options.msgdir, msg.getLongMessageID())
    assert len(os.listdir(dn)) == files
    # Markeringen er nok til at beskeden ikke sendes igen
    assert msg.hasBeenSent()
