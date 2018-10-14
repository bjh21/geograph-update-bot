from __future__ import division, print_function

import pywikibot
from pywikibot.bot import (
    SingleSiteBot, ExistingPageBot, NoRedirectPageBot, AutomaticTWSummaryBot)
import pywikibot.bot as bot
import pywikibot.data.api as api
import pywikibot.pagegenerators
from pywikibot.pagegenerators import PreloadingGenerator
from datetime import datetime, timedelta, timezone
from dateutil.tz import gettz
from itertools import chain
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

from gubutil import (
    get_gridimage_id, TooManyTemplates, tlgetone, NewGeographImages,
    GeographBotUploads, ModifiedGeographs)

# Ways that Geograph locations get in:
# BotMultichill (example?)
# DschwenBot (File:Panorama-Walsall.jpg)
# File Upload Bot (Magnus Manske)
# Geograph2commons

geodb = sqlite3.connect('geograph-db/geograph.sqlite3')
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
    def should_set_location(self, old_template, new_template, desc):
        oldparam = location_params(old_template)
        newparam = location_params(new_template)
        # We generally want to synchronise with Geograph.
        should_set = True
        # but not yet if old template has no gridref
        if (old_template != None and new_template != None
            and '-' not in oldparam['source']):
            if old_template.has(4):
                should_set = False
                bot.log("%s template is DMS with no gridref: not updating" %
                        (desc.capitalize(),))
            else:
                (azon, azno, dist) = az_dist_between_locations(
                    old_template, new_template)
                if dist < int(str(new_template.get('prec').value)):
                    bot.log("%s has only moved by %d m: not updating"
                            % (desc.capitalize(), dist))
                    should_set = False
        # and not if gridref hasn't changed
        if (old_template != None and new_template != None
            and oldparam['source'] == newparam['source']):
            should_set = False
            bot.log("%s gridref unchanged: not updating" %
                    (desc.capitalize(),))
        return should_set
    def describe_move(self, old_template, new_template):
        azon, azno, distance = (
            az_dist_between_locations(old_template, new_template))
        return "moved %.1f m %s" % (distance, format_direction(azon))
    def process_page(self, page):
        location_added = False
        location_replaced = False
        location_removed = False
        object_location_added = False
        object_location_replaced = False
        object_location_removed = False
        creditline_added = False
        revid = page.latest_revision_id
        tree = mwparserfromhell.parse(page.text)
        try:
            gridimage_id = get_gridimage_id(tree)
        except ValueError as e:
            raise BadTemplate(str(e))
            
        mapit = MapItSettings()
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
        minor = False # May need fixing
        bot.log("Old cam: %s" % (old_location,))
        bot.log("Old obj: %s" % (old_object_location,))
        if old_location == None and old_object_location == None:
            minor = False
            mapit.allowed = True
            # No geocoding at all: add from Geograph
            new_location = location_from_row(row, mapit=mapit)
            new_object_location = object_location_from_row(row, mapit=mapit)
            if new_location and new_location.get('prec').value != '1000':
                set_location(tree, new_location)
                location_added = True
            set_object_location(tree, new_object_location)
            object_location_added = True
        else:
            oldcamparam = location_params(old_location)
            oldobjparam = location_params(old_object_location)
            if ((old_location == None or
                 re.match(r'^geograph(-|$)', oldcamparam.get('source',''))) and
                (old_object_location == None or
                 re.match(r'^geograph(-|$)', oldobjparam.get('source','')))):
                bot.log("Old geocoding is from Geograph")
                # Existing geocoding all from Geograph, so updating
                # from Geograph OK if needed.
                new_location = location_from_row(row, mapit=mapit)
                new_object_location = object_location_from_row(row, mapit=mapit)
                # Should we update locations?
                should_set_cam = self.should_set_location(
                    old_location, new_location, "camera")
                should_set_obj = self.should_set_location(
                    old_object_location, new_object_location, "object")
                # Do it if necessary:
                mapit.allowed = True
                if should_set_cam:
                    set_location(tree, location_from_row(row, mapit=mapit))
                    if old_location == None:
                        if new_location != None:
                            location_added = True
                    else:
                        if new_location == None:
                            location_removed = True
                        else:
                            location_replaced = True
                if should_set_obj:
                    set_object_location(tree,
                                    object_location_from_row(row, mapit=mapit))
                    if old_object_location == None:
                        if new_object_location != None:
                            object_location_added = True
                    else:
                        if new_object_location == None:
                            object_location_removed = True
                        else:
                            object_location_replaced = True
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
            if location_added:
                if object_location_added:
                    summary = (
                        "Add camera and object locations from Geograph (%s)" %
                        (format_row(row),))
                elif object_location_replaced:
                    summary = (
                        "Add camera location and update object location (%s), "
                        "both from Geograph (%s)" %
                        (self.describe_move(old_object_location,
                                            new_object_location),
                         format_row(row)))
                elif object_location_removed:
                    summary = (
                        "Add camera location from Geograph (%s) "
                        "and remove Geograph-derived 1km-precision "
                        "object location" %
                        (format_row(row),))                    
                else:
                    summary = ("Add camera location from Geograph (%s)" %
                               (format_row(row),))
            elif location_replaced:
                if object_location_added:
                    summary = (
                        "Update camera location (%s) and add object location, "
                        "both from Geograph (%s)" %
                        (self.describe_move(old_location, new_location),
                         format_row(row)))
                elif object_location_replaced:
                    summary = (
                        "Update camera and object locations "
                        "(%s and %s, respectively) "
                        "from Geograph (%s)" %
                        (self.describe_move(old_location, new_location),
                         self.describe_move(old_object_location,
                                            new_object_location),
                         format_row(row)))
                elif object_location_removed:
                    summary = (
                        "Update camera location (%s) from Geograph (%s) "
                        "and remove Geograph-derived 1km-precision "
                        "object location" %
                        (self.describe_move(old_location, new_location),
                         format_row(row)))
                else:
                    summary = (
                        "Update camera location (%s) from Geograph (%s)" %
                        (self.describe_move(old_location, new_location),
                         format_row(row)))
            elif location_removed:
                if object_location_added:
                    summary = (
                        "Remove Geograph-derived camera location "
                        "(no longer on Geograph, or 1km precision) "
                        "and add object location from Geograph (%s)" %
                        (format_row(row),))
                elif object_location_replaced:
                    summary = (
                        "Remove Geograph-derived camera location "
                        "(no longer on Geograph, or 1km precision) "
                        "and update object location (%s) from Geograph (%s)" %
                        (self.describe_move(old_object_location,
                                            new_object_location),
                         format_row(row)))
                else:
                    summary = (
                        "Remove Geograph-derived camera location "
                        "(no longer on Geograph, or 1km precision)")
            elif object_location_added:
                summary = (
                    "Add object location from Geograph (%s)" %
                    (format_row(row),))
            elif object_location_replaced:
                summary = ("Update object location (%s) from Geograph (%s)" %
                           (self.describe_move(old_object_location,
                                               new_object_location),
                            format_row(row)))
            elif object_location_removed:
                summary = ("Remove Geograph-derived 1km-precision "
                           "object location")
            if creditline_added:
                if summary == "":
                    summary = "Add credit line with title from Geograph"
                else:
                    summary += "; add credit line with title from Geograph"
            if mapit.used:
                # Requested credit where MapIt is used:
                # 'Please attribute us with the text “Powered by Mapit”
                # and a link back to the MapIt front page.'
                summary += (
                    " [powered by MapIt: http://global.mapit.mysociety.org]")
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

class GeoGeneratorFactory(pywikibot.pagegenerators.GeneratorFactory):
    def _handle_recent(self, value):
        starttime = datetime.now(timezone.utc) - timedelta(days=int(value))
        earlystart = starttime - timedelta(days=1)
        extraparams = { 'gcmend': earlystart.astimezone(timezone.utc) }
        new_on_commons = PreloadingGenerator(
            NewGeographImages(site=pywikibot.Site(), parameters=extraparams))
        changed_on_geograph = ModifiedGeographs(
            modified_since = starttime, submitted_before = earlystart)
        return chain(new_on_commons, changed_on_geograph)
            
def main(*args):
    options = {}
    # Process global arguments to determine desired site
    local_args = pywikibot.handle_args(args)

    # This factory is responsible for processing command line arguments
    # that are also used by other scripts and that determine on which pages
    # to work on.
    genFactory = GeoGeneratorFactory()

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
        gen = PreloadingGenerator(NewGeographImages(site=pywikibot.Site(),
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
