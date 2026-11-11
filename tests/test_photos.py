# -*- coding: utf-8 -*-
import email

import pytest

from skoleintra import pgPhotos, semail, surllib

CHILD = u'Alma 5C'
JPEG = b'\xff\xd8\xff\xe0' + b'J' * 100
PNG = b'\x89PNG\r\n\x1a\n' + b'P' * 100


def url(i):
    return u'https://skole.m.skoleintra.dk/parent/1/Alma/photos/%d' % i


@pytest.fixture
def sent(monkeypatch):
    '''Billed-URL'er giver JPEG (nr. 2 PNG); sendte beskeder opsamles'''
    def fake_get(u, asSoup=False, *a, **kw):
        return PNG if u == url(2) else JPEG
    monkeypatch.setattr(surllib, 'skoleGetURL', fake_get)
    msgs = []
    monkeypatch.setattr(semail.Message, 'maybeSend',
                        lambda self: msgs.append(self))
    return msgs


def parts(msg):
    '''(filnavn, content-type, disposition) for hver billeddel'''
    em = email.message_from_bytes(msg.asEmail().as_bytes())
    return [(p.get_filename(), p.get_content_type(),
             p.get_content_disposition())
            for p in em.walk() if p.get_content_maintype() == 'image']


def html_of(msg):
    em = email.message_from_bytes(msg.asEmail().as_bytes())
    for p in em.walk():
        if p.get_content_type() == 'text/html':
            return p.get_payload(decode=True).decode('utf-8')


def test_billeder_vedhaeftes_som_filer(sent):
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', [url(1), url(2)])
    msg, = sent
    assert parts(msg) == [
        (u'Halloween 01.jpg', 'image/jpeg', 'attachment'),
        (u'Halloween 02.png', 'image/png', 'attachment'),
    ]
    html = html_of(msg)
    assert '<img' not in html and 'cid:' not in html
    assert u'Halloween 01.jpg' in html and u'Halloween 02.png' in html


def test_md5_uaendret(sent):
    '''HTML og md5 skal være som før, ellers gensendes alle album'''
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', [url(1), url(2)])
    msg, = sent
    assert msg.mp['html'].count('<img') == 2
    old = semail.Message(CHILD, 'pht', msg.mp['html'])
    old.setTitle(msg.mp['title'])
    old.setMessageID('abc')
    assert old.getMessageID() == msg.getMessageID()


def test_nummerering_fortsaetter_over_mails(sent):
    pgPhotos.sendPhotos(CHILD, u'Tur 4/5', 'abc', [url(i) for i in
                                                   (1, 3, 4, 5, 6, 7, 8)])
    a, b = sent
    assert [p[0] for p in parts(a)] == [u'Tur 4-5 %02d.jpg' % i
                                        for i in range(1, 6)]
    assert [p[0] for p in parts(b)] == [u'Tur 4-5 06.jpg', u'Tur 4-5 07.jpg']


def test_danske_tegn_i_filnavn(sent):
    title = u'Skovtur på Møns Klint med 4.B og 4.C'
    pgPhotos.sendPhotos(CHILD, title, 'abc', [url(1)])
    msg, = sent
    assert parts(msg)[0][0] == title + u' 01.jpg'
    head = msg.asEmail().as_string()
    assert "filename*=utf-8''Skovtur%20p%C3%A5" in head


def test_ikke_billede_vedhaeftes_ikke(sent, monkeypatch):
    monkeypatch.setattr(surllib, 'skoleGetURL',
                        lambda u, *a, **kw: b'<html>login</html>')
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', [url(1)])
    msg, = sent
    assert parts(msg) == []


def test_for_store_billeder_erstattes_af_link(sent, monkeypatch):
    '''Ved 552 genopbygges mailen; billeder over budgettet bliver til links'''
    monkeypatch.setattr(semail, 'MAX_ATTACH_BYTES', 150)
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', [url(1), url(3)])
    msg, = sent
    assert len(parts(msg)) == 2  # uden 552 vedhæftes alt
    msg._dropBigAttachments = True
    msg._email = None
    assert parts(msg) == [(u'Halloween 01.jpg', 'image/jpeg', 'attachment')]
    html = html_of(msg)
    assert u'for stor til mail' in html
    assert u"<a href='%s'>Halloween 02.jpg</a>" % url(3) in html


#
# Hvad er sendt før? (FSKINTRA_STORE_MESSAGES=full/marker)
#

@pytest.fixture
def stored(options, monkeypatch):
    '''Rigtig maybeSend/store - men uden SMTP. Returnerer listen af sendte
    beskeder som lister af billed-URL'er'''
    options.catchup = True
    monkeypatch.setattr(surllib, 'skoleGetURL',
                        lambda u, *a, **kw: JPEG)
    sent = []
    send = semail.Message.send

    def record(self):
        sent.append(self.mp['data'])
        return send(self)
    monkeypatch.setattr(semail.Message, 'send', record)
    return sent


@pytest.mark.parametrize('mode', ['full', 'marker'])
def test_album_med_nye_billeder_sender_kun_de_nye(options, stored, mode):
    '''Går et album fra 6 til 11 billeder, ændres antallet af mails (2 -> 3)
    og dermed titel og md5 for dem alle. Uden listen over tidligere sendte
    billeder ville hele albummet blive sendt igen'''
    options.storemessages = mode
    urls = [url(i) for i in range(1, 12)]
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', urls[:6])
    assert stored == [urls[:5], urls[5:6]]

    del stored[:]
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', urls[:6])
    assert stored == []                     # intet nyt

    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', urls)
    assert stored == [urls[6:11]]           # kun de fem nye


@pytest.mark.parametrize('mode', ['full', 'marker'])
def test_nye_billeder_foerst_i_albummet(options, stored, mode):
    options.storemessages = mode
    urls = [url(i) for i in range(1, 9)]
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', urls[2:])
    del stored[:]
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', urls)
    assert stored == [urls[:2]]


def test_marker_gemmer_kun_hashvaerdier(options, stored):
    '''Med marker må hverken billedadresser (med barnets navn), titel eller
    indhold ligge på disken'''
    import glob
    import json
    import os
    options.storemessages = 'marker'
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', [url(1), url(2)])
    dn, = glob.glob(os.path.join(options.msgdir, '*'))
    fn, = os.listdir(dn)
    assert fn.endswith('.json')
    with open(os.path.join(dn, fn), encoding='utf-8') as fd:
        text = fd.read()
    assert json.loads(text) == {'photo_keys': [pgPhotos.photoKey(url(1)),
                                               pgPhotos.photoKey(url(2))]}
    assert 'Alma' not in text and 'Halloween' not in text
    assert 'skoleintra' not in text


def test_markeringer_uden_liste_fra_foer(options, stored):
    '''Markeringer fra før listen blev gemt: afgørelsen falder tilbage på
    md5 som hidtil - uændrede album sendes ikke igen'''
    import glob
    import os
    options.storemessages = 'marker'
    urls = [url(i) for i in range(1, 7)]
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', urls)
    for fn in glob.glob(os.path.join(options.msgdir, '*', '*.json')):
        os.unlink(fn)
    del stored[:]
    pgPhotos.sendPhotos(CHILD, u'Halloween', 'abc', urls)
    assert stored == []


def test_andre_beskeder_gemmer_intet_med_marker(options):
    import os
    options.catchup = True
    options.storemessages = 'marker'
    msg = semail.Message(CHILD, 'frp', u'<p>Husk gymnastiktøj</p>')
    msg.setTitle(u'Husk gymnastiktøj')
    msg.setData({'unread': True})
    msg.store()
    dn, = os.listdir(options.msgdir)
    assert os.listdir(os.path.join(options.msgdir, dn)) == []
