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
                    prop="categories|imageinfo|images", cllimit="max",
                    clprop="sortkey",
                    clcategories=
                    "Category:Images from Geograph Britain and Ireland",
                    iiprop="size", imlimit="max")),
            key=lambda page: int(page['categories'][0]['sortkeyprefix'])):
        try:
            print(gridimage_id, end="\r")
            items = list(items)
            if len(items) > 1:
                crosslinks = set([(s['title'], d['title'])
                                  for s in items
                                  for d in s.get('images', [])])
                relevant_titles = set([i['title'] for i in items])
                crosslinks = set([(i, j) for i, j in crosslinks
                                  if i != j and j in relevant_titles])
                print(
                    "* [https://www.geograph.org.uk/photo/%d %d]" %
                    (gridimage_id, gridimage_id), file=outfile)
                for item in items:
                    inlinks = set([(s, d) for s, d in crosslinks
                                   if d == item['title']])
                    outlinks = set([(s, d) for s, d in crosslinks
                                    if s == item['title']])
                    bidilinks = set([(s, d) for s, d in inlinks
                                     if (d, s) in outlinks])
                    print("** (%d × %d) %s[[:%s]]" %
                          (item['imageinfo'][0]['width'],
                           item['imageinfo'][0]['height'],
                           "⇌ " * len(bidilinks) +
                           "→ " * (len(outlinks) - len(bidilinks)) +
                           "← " * (len(inlinks) - len(bidilinks)),
                           item['title'],), file=outfile, flush=True)
        except Exception as e:
            print("<!-- Exception: %s -->" % e, file=outfile, flush=True)
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
