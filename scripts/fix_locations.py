from __future__ import division, print_function

import pywikibot
from pywikibot.bot import (
    SingleSiteBot, ExistingPageBot, NoRedirectPageBot, AutomaticTWSummaryBot)
import pywikibot.bot as bot
import pywikibot.data.api as api
import pywikibot.pagegenerators
from pywikibot.pagegenerators import PreloadingGenerator
from math import copysign
import mwparserfromhell
import re
import sqlite3
from creditline import creditline_from_row, can_add_creditline, add_creditline
from location import (location_from_row, object_location_from_row,
                      az_dist_between_locations, format_row,
                      format_direction, get_location, has_object_location,
                      set_location, set_object_location)

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

class FixLocationBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):
    def __init__(self, generator, **kwargs):
        # call constructor of the super class
        super(FixLocationBot, self).__init__(site=True, **kwargs)
        # assign the generator to the bot
        self.generator = generator
    def get_template(self, tree, templatename):
        templates = tree.filter_templates(matches=
                                          lambda x: x.name == templatename)
        if len(templates) == 0:
            raise NotEligible("no {{%s}} template" % (templatename,))
        if len(templates) > 1:
            raise BadTemplate("%d {{%s}} templates" %
                              (len(templates), templatename))
        return templates[0]
    def gridimage_id_from_tree(self, tree):
        geograph_template = self.get_template(tree, "Geograph")
        try:
            gridimage_id = int(str(geograph_template.get(1)))
        except ValueError:
            raise BadTemplate("broken {{Geograph}} template")
        except IndexError:
            raise BadTemplate("broken {{Geograph}} template")
        bot.log("Geograph ID is %d" % (gridimage_id,))
        return gridimage_id
    def is_geographbot_upload(self, page):
        firstrev = page.oldest_revision.full_hist_entry()
        return firstrev.user == 'GeographBot'
    def get_original_tree(self, page):
        firstrev = page.oldest_revision.full_hist_entry()
        first_text = page.getOldVersion(firstrev.revid)
        return mwparserfromhell.parse(first_text)        
    def is_original_location(self, page, location_template):
        first_tree = self.get_original_tree(page)
        try:
            first_location = get_location(first_tree)
        except IndexError:
            return False # Can't be original if there's no original
        if location_template == first_location:
            bot.log("Location identical to original")
            return True
        try:
            lat = float(str(first_location.get(1)))
            lon = float(str(first_location.get(2)))
        except ValueError:
            return False # Can't do arithmetic on this
        def possible_roundings(orig):
            # Try rounding to 3, 4, and five d.p., both rounding
            # towards zero and rounding to nearest.  Our aim here is
            # to detect cases where someone has mechanically rounded
            # the co-ordinates generated from Geograph without adding
            # any creativity, so it's OK for the bot to overwite them.
            return ["%.5f" % (orig,),
                    "%.5f" % (orig - copysign(0.000005, orig),),
                    "%.4f" % (orig,),
                    "%.4f" % (orig - copysign(0.00005, orig),),
                    "%.3f" % (orig,),
                    "%.3f" % (orig - copysign(0.0005, orig),),
            ]
        # Try both rounding towards zero and rounding to nearest.
        for rlat in possible_roundings(lat):
            for rlon in possible_roundings(lon):
                first_location.add(1, rlat)
                first_location.add(2, rlon)
                if location_template == first_location:
                    bot.log("Location matches rounded original")
                    return True
        return False
    def is_original_title(self, page, title):
        # This heuristic depends on GeographBot's behaviour.
        if not self.is_geographbot_upload(page):
            return False
        first_tree = self.get_original_tree(page)
        first_description = str(tlgetone(first_tree, ["Information"]).
                                get("description").value.get(0).get(1).value)
        return (first_description == title or
                first_description == title + "." or
                first_description.startswith(title + " ") or
                first_description.startswith(title + ". "))
    def process_page(self, page):
        location_replaced = False
        location_removed = False
        location_was_mine = False
        object_location_added = False
        creditline_added = False
        revid = page.latest_revision_id
        tree = mwparserfromhell.parse(page.text)
        gridimage_id = get_gridimage_id(tree)
        c = geodb.cursor()
        c.execute("""
            SELECT * FROM gridimage_base NATURAL JOIN gridimage_geo
               WHERE gridimage_id = ?
            """, (gridimage_id,))
        row = c.fetchone()
        if row == None:
            raise NotInGeographDatabase("Geograph ID %d not in database" %
                                        (gridimage_id,))
        try:
            location_template = get_location(tree)
        except IndexError:
            location_template = None
        new_location = location_from_row(row)
        minor = True
        bot.log("Existing location: %s" % (location_template,))
        if (location_template != None and
            location_template.name == 'Location dec' and
            self.is_original_location(page, location_template) and
            self.is_geographbot_upload(page) and
            new_location != location_template):
            bot.log("Proposed location: %s" % (new_location,))
            if (new_location != None and
                new_location.get('prec').value != '1000'):
                set_location(tree, new_location)
                azon, azno, distance = (
                    az_dist_between_locations(location_template, new_location))
                bot.log("Distance moved: %.1f m" % (distance,))
                if distance > float(str(new_location.get('prec').value)):
                    minor = False
                location_replaced = True
            else:
                set_location(tree, None)
                minor = False
                location_removed = True
        if (new_location != None and
            location_template == new_location and
            new_location.get('prec').value == '1000'):
            set_location(tree, None)
            minor = False
            location_removed = True
            location_was_mine = True
        if not has_object_location(tree):
            objloc = object_location_from_row(row)
            if objloc.get('prec').value == '1000' and not location_removed:
                bot.log("Skipping object location: precision is 1km")
            else:
                bot.log("New object location: %s" % (objloc,))
                set_object_location(tree, objloc)
                minor = False
                object_location_added = True
        creditline = creditline_from_row(row)
        if (can_add_creditline(tree, creditline) and
            self.is_original_title(page, row['title'])):
            add_creditline(tree, creditline)
            creditline_added = True
            minor = False
        else:
            bot.log("Cannot add credit line")
        newtext = str(tree)
        if newtext != page.text:
            if not self.is_geographbot_upload(page):
                raise NotEligible("Not a GeographBot upload")
            if location_replaced:
                if object_location_added:
                    summary = (
                        "Replace dubious [[User:GeographBot|GeographBot]]-"
                        "sourced camera location (moved %.1f m %s) and "
                        "add object location, both from Geograph (%s)" %
                        (distance, format_direction(azon), format_row(row)))
                else:
                    summary = (
                        "Replace dubious [[User:GeographBot|GeographBot]]-"
                        "sourced camera location (moved %.1f m %s), "
                        "from Geograph (%s)" %
                        (distance, format_direction(azon), format_row(row)))
            elif location_removed:
                if location_was_mine:
                    summary = (
                        "Remove vague camera location (probably added by me)")
                else:
                    summary = (
                        "Remove dubious [[User:GeographBot|GeographBot]]-"
                        "sourced camera location")
                if object_location_added:
                    summary += (
                        " and add object location from Geograph (%s)" %
                        (format_row(row),))
            elif object_location_added:
                summary = (
                    "Add object location from Geograph (%s)" %
                    (format_row(row),))
            else:
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
        except pywikibot.OtherPageSaveError as e:
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
        bot = FixLocationBot(gen, **options)
        bot.run()  # guess what it does
        return True
    else:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False

main()
