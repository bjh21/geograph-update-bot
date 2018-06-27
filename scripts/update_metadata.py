from __future__ import division, print_function

import pywikibot
from pywikibot.bot import (
    SingleSiteBot, ExistingPageBot, NoRedirectPageBot, AutomaticTWSummaryBot)
import pywikibot.bot as bot
import pywikibot.data.api as api
import pywikibot.pagegenerators
from pywikibot.pagegenerators import PreloadingGenerator
from datetime import datetime, timezone
from dateutil.tz import gettz
from math import copysign
import mwparserfromhell
import re
import sqlite3
from creditline import creditline_from_row, can_add_creditline, add_creditline
from location import (location_from_row, object_location_from_row,
                      az_dist_between_locations, format_row,
                      format_direction, get_location, get_object_location,
                      set_location, set_object_location, location_params)

from gubutil import get_gridimage_id, TooManyTemplates, tlgetone

# Ways that Geograph locations get in:
# BotMultichill (example?)
# DschwenBot (File:Panorama-Walsall.jpg)
# File Upload Bot (Magnus Manske)
# Geograph2commons

geodb = sqlite3.connect('../geograph-db/geograph.sqlite3')
geodb.row_factory = sqlite3.Row

class NotEligible(Exception):
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

class UpdateMetadataBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):
    def __init__(self, generator, **kwargs):
        # call constructor of the super class
        super(UpdateMetadataBot, self).__init__(site=True, **kwargs)
        # assign the generator to the bot
        self.generator = generator
    def unmodified_on_geograph_since_upload(self, page, row):
        commons_dt = page.oldest_revision.full_hist_entry().timestamp
        # For some reason, pywikibot.Timestamps aren't timezone-aware.
        commons_dt = commons_dt.replace(tzinfo=timezone.utc)
        geograph_date = row['upd_timestamp']
        geograph_dt = (
            datetime.strptime(geograph_date, "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=gettz("Europe/London")))
        bot.log("Commons timestamp: %s; Geograph timestamp: %s" %
                (commons_dt, geograph_dt))
        return geograph_dt < commons_dt
    def process_page(self, page):
        location_replaced = False
        location_removed = False
        object_location_added = False
        creditline_added = False
        revid = page.latest_revision_id
        tree = mwparserfromhell.parse(page.text)
        gridimage_id = get_gridimage_id(tree)
        c = geodb.cursor()
        c.execute("""
            SELECT * FROM gridimage_base NATURAL JOIN gridimage_geo
                          NATURAL JOIN gridimage_extra
               WHERE gridimage_id = ?
            """, (gridimage_id,))
        row = c.fetchone()
        if row == None:
            raise NotInGeographDatabase("Geograph ID %d not in database" %
                                        (gridimage_id,))
        try:
            old_location = get_location(tree)
        except IndexError:
            old_location = None
        try:
            old_object_location = get_object_location(tree)
        except IndexError:
            old_object_location = None
        new_location = location_from_row(row)
        minor = True
        bot.log("Old: %s" % (old_location,))
        bot.log("Old: %s" % (old_object_location,))
        oldcamparam = location_params(old_location)
        oldobjparam = location_params(old_object_location)
        creditline = creditline_from_row(row)
        if (can_add_creditline(tree, creditline) and
            self.unmodified_on_geograph_since_upload(page, row)):
            add_creditline(tree, creditline)
            creditline_added = True
            minor = False
        else:
            bot.log("Cannot add credit line")
        newtext = str(tree)
        if newtext != page.text:
            summary = ""
            if creditline_added:
                if summary == "":
                    summary = "Add credit line with title from Geograph"
                else:
                    summary += "; add credit line with title from Geograph"
            bot.log("edit summary: %s" % (summary,))
            # Before we save, make sure pywikibot's view of the latest
            # revision hasn't changed.  If it has, that invalidates
            # our parse tree, and we need to start again.
            if page.latest_revision_id != revid:
                bot.log("page has changed (%d != %d): restarting edit" %
                        (page.latest_revision_id, revid))
                self.process_page(page)
                return
            page.text = newtext
            page.save(summary, minor=minor)

    def treat_page(self):
        try:
            self.process_page(self.current_page)
        except NotEligible as e:
            bot.log(str(e))
        except MinorProblem as e:
            bot.warning(str(e))
        except MajorProblem as e:
            bot.error(str(e))
        except TooManyTemplates as e:
            bot.error(str(e))


def GeographBotUploads(parameters = None, **kwargs):
    if parameters == None: parameters = { }
    parameters['gaiuser'] = 'GeographBot'
    parameters['gaisort'] = 'timestamp'
    print(parameters)
    return api.PageGenerator("allimages", parameters=parameters, **kwargs)
        
def main(*args):
    options = {}
    # Process global arguments to determine desired site
    local_args = pywikibot.handle_args(args)

    # This factory is responsible for processing command line arguments
    # that are also used by other scripts and that determine on which pages
    # to work on.
    genFactory = pywikibot.pagegenerators.GeneratorFactory()

    extraparams = { }
    # Parse command line arguments
    for arg in local_args:

        # Catch the pywikibot.pagegenerators options
        if genFactory.handleArg(arg):
            continue  # nothing to do here
        if arg.startswith("-aistart:"):
            extraparams = { 'gaistart': arg[9:] }
    # The preloading option is responsible for downloading multiple
    # pages from the wiki simultaneously.
    gen = genFactory.getCombinedGenerator(preload=True)
    if not gen:
        gen = PreloadingGenerator(GeographBotUploads(site=pywikibot.Site(),
                                                     parameters=extraparams))
    if gen:
        # pass generator and private options to the bot
        bot = UpdateMetadataBot(gen, **options)
        bot.run()  # guess what it does
        return True
    else:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False

main()
