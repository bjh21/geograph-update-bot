from __future__ import print_function

from io import StringIO
import pywikibot
import pywikibot.bot as bot
import pywikibot.data.api as api
import pywikibot.pagegenerators

def find_duplicates():
    last_id = dup_id = -1
    outfile = StringIO()
    site = pywikibot.Site()
    for item in api.ListGenerator("categorymembers", site=site,
            cmtitle="Category:Images from Geograph Britain and Ireland",
            cmprop="title|sortkeyprefix", cmtype="file"):
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
    reportpage = pywikibot.Page(site,
                "User:Geograph Update Bot/duplicate Geograph IDs/data")
    reportpage.text = (
        "<!-- This page will be overwritten by Geograph Update Bot -->")
    reportpage.text += outfile.getvalue()
    reportpage.save("New list of duplicate IDs")

def main(*args):
    # Process global arguments to determine desired site
    local_args = pywikibot.handle_args(args)

    find_duplicates()

main()
