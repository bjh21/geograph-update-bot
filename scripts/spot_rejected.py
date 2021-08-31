from __future__ import print_function

from io import StringIO
import pywikibot
import pywikibot.bot as bot
import pywikibot.comms.http as http
import pywikibot.data.api as api
import pywikibot.pagegenerators
import sqlite3
from urllib.parse import urlsplit

geodb = sqlite3.connect('geograph-db/geograph.sqlite3')
geodb.row_factory = sqlite3.Row

def find_rejected():
    outfile = StringIO()
    site = pywikibot.Site()
    c = geodb.cursor()
    c.execute("""
        SELECT MAX(gridimage_id) FROM gridimage_base
            ORDER BY gridimage_id desc limit 1""")
    row = c.fetchone()
    maxid = row[0]
    titles_by_id = { }
    for item in api.ListGenerator("categorymembers", site=site,
            cmtitle="Category:Images from Geograph Britain and Ireland",
            cmprop="title|sortkeyprefix", cmtype="file"):
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
                r = http.fetch(
                    'https://www.geograph.org.uk/photo/%d' % (gridimage_id,),
                    method='HEAD', allow_redirects=True)
                if r.status_code == 200:
                    destid = int(urlsplit(r.url).path.rpartition('/')[2])
                    if titles_by_id[destid]:
                        print("** → [%s %d]: [[:%s]]" %
                              (r.url, destid, titles_by_id[destid]),
                              file=outfile, flush=True)#
                    else:
                        print("** → [%s %d]" % (r.url, destid),
                              file=outfile, flush=True)
        except Exception:
            pass
    reportpage = pywikibot.Page(site,
                "User:Geograph Update Bot/images rejected from Geograph/data")
    reportpage.text = (
        "<!-- This page will be overwritten by Geograph Update Bot -->\n")
    reportpage.text += outfile.getvalue()
    reportpage.save("[[User:Geograph Update Bot/REJR|Updated]] list "
                    "of rejected IDs")

def main(*args):
    # Process global arguments to determine desired site
    local_args = pywikibot.handle_args(args)

    find_rejected()

main()
