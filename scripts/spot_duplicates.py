from __future__ import print_function

import hashlib
from io import StringIO
import pywikibot
from pywikibot.bot import (
    SingleSiteBot, ExistingPageBot, NoRedirectPageBot, AutomaticTWSummaryBot)
import pywikibot.bot as bot
import pywikibot.data.api as api
import pywikibot.pagegenerators
import re
import requests
import sqlite3
import tempfile

site = pywikibot.Site()

def find_duplicates(**kwargs):
    last_id = dup_id = -1
    outfile = StringIO()
    for item in api.ListGenerator("categorymembers",
            cmtitle="Category:Images from Geograph Britain and Ireland",
            cmprop="title|sortkeyprefix", cmtype="file", **kwargs):
        try:
            gridimage_id = int(item['sortkeyprefix'])
            print(gridimage_id, end="\r")
            if gridimage_id == last_id:
                if dup_id != last_id:
                    print(
                        "* [https://www.geograph.org.uk/photo/%d %d]" %
                        (gridimage_id, gridimage_id), file=outfile)
                    print("** [[:%s]]" % (last_title,), file=outfile)
                    dup_id = last_id
                print("** [[:%s]]" % (item['title'],), file=outfile, flush=True)
            last_id = gridimage_id
            last_title = item['title']
        except Exception:
            pass
    reportpage = pywikibot.Page(pywikibot.Site(),
                "User:Geograph Update Bot/duplicate Geograph IDs/data")
    reportpage.text = (
        "<!-- This page will be overwritten by Geograph Update Bot -->")
    reportpage.text += outfile.getvalue()
    reportpage.save("New list of duplicate IDs")

def main(*args):
    options = {}
    # Process global arguments to determine desired site
    local_args = pywikibot.handle_args(args)

    # This factory is responsible for processing command line arguments
    # that are also used by other scripts and that determine on which pages
    # to work on.
    genFactory = pywikibot.pagegenerators.GeneratorFactory()

    # Parse command line arguments
    for arg in local_args:

        # Catch the pywikibot.pagegenerators options
        if genFactory.handleArg(arg):
            continue  # nothing to do here
    find_duplicates()
    return
    # The preloading option is responsible for downloading multiple
    # pages from the wiki simultaneously.
    gen = genFactory.getCombinedGenerator(preload=True)
    if not gen:
        gen = InterestingGeographGenerator()
    if gen:
        # pass generator and private options to the bot
        bot = UpgradeSizeBot(gen, **options)
        bot.run()  # guess what it does
        return True
    else:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False
main()
