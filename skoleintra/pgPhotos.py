# -*- coding: utf-8 -*-

import glob
import json
import hashlib
import os
import re

from . import config
from . import sbs4
from . import schildren
from . import semail
from . import surllib

SECTION = 'pht'
MAX_CACHE_AGE = .99
PHOTOS_PER_EMAIL = 5


def photoNames(title, photos):
    '''Filnavne uden endelse til de vedhæftede billeder, fx "Halloween 03".
    Numrene følger rækkefølgen i albummet, så de fortsætter på tværs af
    mails med PHOTOS_PER_EMAIL billeder'''
    base = re.sub(r'[\\/:*?"<>|]+', u'-', title)
    base = u' '.join(base.split()).strip(u' .-') or u'Billede'
    width = max(2, len(str(len(photos))))
    names = {}
    for i, url in enumerate(photos):
        names.setdefault(url, u'%s %0*d' % (base, width, i + 1))
    return names


def photoKey(url):
    '''Nøgle for et billede i listen over tidligere sendte. En hashværdi,
    så selve adressen (der indeholder barnets navn) ikke skal gemmes, når
    der kun gemmes markeringer'''
    return hashlib.sha256(url.encode('utf-8')).hexdigest()


def previouslySentPhotos(mid):
    '''Nøgler (photoKey) for de billeder i albummet, der er sendt før.

    Med FSKINTRA_STORE_MESSAGES=full står adresserne i den gemte kopi
    ('data'). Med 'marker' gemmes ingen kopi - der ligger i stedet kun
    nøglerne ('photo_keys') ved markeringen. Uden dem ville et album, der
    får nye billeder, blive sendt forfra'''
    keys = set()
    for dn in semail.hasSentMessage(tp=SECTION, mid=mid):
        for fn in glob.glob(os.path.join(dn, '*.json')):
            try:
                with open(fn, encoding='utf-8') as fd:
                    jsn = json.load(fd)
            except (ValueError, OSError):
                continue  # Simply ignore files with wrong JSON
            if not isinstance(jsn, dict):
                continue
            keys.update(photoKey(url) for url in jsn.get('data') or []
                        if isinstance(url, str))
            keys.update(key for key in jsn.get('photo_keys') or []
                        if isinstance(key, str))
    return keys


def sendPhotos(cname, title, mid, photos):
    '''Send photos if they have not already been sent'''

    # First determine if any of the photos were sent earlier
    previouslySent = previouslySentPhotos(mid)

    pending = list(url for url in photos
                   if photoKey(url) not in previouslySent)

    if not pending:
        return

    if len(photos) - len(pending) < 5:
        # At most 5 pictures has been sent earlier - send them all again
        pending = photos

    names = photoNames(title, photos)

    # Send the photos in e-mails of PHOTOS_PER_EMAIL pictures
    ecount = (len(pending)-1) // PHOTOS_PER_EMAIL + 1

    for ei in range(ecount):
        pics = pending[:PHOTOS_PER_EMAIL]
        del pending[:PHOTOS_PER_EMAIL]

        # Create HTML snippet. Den skal forblive uændret, da den indgår i md5
        # (ellers gensendes alle album). <img> laves om til vedhæftede filer
        # af semail via setImagesAsAttachments()
        itag = u'<img style="max-width: 100%">'
        ebs = sbs4.beautify(u'<h2></h2><p>%s</p>' %
                            u'<br/>'.join([itag] * len(pics)))
        ebs.h2.string = title
        for i, img in enumerate(ebs.select('img')):
            img['src'] = pics[i]

        msg = semail.Message(cname, SECTION, str(ebs))
        if ecount > 1:
            msg.setTitle(u'Billeder: %s (%d/%d)' % (title, ei+1, ecount))
        else:
            msg.setTitle(u'Billeder: %s' % title)
        msg.setMessageID(mid)
        msg.setData(pics)
        msg.setMarkerData({'photo_keys': [photoKey(url) for url in pics]})
        msg.setImagesAsAttachments(names)
        msg.maybeSend()


def findPhotosInFolder(cname, url, bs):
    '''Search a folder for new photos'''
    title = bs.h2.text.strip()
    mid = hashlib.md5(url.encode('utf-8')).hexdigest()[::2]
    photos = []

    for img in bs.select('img'):
        if not img.has_attr('src'):
            continue
        url = surllib.absurl(img['src'])
        photos.append(url)

    ptext = u'%d billeder' % len(photos) if len(photos) != 1 else '1 billede'

    config.clog(cname, u'Billeder: %s: %s' % (title, ptext))

    if not photos:
        return

    sendPhotos(cname, title, mid, photos)


def findPhotos(cname, bs):
    prefix = schildren.getChildURLPrefix(cname)

    for opt in bs.select('#sk-photos-toolbar-filter option'):
        if not opt.has_attr('value'):
            continue
        url = surllib.absurl(opt['value'])
        folder = opt.text.strip()
        if not url.startswith(prefix):
            config.clog(cname, u'Billeder: %s: ukendt URL %r' %
                        (folder, opt['value']))
            continue

        bs2 = surllib.skoleGetURL(url, True, MAX_CACHE_AGE)
        findPhotosInFolder(cname, url, bs2)


@config.Section(SECTION)
def skolePhotos(cname):
    'Billeder'
    url = schildren.getChildURL(cname, '/photos/archives')
    bs = surllib.skoleGetURL(url, True, MAX_CACHE_AGE)

    config.clog(cname, u'Kigger efter billeder')
    findPhotos(cname, bs)
