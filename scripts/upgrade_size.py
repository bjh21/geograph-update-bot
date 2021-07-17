from __future__ import division, print_function

from itertools import zip_longest
import hashlib
import pywikibot
from pywikibot.bot import (
    SingleSiteBot, ExistingPageBot, NoRedirectPageBot, AutomaticTWSummaryBot)
import pywikibot.bot as bot
import pywikibot.comms.http as http
import pywikibot.data.api as api
import pywikibot.pagegenerators
from pywikibot.page import FilePage
import re
import sqlite3
import tempfile
from requests.exceptions import HTTPError
from urllib.parse import urlencode
import compare
from compare import compare_revisions
import mwparserfromhell

from gubutil import canonicalise_name, tlgetone, GeoGeneratorFactory

geodb = sqlite3.connect('geograph-db/geograph.sqlite3')
geodb.row_factory = sqlite3.Row

def get_geograph_info(gridimage_id):
    # Use the oEmbed API
    r = http.fetch("https://api.geograph.org.uk/api/oembed",
                   params={'url': 'https://www.geograph.org.uk/photo/%d' %
                                  gridimage_id,
                           'format': 'json'},
                   headers={'Accept': 'application/json'})
    r.raise_for_status()
    j = r.json()
    return j

def get_geograph_basic(gridimage_id, info):
    r = http.fetch(info['url'], headers={'Accept': 'image/jpeg'})
    r.raise_for_status()
    return r.content

def get_geograph_size(gridimage_id, info, size):
    url = get_geograph_size_url(gridimage_id, info, size)
    bot.log("Fetching from %s" % (url,))
    r = http.fetch(url, headers={'Accept': 'image/jpeg'})
    r.raise_for_status()
    return r.content

class StrangeURL(Exception):
    pass

def get_geograph_full_url(gridimage_id, info):
    return get_geograph_size_url(gridimage_id, info, 'original')

def get_geograph_size_url(gridimage_id, info, size):
    if size != 'original' and size <= 640:
        return info['url']
    # Evil hack, but better than digging it out of HTML.
    m = re.search(r"_([0-9a-f]{8})\.jpg$", info['url'])
    if not m:
        raise StrangeURL(info['url'])
    imgkey = m.group(1)
    bot.log("imgkey is %s" % (repr(imgkey),))
    return ("https://www.geograph.org.uk/reuse.php?" +
            urlencode({'id': gridimage_id,
                       'download': imgkey,
                       'size': size}))

def get_geograph_full(gridimage_id, info):
    url = get_geograph_full_url(gridimage_id, info)
    bot.log("Fetching from %s" % (url,))
    r = http.fetch(url, headers={'Accept': 'image/jpeg'})
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
class UploadFailed(MinorProblem):
    pass
class MajorProblem(Exception):
    pass
class BadGeographDatabase(MajorProblem):
    pass

def whynot_setup():
    global whynot_db
    whynot_db = sqlite3.connect('whynot.sqlite3')
    whynot_db.execute("""CREATE TABLE IF NOT EXISTS whynot
                         (last_checked DATE DEFAULT (date('now')),
                          gridimage_id INTEGER PRIMARY KEY,
                          whynot TEXT)""")

def whynot(gridimage_id, message):
    whynot_db.execute("""INSERT OR REPLACE INTO whynot (gridimage_id, whynot)
                                         VALUES (?, ?)""",
                      (gridimage_id, message))
    whynot_db.commit()

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
        tree = mwparserfromhell.parse(page.text)
        try:
            geograph_template = tlgetone(tree, ['Geograph'])
        except IndexError:
            raise NotEligible("No {{Geograph}} template")
        try:
            gridimage_id = int(str(geograph_template.get(1).value))
            commons_author = str(geograph_template.get(2).value)
        except ValueError:
            raise BadTemplate("broken {{Geograph}} template")
        except IndexError:
            raise BadTemplate("broken {{Geograph}} template")
        bot.log("Geograph ID is %d" % (gridimage_id,))
        c = geodb.cursor()
        c.execute("""
            SELECT * FROM gridimage_base NATURAL JOIN gridimage_size
               WHERE gridimage_id = ?
            """, (gridimage_id,))
        row = c.fetchone()
        if row == None:
            raise NotInGeographDatabase("Geograph ID %d not in database" %
                                        (gridimage_id,))
        gwidth, gheight, original_width, original_height, original_diff = [
            row[x] for x in ('width', 'height', 'original_width',
                             'original_height', 'original_diff')]
        if original_width == 0:
            raise NotEligible("no high-res version available")
        fi = page.latest_file_info
        bot.log("%d × %d version available" % (original_width, original_height))
        bot.log("current Commons version is %d × %d" % (fi.width, fi.height))
        if fi.width >= original_width and fi.height >= original_height:
            raise NotEligible("no higher-resolution version on Geograph")
        if not aspect_ratios_match(fi.width, fi.height,
                                   original_width, original_height):
            raise NotEligible("aspect ratios of images differ")
        if (fi.width, fi.height) == (gwidth, gheight):
            if original_diff == 'yes':
                raise NotEligible("Geograph says pictures are different")
        else:
            if max(fi.width, fi.height) not in (800, 1024):
                raise NotEligible("dimensions do not match any Geograph image")
        for ofi in page.get_file_history().values():
            if ofi.user == "Geograph Update Bot":
                raise NotEligible("file already uploaded by me")
        geograph_info = get_geograph_info(gridimage_id)
        if (canonicalise_name(geograph_info['author_name']) !=
            canonicalise_name(commons_author)):
            raise NotEligible("author does not match Geograph (%s vs. %s)" %
                              (repr(commons_author),
                               repr(geograph_info['author_name'])))
        try:
            credit_line = tlgetone(tree, ['Credit line'])
        except IndexError:
            pass
        else:
            commons_title = ''.join([
                str(x) for x in
                credit_line.get('Other').value.filter_text()]).strip()
            bot.log("Title on Commons: %s" % (commons_title,))
            if (canonicalise_name(commons_title) !=
                canonicalise_name(geograph_info['title'])):
                raise NotEligible("title does not match Geograph (%s vs. %s)" %
                                  (repr(commons_title),
                                   repr(geograph_info['title'])))
        geograph_image = get_geograph_size(gridimage_id, geograph_info,
                                           max(fi.width, fi.height))
        if hashlib.sha1(geograph_image).hexdigest() != fi.sha1:
            raise NotEligible("SHA-1 does not match Geograph %d px image." %
                              ( max(fi.width, fi.height),))
        bot.log("Image matches. Update possible.")
        self.replace_file(page, get_geograph_full_url(gridimage_id,
                                                      geograph_info))
        compare_revisions(self.site, parameters=dict(titles=page.title()))
    def replace_file(self, page, newurl):
        bot.log("Uploading from %s" % (newurl,))
        success = page.upload(newurl, 
                              comment="[[User:Geograph Update Bot/RES|"
                              "Higher-resolution version]] from Geograph",
                        ignore_warnings=['exists'])
        if not success:
            raise UploadFailed("upload from %s to %s failed" % (newurl, page))
        return

    def treat_page(self):
        try:
            gridimage_id = -1
            if hasattr(self.current_page, 'gridimage_id'):
                gridimage_id = self.current_page.gridimage_id
            if self.current_page.namespace() != 6:
                return # Not a file page
            self.process_page(FilePage(self.current_page))
        except NotEligible as e:
            whynot(gridimage_id, str(e))
            bot.log(str(e))
        except MinorProblem as e:
            whynot(gridimage_id, str(e))
            bot.warning(str(e))
        except MajorProblem as e:
            whynot(gridimage_id, str(e))
            bot.error(str(e))
        except HTTPError as e:
            whynot(gridimage_id, str(e))
            bot.error(str(e))

def InterestingGeographsByNumber(**kwargs):
    site = kwargs['site']
    # Fetch starting ID from a special page.
    startpage = pywikibot.Page(site, 'User:Geograph Update Bot/last ID')
    start = int(startpage.text)
    startsortkeyprefix=" %08d" % (start,)
    n = 0
    g = api.QueryGenerator(parameters=dict(
        generator="categorymembers",
        gcmtitle="Category:Images from Geograph Britain and Ireland",
        gcmtype="file", gcmstartsortkeyprefix=startsortkeyprefix,
        prop="categories|imageinfo", cllimit="max", clprop="sortkey",
        clcategories="Category:Images from Geograph Britain and Ireland",
        iiprop="size"), **kwargs)
    for page in InterestingGeographGenerator(site, g):
        yield page
        n = n + 1;
        if (n % 50 == 0):
            # Write a checkpoint every fifty yielded items
            startpage.text = str(page.gridimage_id)
            startpage.save("Checkpoint: up to %d" % (page.gridimage_id,))

def InterestingGeographsByDate(**kwargs):
    site = kwargs['site']
    g = api.QueryGenerator(parameters=dict(
        generator="categorymembers",
        gcmtitle="Category:Images from Geograph Britain and Ireland",
        gcmtype="file",
        gcmsort="timestamp", gcmdir="older",
        prop="categories|imageinfo", cllimit="max", clprop="sortkey",
        clcategories="Category:Images from Geograph Britain and Ireland",
        iiprop="size"), **kwargs)
    yield from InterestingGeographGenerator(site, g)

def InterestingGeographGenerator(site, g):
    for item in g:
        bot.log(repr(item))
        try:
            # We only request a single category, and every file we get
            # is guaranteed to be a member of it, so the "[0]" here
            # should be safe.
            gridimage_id = int(item['categories'][0]['sortkeyprefix'])
        except (ValueError):
            # Unparseable sort key.  Skip it.
            continue
        try:
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
                raise NotEligible("no high-res version available")
            if not aspect_ratios_match(basic_width, basic_height,
                                       original_width, original_height):
                raise NotEligible("aspect ratios of images differ")
            ii = item['imageinfo'][0]
            if ((ii['width'], ii['height']) ==
                (original_width, original_height)):
                # We already have the full-resolution version.
                raise NotEligible("high-res version already uploaded")
        except NotEligible as e:
            whynot(gridimage_id, str(e))
            continue
        except Exception:
            pass # Anything odd happens, yield the item for further inspection.
        page = pywikibot.FilePage(site, item['title'])
        page.gridimage_id = gridimage_id
        yield page
        
def main(*args):
    options = {}
    # Process global arguments to determine desired site
    local_args = pywikibot.handle_args(args)

    # This factory is responsible for processing command line arguments
    # that are also used by other scripts and that determine on which pages
    # to work on.
    genFactory = GeoGeneratorFactory()

    gen = None
    # Parse command line arguments
    for arg in local_args:

        # Catch the pywikibot.pagegenerators options
        if genFactory.handle_arg(arg):
            continue  # nothing to do here
        if arg == '-bynumber':
            gen = InterestingGeographsByNumber(site=pywikibot.Site())
    # The preloading option is responsible for downloading multiple
    # pages from the wiki simultaneously.
    if not gen:
        gen = genFactory.getCombinedGenerator(preload=True)
    if not gen:
        gen = InterestingGeographsByDate(site=pywikibot.Site())
    if gen:
        whynot_setup()
        # pass generator and private options to the bot
        bot = UpgradeSizeBot(gen, **options)
        bot.run()  # guess what it does
        return True
    else:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False

main()
