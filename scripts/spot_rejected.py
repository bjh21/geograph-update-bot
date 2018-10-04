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
from urllib.parse import urlsplit

site = pywikibot.Site()
geodb = sqlite3.connect('geograph-db/geograph.sqlite3')
geodb.row_factory = sqlite3.Row

client = requests.Session()
client.headers['User-Agent'] = "spot_rejected (bjh21@bjh21.me.uk)"

def find_rejected(**kwargs):
    outfile = StringIO()
    c = geodb.cursor()
    c.execute("""
        SELECT MAX(gridimage_id) FROM gridimage_base
            ORDER BY gridimage_id desc limit 1""")
    row = c.fetchone()
    maxid = row[0]
    titles_by_id = { }
    for item in api.ListGenerator("categorymembers", site=site,
            cmtitle="Category:Images from Geograph Britain and Ireland",
            cmprop="title|sortkeyprefix", cmtype="file", **kwargs):
        try:
            gridimage_id = int(item['sortkeyprefix'])
            titles_by_id[gridimage_id] = item['title']
            if gridimage_id > maxid: continue
            print(gridimage_id, end="\r")
            c = geodb.cursor()
            c.execute("""
                SELECT gridimage_id FROM gridimage_base
                WHERE gridimage_id = ?
                """, (gridimage_id,))
            if c.fetchone() == None:
                print("* [https://www.geograph.org.uk/photo/%d %d]: [[:%s]]" %
                      (gridimage_id, gridimage_id, item['title']),
                      file=outfile, flush=True)
                r = requests.head(
                    'https://www.geograph.org.uk/photo/%d' % (gridimage_id,),
                    allow_redirects=True)
                if r.status_code == 200:
                    destid = int(urlsplit(r.url).path.rpartition('/')[2])
                    if titles_by_id[destid]:
                        print("** → [%s %d]: [[:%s]]" %
                              (r.url, destid, titles_by_id[destid]),
                              file=outfile, flush=True)
                    print("** → [%s %d]" % (r.url, destid),
                          file=outfile, flush=True)
        except Exception:
            pass
    reportpage = pywikibot.Page(pywikibot.Site(),
                "User:Geograph Update Bot/images rejected from Geograph/data")
    reportpage.text = (
        "<!-- This page will be overwritten by Geograph Update Bot -->")
    reportpage.text += outfile.getvalue()
    reportpage.save("New list of rejected IDs")

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
    find_rejected()
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
