#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import json
import sys

import skoleintra.config
import skoleintra.schildren
import skoleintra.snotifications
import skoleintra.pgFrontpage
import skoleintra.pgContacts
import skoleintra.pgDialogue
import skoleintra.pgDocuments
import skoleintra.pgHomework
import skoleintra.pgPhotos
import skoleintra.pgSignup
import skoleintra.pgWeekplans
import skoleintra.soverview
import skoleintra.sretention
import skoleintra.sstate


def main(argv=None):
    skoleintra.config.parseArgs(argv)

    if skoleintra.config.options.printpaths:
        # Hvor ligger de gemte data? (stabil kontrakt for driftslag)
        print(json.dumps(skoleintra.sretention.paths(), ensure_ascii=False,
                         sort_keys=True))
        return

    if skoleintra.config.options.forgetlogin:
        # Nulstil login: slet browser-tilstanden (cookies)
        removed = skoleintra.sretention.forgetLogin()
        print(json.dumps({'forgotten': removed}, ensure_ascii=False))
        return

    if skoleintra.config.options.purge:
        # Slet alt gemt for denne FSKINTRA_ROOT. Exit 0, også hvis der
        # intet var at slette
        removed, failed = skoleintra.sretention.purge()
        for path, err in failed:
            skoleintra.config.log(u'Kunne ikke slette %s: %s' % (path, err),
                                  0)
        print(json.dumps({'purged': removed}, ensure_ascii=False))
        if failed:
            sys.exit(skoleintra.config.EXIT_ERROR)
        return

    if skoleintra.config.options.checklogin:
        # Log blot ind og vis hvilke børn der er adgang til. Fejler login,
        # afsluttes med config.EXIT_LOGIN_FAILED/EXIT_SITE_ERROR
        cnames = skoleintra.schildren.getChildren()
        print(json.dumps({'children': cnames}, ensure_ascii=False))
        return

    if skoleintra.config.options.overviewonly:
        # Genbyg kun skoleoverblikket ud fra tidligere hentede ugeplaner
        skoleintra.soverview.update()
        return

    # Opbevaring (slået fra som standard): cachen ryddes før der hentes
    # nyt, så det også sker i en kørsel, der senere fejler (fx login)
    if skoleintra.config.options.prunecachedays:
        skoleintra.sretention.pruneCache(
            skoleintra.config.options.prunecachedays)

    (full, state) = skoleintra.snotifications.checkForUpdates()
    if not full:
        return

    cnames = skoleintra.schildren.getChildren()

    # Sections/pages are considered in the order they were imported
    for sf in skoleintra.config.PAGE_SECTIONS:
        sf.maybeRun(cnames)

    # save updated state
    skoleintra.snotifications.saveState(state)

    # Ryd op i det gemte (udløbne ugeplaner og "seneste ændring") - også
    # når der ikke er sat noget overblik op
    skoleintra.sstate.prune(datetime.date.today())

    # Opbevaring (slået fra som standard): markeringer af sendte mails,
    # hvis indhold ikke længere findes på ForældreIntra. Sker kun her,
    # sidst i en gennemført kørsel, hvor alt indhold er set efter
    if skoleintra.config.options.prunemarkersdays:
        skoleintra.sretention.pruneMarkers(
            skoleintra.config.options.prunemarkersdays,
            skoleintra.config.options.sections)

    # Opdatér skoleoverblikket i Home Assistant (hvis sat op)
    skoleintra.soverview.update()


if __name__ == '__main__':
    main()
