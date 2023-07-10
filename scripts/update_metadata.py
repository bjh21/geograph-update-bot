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
import json
from math import copysign
import mwparserfromhell
import re
import sqlite3
from uuid import uuid4

from creditline import creditline_from_row, can_add_creditline, add_creditline
from location import (location_from_row, object_location_from_row,
                      camera_statement_from_row, object_statement_from_row,
                      az_dist_between_locations, format_row,
                      format_direction, get_location, get_object_location,
                      set_location, set_object_location, location_params,
                      MapItSettings, statement_matches_template)

from gubutil import (
    connect_geograph_db, get_gridimage_id, TooManyTemplates, tlgetone,
    NewGeographImages, GeoGeneratorFactory)

# Ways that Geograph locations get in:
# BotMultichill (example?)
# DschwenBot (File:Panorama-Walsall.jpg)
# File Upload Bot (Magnus Manske)
# Geograph2commons

geodb = connect_geograph_db()
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
class SDCMismatch(MinorProblem):
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
    summary_formats = {
        # (camera_action, object_action)
        ('add', 'add'):
        "[[User:Geograph Update Bot/GEO|Added]] camera and object locations "
        "from Geograph ({row})",
        ('add', 'update'):
        "[[User:Geograph Update Bot/GEO|Added]] camera location and "
        "[[User:Geograph Update Bot/GEO|updated]] object location "
        "({object_move}), both from Geograph ({row})",
        ('add', 'remove'):
        "[[User:Geograph Update Bot/GEO|Added]] camera location from "
        "Geograph ({row}) and [[User:Geograph Update Bot/GEO|removed]] "
        "Geograph-derived ≥1km-precision object location",
        ('add', None):
        "[[User:Geograph Update Bot/GEO|Added]] camera location from Geograph "
        "({row})",
        ('update', 'add'):
        "[[User:Geograph Update Bot/GEO|Updated]] camera location "
        "({camera_move}) and [[User:Geograph Update Bot/GEO|added]] object "
        "location, both from Geograph ({row})",
        ('update', 'update'):
        "[[User:Geograph Update Bot/GEO|Updated]] camera and object locations "
        "({camera_move} and {object_move}, respectively) "
        "from Geograph ({row})",
        ('update', 'remove'):
        "[[User:Geograph Update Bot/GEO|Updated]] camera location "
        "({camera_move}) from Geograph ({row}) "
        "and [[User:Geograph Update Bot/GEO|removed]] Geograph-derived "
        "≥1km-precision object location",
        ('update', None):
        "[[User:Geograph Update Bot/GEO|Updated]] camera location "
        "({camera_move}) from Geograph ({row})",
        ('remove', 'add'):
        "[[User:Geograph Update Bot/GEO|Removed]] Geograph-derived camera "
        "location (no longer on Geograph, or ≥1km precision) "
        "and [[User:Geograph Update Bot/GEO|added]] object location from "
        "Geograph ({row})",
        ('remove', 'update'):
        "[[User:Geograph Update Bot/GEO|Removed]] Geograph-derived camera "
        "location (no longer on Geograph, or ≥1km precision) "
        "and [[User:Geograph Update Bot/GEO|updated]] object location "
        "({object_move}) from Geograph ({row})",
        # ('remove', 'remove') should be impossible
        ('remove', None):
        "[[User:Geograph Update Bot/GEO|Removed]] Geograph-derived camera "
        "location (no longer on Geograph, or ≥1km precision)",
        (None, 'add'):
        "[[User:Geograph Update Bot/GEO|Added]] object location from Geograph "
        "({row})",
        (None, 'update'):
        "[[User:Geograph Update Bot/GEO|Updated]] object location "
        "({object_move}) from Geograph ({row})",
        (None, 'remove'):
        "[[User:Geograph Update Bot/GEO|Removed]] Geograph-derived "
        "≥1km-precision object location",
        (None, None): ""
    }
    def should_set_location(self, old_template, new_template, desc):
        oldparam = location_params(old_template)
        newparam = location_params(new_template)
        # We generally want to synchronise with Geograph.
        should_set = True
        # but not if there's no change (e.g. both are None)
        if old_template == new_template: should_set = False
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
        if old_template == None or new_template == None: return None
        azon, azno, distance = (
            az_dist_between_locations(old_template, new_template))
        if distance >= 1000:
            return "moved %.1f km %s" % (distance/1000, format_direction(azon))
        return "moved %.1f m %s" % (distance, format_direction(azon))
    def get_sdc_statements(self, page):
        # SDC data aren't preloaded, so we make an API request every time.
        # This could be better, wbgetentities can do batches of pages just
        # like query.
        mediaid = 'M%d' % (page.pageid,)
        request = self.site.simple_request(action='wbgetentities',
                                           ids=mediaid)
        data = request.submit()
        return data['entities'][mediaid].get('statements', {})
    def process_page(self, page):
        camera_action = None
        object_action = None
        sdc_camera_action = None
        sdc_object_action = None
        creditline_added = False
        sdc_edits = {}
        revid = page.latest_revision_id
        tree = mwparserfromhell.parse(page.text)
        try:
            gridimage_id = get_gridimage_id(tree)
        except ValueError as e:
            raise BadTemplate(str(e))
        except IndexError as e:
            raise BadTemplate(str(e))
            
        mapit = MapItSettings()
        c = geodb.cursor()
        c.execute("""
            SELECT * FROM gridimage_base NATURAL JOIN gridimage_geo
                          NATURAL JOIN gridimage_extra, sources
               WHERE gridimage_id = ? AND sources.tablename = 'gridimage_geo'
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
                camera_action = 'add'
            set_object_location(tree, new_object_location)
            object_action = 'add'
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
                if ((should_set_cam and old_location != None) or
                    (should_set_obj and old_object_location != None)):
                    # Check if SDC has location templates.
                    statements = self.get_sdc_statements(page)
                    if 'P625' in statements:
                        raise SDCMismatch("P625 no longer supported")
                    for s in statements.get('P1259', []):
                        if should_set_cam and old_location != None:
                            bot.log("Considering P1259 update")
                            if not statement_matches_template(s, old_location):
                                raise SDCMismatch("SDC/template mismatch: "
                                                  "%s vs %s" %
                                                  (s, old_location))
                            s_new = camera_statement_from_row(row)
                            if s_new == None:
                                s_new = dict(id=s['id'], remove="")
                                bot.log("Removing %s statement %s" %
                                        (s['mainsnak']['property'], s['id']))
                                sdc_camera_action = 'remove'
                            else:
                                s_new['id'] = s['id']
                                bot.log("Updating %s statement %s" %
                                        (s['mainsnak']['property'], s['id']))
                                sdc_camera_action = 'update'
                            sdc_edits.setdefault('claims', [])
                            sdc_edits['claims'].append(s_new)
                    for s in statements.get('P9149', []):
                        if should_set_obj and old_object_location != None:
                            bot.log("Considering P9149 update")
                            if not statement_matches_template(
                                    s, old_object_location):
                                raise SDCMismatch("SDC/template mismatch: "
                                                  "%s vs %s",
                                                  (s, old_object_location))
                            s_new = object_statement_from_row(row)
                            if s_new == None:
                                s_new = dict(id=s['id'], remove="")
                                bot.log("Removing %s statement %s" %
                                        (s['mainsnak']['property'], s['id']))
                                sdc_object_action = 'remove'
                            else:
                                s_new['id'] = s['id']
                                bot.log("Updating %s statement %s" %
                                        (s['mainsnak']['property'], s['id']))
                                sdc_object_action = 'update'
                            sdc_edits.setdefault('claims', [])
                            sdc_edits['claims'].append(s_new)
                    # If we're updating SDC anyway, consider adding missing
                    # geocoding statements.
                    if (sdc_object_action != None and
                        'P1259' not in statements and should_set_cam):
                        s_new = camera_statement_from_row(row)
                        if s_new != None:
                            sdc_camera_action = 'add'
                            sdc_edits.setdefault('claims', [])
                            sdc_edits['claims'].append(s_new)
                    if (sdc_camera_action != None and
                        'P9149' not in statements and should_set_obj):
                        s_new = object_statement_from_row(row)
                        if s_new != None:
                            sdc_object_action = 'add'
                            sdc_edits.setdefault('claims', [])
                            sdc_edits['claims'].append(s_new)
                # Do it if necessary:
                mapit.allowed = True
                if should_set_cam:
                    set_location(tree, location_from_row(row, mapit=mapit))
                    if old_location == None:
                        if new_location != None:
                            camera_action = 'add'
                    else:
                        if new_location == None:
                            camera_action = 'remove'
                        else:
                            camera_action = 'update'
                if should_set_obj:
                    set_object_location(tree,
                                    object_location_from_row(row, mapit=mapit))
                    if old_object_location == None:
                        if new_object_location != None:
                            object_action = 'add'
                    else:
                        if new_object_location == None:
                            object_action = 'remove'
                        else:
                            object_action = 'update'
        creditline = creditline_from_row(row)
        if (can_add_creditline(tree, creditline)):
            add_creditline(tree, creditline)
            creditline_added = True
            minor = False
        else:
            bot.log("Cannot add credit line")
        newtext = str(tree)
        if newtext != page.text:
            editgroup_summary = ""
            if sdc_edits:
                # Generate an edit group ID.  See
                # <https://commons.wikimedia.org/wiki/
                # Commons:Edit_groups/Adding_a_tool>
                editgroup_summary = (" ([[:toolforge:editgroups-commons/b/CB/"
                                     f"{uuid4().hex}|details]])")
            format_params = dict(row=format_row(row))
            if camera_action == 'update':
                format_params['camera_move'] = (
                    self.describe_move(old_location, new_location))
            if object_action == 'update':
                format_params['object_move'] = (
                    self.describe_move(old_object_location,
                                       new_object_location))
            summary = (self.summary_formats[(camera_action, object_action)]
                       .format(**format_params))
            if creditline_added:
                if summary == "":
                    summary = ("[[User:Geograph Update Bot/CRED|Added]] "
                               "credit line with title from Geograph")
                else:
                    summary += ("; [[User:Geograph Update Bot/CRED|added]] "
                                "credit line with title from Geograph")
            if mapit.used:
                # Requested credit where MapIt is used:
                # 'Attribution should use the text “Powered by MapIt”,
                # with a link back to this page.'
                summary += (
                    " [Powered by MapIt: https://global.mapit.mysociety.org]")
            summary += editgroup_summary
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
            if sdc_edits:
                sdc_summary = (self.summary_formats[(sdc_camera_action,
                                                     sdc_object_action)]
                               .format(**format_params))
                sdc_summary += editgroup_summary
                bot.log("SDC edit summary: %s" % (sdc_summary,))
                self.site.simple_request(
                    action='wbeditentity', format='json',
                    id='M%d' % (page.pageid,), data=json.dumps(sdc_edits),
                    token=self.site.tokens['csrf'], summary=sdc_summary,
                    bot=True, baserevid=revid).submit()

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
