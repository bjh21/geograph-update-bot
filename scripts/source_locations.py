#! /usr/bin/python3

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
                      set_location, set_object_location, location_params,
                      MapItSettings)
from gubutil import TooManyTemplates

# Ways that Geograph locations get in:
# [✓] GeographBot (of course)
# [✓] BotMultichill
#         (File:Lacock, St Cyriac's Church - geograph.org.uk - 211699.jpg)
# [✓] DschwenBot (File:Panorama-Walsall.jpg)
# [✓] File Upload Bot (Magnus Manske)
# [✓] Geograph2commons
# [ ] Manually copied from Geograph

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
    def process_page(self, page):
        reason = None
        location_replaced = False
        location_removed = False
        object_location_added = False
        location_added = False
        creditline_added = False
        revid = page.latest_revision_id
        tree = mwparserfromhell.parse(page.text)
        try:
            old_location = get_location(tree)
        except IndexError:
            raise NotEligible("no location present")

        oldcamparam = location_params(old_location)

        bot.log("param: %s" % (repr(oldcamparam),))
        if 'source' in oldcamparam:
            raise NotEligible("location already has source")
        if old_location.name not in ('Location dec', 'location dec'):
            raise NotEligible("location using unusual template")

        firstrev = page.oldest_revision.hist_entry()
        first_tree = mwparserfromhell.parse(page.getOldVersion(firstrev.revid))
        try:
            first_location = get_location(first_tree)
        except IndexError:
            # Location added since upload.  Maybe added by DschwenBot?
            for oldrev in page.revisions():
                if oldrev.user == 'DschwenBot':
                    if (oldrev.comment == "adding missing Location data from "
                                      "www.geograph.org.uk"):
                        added_tree = mwparserfromhell.parse(
                            page.getOldVersion(oldrev.revid))
                        added_location = get_location(added_tree)
                        if old_location != added_location:
                            raise NotEligible("location changed since added")
                        reason = "added by [[User:DschwenBot]]"
            if not reason:
                raise NotEligible("location added since upload")
        else:
          if old_location == first_location:
            if (firstrev.comment in
                ("Transferred from geograph.co.uk using "
                 "[https://tools.wmflabs.org/geograph2commons/ "
                 "geograph2commons]",
                 # Some uploads have this curious typo'd version of the summary.
                 "Transferred from geograph.co.uk using "
                 "[https://tools.wmflabs.org/geograph2commons/ "
                 "grograph2commons]")):
                # Would like to check tag, but pywikibot doesn't seem to
                # expose it.
                reason = ("set at upload by "
                          "[[toollabs:geograph2commons|geograph2commons]]")
            elif (firstrev.user in
                  ("File Upload Bot (Magnus Manske)", "GeographBot")):
                reason = ("set at upload by [[User:%s|%s]]" %
                          (firstrev.user, firstrev.user))
          else:
            # Location changed since first upload.
            # This may have been BotMultichill fixing a broken upload.
            for oldrev in page.revisions():
                if oldrev.user == 'BotMultichill':
                    if (oldrev.comment == "Fixing location"):
                        fixed_tree = mwparserfromhell.parse(
                            page.getOldVersion(oldrev.revid))
                        fixed_location = get_location(fixed_tree)
                        if old_location != fixed_location:
                            raise NotEligible("location changed since fixing")
                        reason = "fixed by [[User:BotMultichill]]"
            if not reason:
                raise NotEligible("location changed since upload")
        if reason:
            try:
                paramstr = str(old_location.get(3).value)
            except ValueError:
                paramstr = ""
            if paramstr != "": paramstr += "_"
            old_location.add(3, paramstr + "source:geograph")

        newtext = str(tree)
        if newtext != page.text:
            summary = ("Mark Geograph-derived location (%s) with appropriate "
                       "\"source\" parameter" % (reason,))
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
            page.save(summary)

    def treat_page(self):
        try:
            self.process_page(self.current_page)
        except NotEligible as e:
            bot.log(str(e))
        except TooManyTemplates as e:
            bot.log(str(e))
        except MinorProblem as e:
            bot.warning(str(e))
        except MajorProblem as e:
            bot.error(str(e))

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
        if genFactory.handle_arg(arg):
            continue  # nothing to do here
    # The preloading option is responsible for downloading multiple
    # pages from the wiki simultaneously.
    gen = genFactory.getCombinedGenerator(preload=True)
    if gen:
        # pass generator and private options to the bot
        bot = UpdateMetadataBot(gen, **options)
        bot.run()  # guess what it does
        return True
    else:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False

main()
