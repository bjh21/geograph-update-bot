from __future__ import division, print_function

from itertools import zip_longest
import hashlib
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
from requests.exceptions import HTTPError
from urllib.parse import urlencode
from compare import compare_revisions

geodb = sqlite3.connect('../geograph-db/geograph.sqlite3')

client = requests.Session()
client.headers['User-Agent'] = "upgrade_size (bjh21@bjh21.me.uk)"

def get_geograph_info(gridimage_id):
    # Use the oEmbed API
    r = client.get("https://api.geograph.org.uk/api/oembed",
                     params={'url': 'https://www.geograph.org.uk/photo/%d' %
                                    gridimage_id,
                             'format': 'json'})
    r.raise_for_status()
    j = r.json()
    return j

def get_geograph_basic(gridimage_id, info):
    r = client.get(info['url'])
    r.raise_for_status()
    return r.content

class StrangeURL(Exception):
    pass

def get_geograph_full_url(gridimage_id, info):
    # Evil hack, but better than digging it out of HTML.
    m = re.search(r"_([0-9a-f]{8})\.jpg$", info['url'])
    if not m:
        raise StrangeURL(info['url'])
    imgkey = m.group(1)
    bot.log("imgkey is %s" % (repr(imgkey),))
    return ("https://www.geograph.org.uk/reuse.php?" +
            urlencode({'id': gridimage_id,
                       'download': imgkey,
                       'size': 'original'}))

def get_geograph_full(gridimage_id, info):
    url = get_geograph_full_url(gridimage_id, info)
    bot.log("Fetching from %s" % (url,))
    r = client.get(url)
    r.raise_for_status()
    return r.content

def aspect_ratios_match(w0, h0, w1, h1):
    # Treat aspect ratios as matching if they are within 1%
    # (allowing for possible rotation).
    return (0.99 < (w0/h0) / (w1/h1) < 1.01 or
            0.99 < (w0/h0) / (h1/w1) < 1.01)

class NotEligible(Exception):
    "This file is not eligible for resolution upgrade."
    pass
class MinorProblem(Exception):
    pass
class BadTemplate(MinorProblem):
    pass
class NotInGeographDatabase(MinorProblem):
    pass
class MajorProblem(Exception):
    pass
class BadGeographDatabase(MajorProblem):
    pass

class UpgradeSizeBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):
    def __init__(self, generator, **kwargs):
        # call constructor of the super class
        super(UpgradeSizeBot, self).__init__(site=True, **kwargs)
        # assign the generator to the bot
        self.generator = generator
        self.geograph = pywikibot.Page(self.site, "Template:Geograph")
    def process_page(self, page):
        if not page.botMayEdit():
            raise NotEligible("bot forbidden from editing this page")
        for fi in page.get_file_history().values():
            if fi.user == "Geograph Update Bot":
                raise NotEligible("file already uploaded by me")
        templates = page.templatesWithParams()
        geograph_templates = [t for t in templates if t[0] == self.geograph]
        if len(geograph_templates) == 0:
            raise NotEligible("no {{Geograph}} template")
        if len(geograph_templates) > 1:
            raise BadTemplate("%d {{Geograph}} templates" %
                              (len(geograph_templates),))
        try:
            gridimage_id = int(geograph_templates[0][1][0])
            commons_author = geograph_templates[0][1][1]
        except ValueError:
            raise BadTemplate("broken {{Geograph}} template")
        except IndexError:
            raise BadTemplate("broken {{Geograph}} template")
        bot.log("Geograph ID is %d" % (gridimage_id,))
        c = geodb.cursor()
        c.execute("""
            SELECT width, height, original_width, original_height
               FROM gridimage_size
               WHERE gridimage_id = ?
            """, (gridimage_id,))
        row = c.fetchone()
        if row == None:
            raise NotInGeographDatabase("Geograph ID %d not in database" %
                                        (gridimage_id,))
        gwidth, gheight, original_width, original_height = row
        if not aspect_ratios_match(gwidth, gheight,
                                   original_width, original_height):
            raise NotEligible("aspect ratios of images differ")
        bot.log("%d × %d version available" % (original_width, original_height))
        fi = page.latest_file_info
        bot.log("current Commons version is %d × %d" % (fi.width, fi.height))
        if (fi.width, fi.height) != (gwidth, gheight):
            raise NotEligible("dimensions do not match Geograph basic image")
        geograph_info = get_geograph_info(gridimage_id)
        if geograph_info['author_name'] != commons_author:
            raise NotEligible("author does not match Geograph (%s vs. %s)" %
                              (repr(commons_author),
                               repr(geograph_info['author_name'])))
        basic_image = get_geograph_basic(gridimage_id, geograph_info)
        if hashlib.sha1(basic_image).hexdigest() != fi.sha1:
            raise NotEligible("SHA-1 does not match Geograph basic image.")
        bot.log("Image matches. Update possible.")
        self.replace_file(page, get_geograph_full_url(gridimage_id,
                                                      geograph_info))
        compare_revisions(self.site, parameters=dict(titles=page.title()))
    def replace_file(self, page, newurl):
        bot.log("Uploading from %s" % (newurl,))
        success = page.upload(newurl, 
                        comment="Higher-resolution version from Geograph.",
                        ignore_warnings=['exists'])
        if not success:
            bot.warning("upload from %s to %s failed" % (newurl, page))
        return
    def replace_file_indirect(self, page, newurl):
        bot.log("Fetching from %s" % (newurl,))
        r = client.get(newurl)
        r.raise_for_status()
        newimg = r.content
        bot.log("Got %d bytes of image" % (len(newimg),))
        tf = tempfile.NamedTemporaryFile()
        tf.write(newimg)
        tf.flush()
        bot.log("File written to %s" % (tf.name,))
        page.upload(tf.name, comment="Higher-resolution version from Geograph.",
                    ignore_warnings=['exists'])

    def treat_page(self):
        try:
            self.process_page(self.current_page)
        except NotEligible as e:
            bot.log(str(e))
        except MinorProblem as e:
            bot.warning(str(e))
        except MajorProblem as e:
            bot.error(str(e))
        except HTTPError as e:
            bot.error(str(e))

def merge_generators(*gens):
    pendings = [{} for _ in gens]
    for items in zip_longest(*gens):
        for i, item in enumerate(items):
            if item == None: continue
            key = item['title']
            pendings[i][key] = item
            if all([key in pending for pending in pendings]):
                ret = { }
                for pending in pendings:
                    ret.update(pending[key])
                    del pending[key]
                yield ret

def InterestingGeographGenerator(**kwargs):
    site = kwargs['site']
    # Fetch starting ID from a special page.
    startpage = pywikibot.Page(site, 'User:Geograph Update Bot/last ID')
    start = int(startpage.text)
    startsortkeyprefix=" %08d" % (start,)
    n = 0
    g0 = api.ListGenerator("categorymembers", parameters=dict(
            cmtitle="Category:Images from the Geograph British Isles project",
            cmprop="title|sortkeyprefix", cmtype="file",
            cmstartsortkeyprefix=startsortkeyprefix), **kwargs)
    g1 = api.QueryGenerator(parameters=dict(
        generator="categorymembers",
        gcmtitle="Category:Images from the Geograph British Isles project",
        gcmtype="file", gcmstartsortkeyprefix=startsortkeyprefix,
        prop="imageinfo", iiprop="size", **kwargs))
    for item in merge_generators(g0, g1):
        try:
            gridimage_id = int(item['sortkeyprefix'])
            c = geodb.cursor()
            c.execute("""
                SELECT width, height, original_width, original_height
                    FROM gridimage_size
                    WHERE gridimage_id = ?
                """, (gridimage_id,))
            row = c.fetchone()
            if row == None:
                raise NotInGeographDatabase("Geograph ID %d not in database" %
                                            (gridimage_id,))
            (basic_width, basic_height, original_width, original_height) = row
            if original_width == 0:
                # No high-res version available.
                continue
            if not aspect_ratios_match(basic_width, basic_height,
                                       original_width, original_height):
                continue
            ii = item['imageinfo'][0]
            if ((ii['width'], ii['height']) ==
                (original_width, original_height)):
                # We already have the full-resolution version.
                continue
        except Exception:
            pass # Anything odd happens, yield the item for further inspection.
        yield pywikibot.FilePage(site, item['title'])
        n = n + 1;
        if (n % 50 == 0):
            # Write a checkpoint every fifty yielded items
            startpage.text = str(gridimage_id)
            startpage.save("Checkpoint: up to %d" % (gridimage_id,))

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
    # The preloading option is responsible for downloading multiple
    # pages from the wiki simultaneously.
    gen = genFactory.getCombinedGenerator(preload=True)
    if not gen:
        gen = InterestingGeographGenerator(site=pywikibot.Site())
    if gen:
        # pass generator and private options to the bot
        bot = UpgradeSizeBot(gen, **options)
        bot.run()  # guess what it does
        return True
    else:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False
main()
