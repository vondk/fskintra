#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import json

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
import skoleintra.sstate


def main(argv=None):
    skoleintra.config.parseArgs(argv)

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

    # Opdatér skoleoverblikket i Home Assistant (hvis sat op)
    skoleintra.soverview.update()


if __name__ == '__main__':
    main()
