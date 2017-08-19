from __future__ import print_function

import hashlib
import logging
import pywikibot
from pywikibot.bot import (
    SingleSiteBot, ExistingPageBot, NoRedirectPageBot, AutomaticTWSummaryBot)
import pywikibot.pagegenerators
import re
import requests
import sqlite3
import tempfile

logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO)

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

def get_geograph_basic(gridimage_id):
    info = get_geograph_info(gridimage_id)
    r = client.get(info['url'])
    r.raise_for_status()
    return r.content

class StrangeURL(Exception):
    pass

def get_geograph_full(gridimage_id):
    info = get_geograph_info(gridimage_id)
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

def process_page(page):
    templates = page.templatesWithParams()
    geograph_templates = [t for t in templates if t[0] == geograph]
    if len(geograph_templates) == 0:
        logger.info("%s: no {{Geograph}} template", page)
        return
    if len(geograph_templates) > 1:
        logger.warning("%s: %d {{Geograph}} templates", page)
        return
    try:
        gridimage_id = int(geograph_templates[0][1][0])
    except ValueError, IndexError:
        logger.warning("%s: broken {{Geograph}} template", page)
        return
    logger.info("%s: Geograph ID is %d", page, gridimage_id)
    c = geodb.cursor()
    c.execute("""
        SELECT width, height, original_width, original_height
           FROM gridimage_size
           WHERE gridimage_id = ?
        """, (gridimage_id,))
    if c.rowcount == 0:
        logger.warning("%s: Geograph ID %d not in database",
                       page, gridimage_id)
        return
    if c.rowcount > 1:
        logger.error("Multiple database entries for Geograph ID %d",
                     gridimage_id)
        return
    gwidth, gheight, original_width, original_height = c.fetchone()
    if original_width == 0:
        logger.info("%s: No high-res version available", page)
        return
    logger.info("%s: %dx%d version available",
                page, original_width, original_height)
    fi = page.latest_file_info
    logger.info("%s: current Commons version is %dx%d",
                page, fi.width, fi.height)
    if (fi.width, fi.height) != (gwidth, gheight):
        logger.info("%s: dimensions do not match Geograph basic image", page)
        return
    gb = get_geograph_basic(gridimage_id)
    if hashlib.sha1(gb).hexdigest() != fi.sha1:
        logger.info("%s: SHA-1 does not match Geograph basic image")
    logger.info("%s: Image matches. Update possible.", page)
    newimg = get_geograph_full(gridimage_id)
    logger.info("Got %d bytes of image", len(newimg))
    tf = tempfile.NamedTemporaryFile()
    tf.write(newimg)
    logger.info("File written to %s", tf.name)
    page.upload(tf.name, comment="Higher-resolution version from Geograph",
                ignore_warnings=['exists'])

class UpgradeSizeBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):
    def __init__(self, generator, **kwargs):
        # call constructor of the super class
        super(UpgradeSizeBot, self).__init__(site=True, **kwargs)
        # assign the generator to the bot
        self.generator = generator
    def treat_page(self):
        process_page(self.current_page)

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
    if gen:
        # pass generator and private options to the bot
        bot = UpgradeSizeBot(gen, **options)
        bot.run()  # guess what it does
        return True
    else:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False
main()
