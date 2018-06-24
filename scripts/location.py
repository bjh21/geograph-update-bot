from __future__ import division, print_function, unicode_literals

import pyproj

import mwparserfromhell
from mwparserfromhell.nodes.template import Template
from mwparserfromhell.nodes.text import Text
from mwparserfromhell.wikicode import Wikicode
import requests

from gubutil import tlgetall, tlgetone

# Geograph Britain and Ireland uses the British National Grid in Great
# Britain and the Irish Grid in Ireland.

# epsg:27700 is the British National Grid
bng = pyproj.Proj(init="epsg:27700")
# epsg:29903 is the Irish Grid
ig = pyproj.Proj(init="epsg:29903")
wgs84 = pyproj.Proj(proj="latlong", datum="WGS84")

gridletters = [
    "ABCDE",
    "FGHJK",
    "LMNOP",
    "QRSTU",
    "VWXYZ"]
gridlettermap = { }
for i, row in enumerate(gridletters):
    for j, letter in enumerate(row):
        gridlettermap[letter] = (j, 4-i)

def en_from_gr(gr):
    # Convert a 4-figure grid reference to eastings and northings of
    # SW corner.
    if len(gr) == 6:
        # British grid: two grid letters
        e = -1000000 + gridlettermap[gr[0]][0] * 500000
        n =  -500000 + gridlettermap[gr[0]][1] * 500000
    else:
        # Irish grid: one grid letter
        assert(len(gr) == 5)
        e = 0
        n = 0
    e += gridlettermap[gr[-5]][0] * 100000
    n += gridlettermap[gr[-5]][1] * 100000
    e += int(gr[-4:-2]) * 1000
    n += int(gr[-2:]) * 1000
    return (e, n)

def bngr_from_en(e, n, digits):
    e = int(e + 1000000)
    n = int(n +  500000)
    letters = (gridletters[4-n//500000][e//500000] +
               gridletters[4-n%500000//100000][e%500000//100000])
    estr = "{:05d}".format(e%100000)[:int(digits//2)]
    nstr = "{:05d}".format(n%100000)[:int(digits//2)]
    return letters + estr + nstr

def igr_from_en(e, n, digits):
    e = int(e)
    n = int(n)
    letter = gridletters[4-n//100000][e//100000]
    estr = "{:05d}".format(e%100000)[:int(digits//2)]
    nstr = "{:05d}".format(n%100000)[:int(digits//2)]
    return letter + estr + nstr

def region_of(grid, e, n, lat, lon):
    r = requests.get('http://global.mapit.mysociety.org'
                     '/point/4326/{:f},{:f}'.format(lon,lat))
    r.raise_for_status()
    j = r.json()
    for area in j.values():
        if 'codes' in area and 'iso3166_1' in area['codes']:
            return area['codes']['iso3166_1']
    return None

def source_from_grid(grid, e, n, digits):
    src = "geograph"
    if grid == bng:
        src += "-osgb36({})".format(bngr_from_en(e, n, digits))
    if grid == ig:
        src += "-irishgrid({})".format(igr_from_en(e, n, digits))
    return src

def location_from_grid(grid, e, n, digits, view_direction, use6fig):
    # A grid reference in textual form, like SO8001, represents a
    # square on the ground whose size depends on the number of digits.
    # So SO8001 is the 1km square whose SW corner is at
    # (380000,201000).  To convert a grid reference to lat/lon, we
    # really want to use the location of the centre of the square, but
    # Geograph stores the SW corner, so we need to add half a square
    # in each direction based on the length of the grid reference.
    square = 10**(5-digits/2)
    e += 0.5 * square
    n += 0.5 * square
    lon, lat = pyproj.transform(grid, wgs84, e, n)
    # At 6dp, one ulp in latitude is about 11cm.  In longitude, about
    # 6cm.  Thus 6dp is enough to distinguish 10-figure GRs in latitude,
    # and 5dp is enough in longitude.
    latstr = "{{:.{}f}}".format(digits//2 + 1).format(lat)
    lonstr = "{{:.{}f}}".format(digits//2).format(lon)
    # The "prec=" parameter doesn't seem to be well-defined, so we
    # just put the size of a grid square in it.
    prec = square
    # but if use6fig is set, our accuracy is less
    if use6fig: prec = max(prec, 100)
    precstr = "{:g}".format(prec)
    paramstr = "source:" + source_from_grid(grid, e, n, digits)
    region = region_of(grid, e, n, lat, lon)
    if region != None:
        paramstr += "_region:{}".format(region)
    if view_direction != None:
        paramstr += "_heading:{}".format(view_direction)
    t = Template(mwparserfromhell.parse('Location'))
    t.add(1, latstr)
    t.add(2, lonstr)
    t.add(3, paramstr)
    t.add('prec', precstr)
    return t

def location_from_row(row):
    # Row is assumed to be a database row.
    grids = { 1: bng, 2: ig }
    grid = grids[row['reference_index']]
    # Usually, lack of a viewpoint location is indicated by
    # viewpoint_grlen = '0'.  Sometimes, though, it's indicated by
    # viewpoint_northings = 0 and viewpoint_eastings = 0, so we handle
    # that as well.
    if not (row['viewpoint_grlen'] == '0' or
            (row['viewpoint_eastings'] == 0 and
             row['viewpoint_northings'] == 0)):
        e, n, digits = (row['viewpoint_eastings'], row['viewpoint_northings'],
                        int(row['viewpoint_grlen']))
    elif row['moderation_status'] == 'geograph':
        # Geograph rules say that the photographer must be in (or very
        # close to) the target square.  This only applies to images
        # moderated as Geographs.
        e, n = en_from_gr(row['grid_reference'])
        digits = 4
    else:
        return None
    # The Geograph view direction is probably specified in grid space
    # rather than as a true heading.  Happily, the difference in the
    # second-worst place (Soay) is only 5°, which isn't really
    # significant when the direction is only specified with 23°
    # precision.  At Rockall, the difference is 10°, but none of the
    # photos of Rockall on Geograph has a view direction set anyway.
    heading = int(row['view_direction'])
    if heading == -1: heading = None
    use6fig = bool(row['use6fig'])
    t = location_from_grid(grid, e, n, digits, heading, use6fig)
    return t

def object_location_from_row(row):
    # The "subject location" in Geograph isn't necessarily the main
    # subject of the image:
    #
    # https://www.geograph.org.uk/article/Which-Square
    #
    # In practice, though, the best we can do is to assume that it is.
    grids = { 1: bng, 2: ig }
    grid = grids[row['reference_index']]
    if row['natgrlen'] in ('6', '8', '10'):
        e, n, digits = (row['nateastings'], row['natnorthings'],
                        int(row['natgrlen']))
    else:
        e, n = en_from_gr(row['grid_reference'])
        digits = int(row['natgrlen'])
    heading = int(row['view_direction'])
    if heading == -1: heading = None
    use6fig = bool(row['use6fig'])
    t = location_from_grid(grid, e, n, digits, heading, use6fig)
    t.name = mwparserfromhell.parse("Object location")
    return t

# This is overkill, but since I've got pyproj lying around...
geod = pyproj.Geod(ellps='WGS84')
def az_dist_between_locations(loc1, loc2):
    lat1 = float(str(loc1.get(1)))
    lat2 = float(str(loc2.get(1)))
    lon1 = float(str(loc1.get(2)))
    lon2 = float(str(loc2.get(2)))
    # az12, az21, dist
    return geod.inv(lon1, lat1, lon2, lat2)

def format_row(row):
    # Format a database row for use in an edit summary.
    ret = "subject "
    if row['reference_index'] == 1:
        fmtref = bngr_from_en
    else:
        fmtref = igr_from_en
    if row['natgrlen'] == '4':
        ret += row['grid_reference']
    else:
        ret += fmtref(row['nateastings'], row['natnorthings'],
                      int(row['natgrlen']))
    if not (row['viewpoint_grlen'] == '0' or
            (row['viewpoint_eastings'] == 0 and
             row['viewpoint_northings'] == 0)):
        ret += "; viewpoint " + fmtref(row['viewpoint_eastings'],
                                       row['viewpoint_northings'],
                                       int(row['viewpoint_grlen']))
    if row['view_direction'] != -1:
        ret += "; looking {}".format(format_direction(row['view_direction']))
    if row['use6fig'] and (int(row['natgrlen']) > 4 or
                           int(row['viewpoint_grlen']) > 4):
        ret += "; use6fig"
    if row['moderation_status'] == 'geograph':
        ret += "; geograph"
    return ret

def format_direction(dir):
    dirs = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
            'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW', 'N']
    return dirs[int(round(dir / 22.5))]

# Known aliases of {{Location}}
loctls = ("Location", "Location dec", "Location dms", "Camera Location",
          "Koordynaty", "Camera location", "Camera location dec",
          "Location Dec", "Locationdec", "Locationdms")

# Known aliases of {{Object Location}}
objtls = ("Object location", "Object location dec", "Object Location",
          "Object Location dec")

# Known infobox templates
# https://commons.wikimedia.org/wiki/Commons:Infobox_templates
infoboxes = ("Information", "Artwork", "Photograph", "Art photo", "Book",
             "Map", "Musical work", "Information2", "COAInformation",
             "Bus-Information", "Infobox aircraft image", "Spoken article",
             "Specimen")
def isinfobox(t):
    for x in infoboxes:
        if tpmatch(t.name, x): return True
    return False

# Remove all matching templates and replace the first of them with the
# new one.
def replace_templates(tree, new, names):
    olds = tlgetall(tree, names)
    tree.replace(olds[0], new)
    for o in olds[1:]:
        tree.remove(o)

def insert_template_after(tree, new, names):
    olds = tlgetall(tree, names)
    tree.insert_after(olds[0], Wikicode([Text("\n"), new]))

def insert_template_before(tree, new, names):
    olds = tlgetall(tree, names)
    tree.insert_before(olds[0], Wikicode([new, Text("\n")]))

def insert_template_at_start(tree, new):
    tree.insert(0, Wikicode([new, Text("\n")]))

def get_location(tree):
    return tlgetone(tree, loctls)

def set_location(tree, loc):
    if loc == None:
        for tl in tlgetall(tree, loctls):
            tree.remove(tl)
        return
    try:
        replace_templates(tree, loc, loctls)
    except IndexError:
        try:
            insert_template_before(tree, loc, objtls)
        except IndexError:
            try:
                insert_template_after(tree, loc, infoboxes)
            except IndexError:
                insert_template_at_start(tree, loc)

def get_object_location(tree):
    return tlgetone(tree, objtls)

def has_object_location(tree):
    return len(tlgetall(tree, objtls)) > 0
                
def set_object_location(tree, oloc):
    if oloc == None:
        for tl in tlgetall(tree, objtls):
            tree.remove(tl)
        return
    try:
        replace_templates(tree, oloc, objtls)
    except IndexError:
        try:
            insert_template_after(tree, oloc, loctls)
        except IndexError:
            try:
                insert_template_after(tree, oloc, infoboxes)
            except IndexError:
                insert_template_at_start(tree, oloc)

def location_params(template):
    paramstr = template.get(3)
    paramdict = { }
    for x in paramstr.split('_'):
        k, _, v = x.partition(':')
        paramdict[k] = v
    return paramdict

    
