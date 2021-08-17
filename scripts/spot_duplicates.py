from __future__ import print_function

from io import StringIO
from itertools import groupby
import pywikibot
import pywikibot.bot as bot
import pywikibot.data.api as api
import pywikibot.pagegenerators
import sys

def find_duplicates():
    last_id = dup_id = -1
    outfile = StringIO()
    site = pywikibot.Site()
    for gridimage_id, items in groupby(
            api.QueryGenerator(
                site=site, parameters=dict(
                    generator="categorymembers",
                    gcmtitle=
                    "Category:Images from Geograph Britain and Ireland",
                    gcmtype="file",
                    prop="categories|imageinfo", cllimit="max",
                    clprop="sortkey",
                    clcategories=
                    "Category:Images from Geograph Britain and Ireland",
                    iiprop="size")),
            key=lambda page: int(page['categories'][0]['sortkeyprefix'])):
        try:
            print(gridimage_id, end="\r")
            items = list(items)
            if len(items) > 1:
                print(
                    "* [https://www.geograph.org.uk/photo/%d %d]" %
                    (gridimage_id, gridimage_id), file=outfile)
                for item in items:
                    print("** (%d × %d) [[:%s]]" %
                          (item['imageinfo'][0]['width'],
                           item['imageinfo'][0]['height'],
                           item['title'],), file=outfile, flush=True)
        except Exception:
            pass
    reportpage = pywikibot.Page(site,
                "User:Geograph Update Bot/duplicate Geograph IDs/data")
    reportpage.text = (
        "<!-- This page will be overwritten by Geograph Update Bot -->\n")
    reportpage.text += outfile.getvalue()
    reportpage.save("[[User:Geograph Update Bot/DUPR|New list]] "
                    "of duplicate IDs")

def main(*args):
    # Process global arguments to determine desired site
    local_args = pywikibot.handle_args(args)

    find_duplicates()

main()
