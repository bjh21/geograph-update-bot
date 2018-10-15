# Useful stuff for all tasks of Geograph Update Bot.

from functools import partial
import re

# Template searching functions.

def titlematch(a, b):
    a = a.strip()
    b = b.strip()
    return a[0].upper() + a[1:] == b[0].upper() + b[1:]

def titlein(a, bs):
    return any(map(partial(titlematch, a), bs))

def tlmatchfn(names):
    return lambda tl: titlein(tl.name, names)

class TooManyTemplates(Exception):
    pass

def tlgetall(tree, names):
    return tree.filter_templates(matches = tlmatchfn(names))

def tlgetone(tree, names):
    tls = tlgetall(tree, names)
    if len(tls) > 1:
        raise TooManyTemplates("%d %s or equivalent templates" %
                               (len(tls), tls[0]))
    return tls[0] # raises IndexError

def tlgetfirst(tree, names):
    tls = tlgetall(tree, names)
    return tls[0] # raises IndexError

geographtls = ("Geograph", "Also geograph")

# Get Geograph ID of a file
def get_gridimage_id(tree):
    return int(str(tlgetone(tree, geographtls).get(1).value))

# Canonicalise a Geograph user name for comparison
def canonicalise_name(n):
    n = str(n)
    n = re.sub("^\s+", "", n) # Strip leading spaces.
    n = re.sub("\s+$", "", n) # Strip trailing spaces.
    n = re.sub("\s+", " ", n) # Compress multiple spaces
    return n

# Page generators
import pywikibot.data.api as api

def NewGeographImages(parameters = None, **kwargs):
    if parameters == None: parameters = dict()
    return api.PageGenerator("categorymembers", parameters=dict(
        gcmtitle="Category:Images from Geograph Britain and Ireland",
        gcmtype="file",
        gcmsort="timestamp", gcmdir="older", **parameters),
        **kwargs)

def GeographBotUploads(parameters = None, **kwargs):
    if parameters == None: parameters = { }
    parameters['gaiuser'] = 'GeographBot'
    parameters['gaisort'] = 'timestamp'
    print(parameters)
    return api.PageGenerator("allimages", parameters=parameters, **kwargs)

import sqlite3
from dateutil.tz import gettz

geodb = sqlite3.connect('geograph-db/geograph.sqlite3')
geodb.row_factory = sqlite3.Row

def ModifiedGeographs(modified_since, submitted_before):
    # Return images modified on Geograph since the specified start time
    # (as a datetime).
    c = geodb.cursor()
    geograph_mod = (
        modified_since.astimezone(gettz("Europe/London"))
                      .strftime("%Y-%m-%d %H:%M:%S"))
    geograph_sub = (
        submitted_before.astimezone(gettz("Europe/London"))
                        .strftime("%Y-%m-%d %H:%M:%S"))
    c.execute("""
        SELECT gridimage_id
          FROM gridimage_extra
         WHERE upd_timestamp >= ? AND submitted < ?
        """, (geograph_mod, geograph_sub))
    for row in c:
        yield from PagesByGeographId(row['gridimage_id'])

def PagesByGeographId(gridimage_id):
    # Returns all pages with a given Geograph ID.
    return api.PageGenerator("categorymembers", parameters=dict(
        gcmtitle="Category:Images from Geograph Britain and Ireland",
        gcmtype="file",
        gcmstartsortkeyprefix=" %08d" % (gridimage_id,),
        gcmendsortkeyprefix=" %08d" % (gridimage_id + 1,)))

import pywikibot.pagegenerators
from pywikibot.pagegenerators import PreloadingGenerator
from datetime import datetime, timedelta, timezone
from dateutil.tz import gettz
from itertools import chain

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
    def _handle_newgeographs(self, value):
        return NewGeographImages(site=pywikibot.Site())
