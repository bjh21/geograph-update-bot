from __future__ import print_function

from io import StringIO
from itertools import groupby
import pywikibot
import pywikibot.bot as bot
import pywikibot.comms.http as http
import pywikibot.data.api as api
import pywikibot.pagegenerators
import sys

def find_duplicates():
    last_id = dup_id = -1
    outfile = StringIO()
    site = pywikibot.Site()
    r = http.fetch(
        "https://quarry.wmflabs.org/query/58785/result/latest/0/json")
    r.raise_for_status()
    j = r.json()
    for row in j['rows']:
        gridimage_id = row[0]
        print(
            "* [https://www.geograph.org.uk/photo/%d %d]" %
            (gridimage_id, gridimage_id), file=outfile)
        pageids = row[1].split(",")
        mwrequest = site._simple_request(action="query",
                                         pageids="|".join(pageids),
                                         prop="imageinfo|images|links",
                                         iiprop="size", imlimit="max",
                                         plnamespace="6", pllimit="max")
        data = mwrequest.submit()
        items = data['query']['pages'].values()
        crosslinks = {(s['title'], d['title'])
                      for s in items
                      for d in
                      s.get('images', []) + s.get('links', [])}
        relevant_titles = {i['title'] for i in items}
        crosslinks = {(i, j) for i, j in crosslinks
                      if i != j and j in relevant_titles}
        for item in items:
            try:
                inlinks = {(s, d) for s, d in crosslinks
                           if d == item['title']}
                outlinks = {(s, d) for s, d in crosslinks
                            if s == item['title']}
                bidilinks = {(s, d) for s, d in inlinks
                             if (d, s) in outlinks}
                print("** (%d × %d) %s[[:%s]]" %
                      (item['imageinfo'][0]['width'],
                       item['imageinfo'][0]['height'],
                       "⇌ " * len(bidilinks) +
                       "← " * (len(outlinks) - len(bidilinks)) +
                       "→ " * (len(inlinks) - len(bidilinks)),
                       item['title'],), file=outfile, flush=True)
            except Exception as e:
                print("<!-- Exception: %s -->" % e, file=outfile, flush=True)

    reportpage = pywikibot.Page(site,
                "User:Geograph Update Bot/duplicate Geograph IDs/data")
    reportpage.text = (
        "<!-- This page will be overwritten by Geograph Update Bot -->\n")
    reportpage.text += outfile.getvalue()
    reportpage.save("[[User:Geograph Update Bot/DUPR|Updated]] list "
                    "of duplicate IDs")

def main(*args):
    # Process global arguments to determine desired site
    local_args = pywikibot.handle_args(args)

    find_duplicates()

main()
