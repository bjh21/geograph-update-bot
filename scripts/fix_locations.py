from __future__ import division, print_function

import pywikibot
from pywikibot.bot import (
    SingleSiteBot, ExistingPageBot, NoRedirectPageBot, AutomaticTWSummaryBot)
import pywikibot.bot as bot
import pywikibot.data.api as api
import pywikibot.pagegenerators
import mwparserfromhell
import re
import sqlite3
from location import location_from_row, distance_between_locations, format_row

geodb = sqlite3.connect('../geograph-db/geograph.sqlite3')
geodb.row_factory = sqlite3.Row

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
    def process_page(self, page):
        tree = mwparserfromhell.parse(page.text)
        gridimage_id = self.gridimage_id_from_tree(tree)
        c = geodb.cursor()
        c.execute("""
            SELECT * FROM gridimage_base NATURAL JOIN gridimage_geo
               WHERE gridimage_id = ?
            """, (gridimage_id,))
        row = c.fetchone()
        if row == None:
            raise NotInGeographDatabase("Geograph ID %d not in database" %
                                        (gridimage_id,))
        location_template = self.get_template(tree, "Location dec")
        bot.log("Existing location: %s" % location_template)
        new_location = location_from_row(row)
        bot.log("Proposed location: %s" % (new_location,))
        distance = distance_between_locations(location_template, new_location)
        bot.log("Distance moved: %.1f m" % (distance,))
        if (distance < float(str(new_location.get('prec').value)) and
            new_location.name != 'Object location'):
            raise NotEligible("Change too small to matter")
        firstrev = page.oldest_revision.full_hist_entry()
        if firstrev.user != 'GeographBot':
            raise NotEligible("Not a GeographBot upload")
        first_text = page.getOldVersion(firstrev.revid)
        first_tree = mwparserfromhell.parse(first_text)
        first_location = self.get_template(first_tree, "Location dec")
        if location_template != first_location:
            raise NotEligible("Location template changed since upload")
        tree.replace(location_template, location_from_row(row))
        page.text = str(tree)
        page.save("Update location from Geograph (%s)" %
                  (format_row(row),))

    def treat_page(self):
        try:
            self.process_page(self.current_page)
        except NotEligible as e:
            bot.log(str(e))
        except MinorProblem as e:
            bot.warning(str(e))
        except MajorProblem as e:
            bot.error(str(e))

def InterestingGeographsByNumber(**kwargs):
    site = kwargs['site']
    # Fetch starting date from a special page.
    #startpage = pywikibot.Page(site, 'User:Geograph Update Bot/last ID')
    #start = int(startpage.text)
    #startsortkeyprefix=" %08d" % (start,)
    n = 0
    g = api.ListGenerator("categorymembers", parameters=dict(
            cmtitle="Category:Images from the Geograph British Isles project",
            cmprop="title|sortkeyprefix", cmtype="file",
            cmstartsortkeyprefix=startsortkeyprefix), **kwargs)
    g1 = api.QueryGenerator(parameters=dict(
        generator="categorymembers",
        gcmtitle="Category:Images from the Geograph British Isles project",
        gcmtype="file", gcmstartsortkeyprefix=startsortkeyprefix,
        prop="imageinfo", iiprop="size"), **kwargs)
    for page in InterestingGeographGenerator(site, g0, g1):
        yield page
        n = n + 1;
        if (n % 50 == 0):
            # Write a checkpoint every fifty yielded items
            startpage.text = str(gridimage_id)
            startpage.save("Checkpoint: up to %d" % (gridimage_id,))

def InterestingGeographsByDate(**kwargs):
    site = kwargs['site']
    g0 = api.ListGenerator("categorymembers", parameters=dict(
            cmtitle="Category:Images from the Geograph British Isles project",
            cmprop="title|sortkeyprefix", cmtype="file",
            cmsort="timestamp", cmdir="older",
            ), **kwargs)
    g1 = api.QueryGenerator(parameters=dict(
        generator="categorymembers",
        gcmtitle="Category:Images from the Geograph British Isles project",
        gcmtype="file",
        gcmsort="timestamp", gcmdir="older",
        prop="imageinfo", iiprop="size"), **kwargs)
    yield from InterestingGeographGenerator(site, g0, g1)

def InterestingGeographGenerator(site, g0, g1):
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
            print("%d: %s" % (gridimage_id, str(e)), file=whynot)
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
        gen = InterestingGeographsByDate(site=pywikibot.Site())
    if gen:
        # pass generator and private options to the bot
        bot = FixLocationBot(gen, **options)
        bot.run()  # guess what it does
        return True
    else:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False

main()
