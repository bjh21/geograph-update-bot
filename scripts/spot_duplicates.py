from __future__ import print_function

from io import StringIO
from itertools import groupby
import pywikibot
import pywikibot.bot as bot
import pywikibot.data.api as api
import pywikibot.pagegenerators
import sys
import toolforge

def find_duplicates():
    outfile = StringIO()
    site = pywikibot.Site()
    conn = toolforge.connect('commonswiki')
    cur = conn.cursor()
    cur.execute(
        """  SELECT CAST(cl_sortkey_prefix AS INTEGER) AS gridimage_id,
                    GROUP_CONCAT(cl_from) AS page_ids
               FROM categorylinks
              WHERE cl_to = 'Images_from_Geograph_Britain_and_Ireland'
                AND cl_type = 'file'
                AND cl_sortkey_prefix <> ''
           GROUP BY cl_sortkey_prefix
             HAVING COUNT(*) > 1""")
    for row in cur:
        gridimage_id = row[0]
        print(
            "* [https://www.geograph.org.uk/photo/%d %d]" %
            (gridimage_id, gridimage_id), file=outfile)
        pageids = row[1].split(",")
        mwrequest = site.simple_request(
            action="query", pageids="|".join(pageids),
            prop="categories|imageinfo|images|links",
            clprop="sortkey", cllimit="max",
            clcategories="Category:Images from Geograph Britain and Ireland",
            iiprop="size", imlimit="max",
            plnamespace="6", pllimit="max")
        data = mwrequest.submit()
        items = sorted(data['query']['pages'].values(),
                       key=lambda i: i["categories"][0]["sortkey"])
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
                "User:Geograph Update Bot/duplicate Geograph IDs")
    reportpage.text = (
        "<!-- This page will be overwritten by Geograph Update Bot -->\n"
        "{{/header}}\n")
    reportpage.text += outfile.getvalue()
    reportpage.save("[[User:Geograph Update Bot/DUPR|Updated]] list "
                    "of duplicate IDs")

def main(*args):
    # Process global arguments to determine desired site
    local_args = pywikibot.handle_args(args)

    find_duplicates()

main()
