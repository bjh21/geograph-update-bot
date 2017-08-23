from __future__ import print_function

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

site = pywikibot.Site()

geograph = pywikibot.Page(site, "Template:Geograph")

geodb = sqlite3.connect('../geograph-db/geograph.sqlite3')

client = requests.Session()
client.headers['User-Agent'] = "upgrade_size (bjh21@bjh21.me.uk)"

def get_geograph_info(gridimage_id):
    # Use the oEmbed API
    r = client.get("http://api.geograph.org.uk/api/oembed",
                     params={'url': 'http://www.geograph.org.uk/photo/%d' %
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

def get_geograph_full(gridimage_id, info):
    # Evil hack, but better than digging it out of HTML.
    m = re.search(r"_([0-9a-f]{8})\.jpg$", info['url'])
    if not m:
        raise StrangeURL(info['url'])
    imgkey = m.groups(1)
    r = client.get("http://www.geograph.org.uk/reuse.php",
                     params={'id': gridimage_id, 'download': imgkey,
                             'size': 'original'})
    r.raise_for_status()
    return r.content

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

def process_page(page):
    templates = page.templatesWithParams()
    geograph_templates = [t for t in templates if t[0] == geograph]
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
    if original_width == 0:
        raise NotEligible("No high-res version available")
    bot.log("%dx%d version available" % (original_width, original_height))
    fi = page.latest_file_info
    bot.log("current Commons version is %dx%d" % (fi.width, fi.height))
    if (fi.width, fi.height) != (gwidth, gheight):
        raise NotEligible("dimensions do not match Geograph basic image")
    geograph_info = get_geograph_info(gridimage_id)
    if geograph_info['author_name'] != commons_author:
        raise NotEligible("author does not match Geograph")
    basic_image = get_geograph_basic(gridimage_id, geograph_info)
    if hashlib.sha1(basic_image).hexdigest() != fi.sha1:
        raise NotEligible("SHA-1 does not match Geograph basic image.")
    bot.log("Image matches. Update possible.")
    newimg = get_geograph_full(gridimage_id, geograph_info)
    bot.log("Got %d bytes of image" % (len(newimg),))
    tf = tempfile.NamedTemporaryFile()
    tf.write(newimg)
    bot.log("File written to %s" % (tf.name,))
    page.upload(tf.name, comment="Higher-resolution version from Geograph",
                ignore_warnings=['exists'])

class UpgradeSizeBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):
    def __init__(self, generator, **kwargs):
        # call constructor of the super class
        super(UpgradeSizeBot, self).__init__(site=True, **kwargs)
        # assign the generator to the bot
        self.generator = generator
    def treat_page(self):
        try:
            process_page(self.current_page)
        except NotEligible as e:
            bot.log(str(e))
        except MinorProblem as e:
            bot.warning(str(e))
        except MajorProblem as e:
            bot.error(str(e))

def InterestingGeographGenerator(**kwargs):
    for item in api.ListGenerator("categorymembers",
            cmtitle="Category:Images from the Geograph British Isles project",
            cmprop="title|sortkeyprefix", cmtype="file", **kwargs):
        try:
            gridimage_id = int(item['sortkeyprefix'])
            c = geodb.cursor()
            c.execute("""
                SELECT width, height, original_width, original_height
                    FROM gridimage_size
                    WHERE gridimage_id = ?
                """, (gridimage_id,))
            if c.rowcount == 0:
                raise NotInGeographDatabase("Geograph ID %d not in database" %
                                            (gridimage_id,))
            if c.rowcount > 1:
                raise BadGeographDatabase(
                    "Multiple database entries for Geograph ID %d" %
                    (gridimage_id,))
            (basic_width, basic_height,
             original_width, original_height) = c.fetchone()
            if original_width == 0:
                # No high-res version available.
                continue
        except Exception:
            pass # Anything odd happens, yield the item for further inspection.
        yield pywikibot.FilePage(site, item['title'])
    
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
