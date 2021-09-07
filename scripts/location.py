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
bng = pyproj.CRS.from_epsg(27700)
# epsg:29903 is the Irish Grid
ig = pyproj.CRS.from_epsg(29903)
wgs84 = pyproj.CRS.from_epsg(4326)
transformers = {
    bng: pyproj.Transformer.from_crs(bng, wgs84),
    ig:  pyproj.Transformer.from_crs(ig, wgs84),
}

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

class MapItSettings(object):
    def __init__(self, allowed=False):
        self.allowed = allowed
        self.used = False

def region_of(grid, e, n, latstr, lonstr, mapit = None):
    # First, see if it's obvious.  Look for a myriad wholly within a single
    # region (including territorial waters).
    myriad = None
    if grid == bng:
        myriad = bngr_from_en(e, n, 0)
        if myriad in ('NG', 'NH', 'NM', 'NN', 'NS'): return 'GB-SCT'
        if myriad == 'NY': return 'GB-GBN' # Spans England/Scotland border
        if myriad in ('SJ', 'SO', 'ST'): return 'GB-EAW' # England/Wales
        if myriad in ('SE', 'SK', 'SP', 'SS', 'SU', 'TL', 'TQ'):
            return 'GB-ENG'
    if grid == ig:
        if igr_from_en(e, n, 0) in ('M', 'N', 'R', 'S'): return 'IE'

    if mapit and mapit.allowed:
        r = requests.get('http://global.mapit.mysociety.org'
                         '/point/4326/{},{}'.format(lonstr,latstr))
        r.raise_for_status()
        j = r.json()
        for area in j.values():
            if 'codes' in area and 'iso3166_1' in area['codes']:
                mapit.used = True
                if area['codes']['iso3166_1'] == 'GB':
                    if grid == ig:
                        return 'GB-NIR'
                    return 'GB-GBN'
                return area['codes']['iso3166_1']
    return None

def source_from_grid(grid, e, n, digits):
    src = "geograph"
    if grid == bng:
        src += "-osgb36({})".format(bngr_from_en(e, n, digits))
    if grid == ig:
        src += "-irishgrid({})".format(igr_from_en(e, n, digits))
    return src

def latlon_from_grid(grid, e, n, digits, use6fig):
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
    lat, lon = transformers[grid].transform(e, n)
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
    return latstr, lonstr, prec

def location_from_grid(grid, e, n, digits, view_direction, use6fig,
                       mapit = None):
    latstr, lonstr, prec = latlon_from_grid(grid, e, n, digits, use6fig)
    precstr = "{:g}".format(prec)
    paramstr = "source:" + source_from_grid(grid, e, n, digits)
    region = region_of(grid, e, n, latstr, lonstr, mapit)
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

def statement_from_grid(grid, e, n, digits, view_direction, use6fig):
    latstr, lonstr, prec = latlon_from_grid(grid, e, n, digits, use6fig)
    # The precision of a Wikidata GlobeCoordinateValue is expressed in
    # degrees and must be the same in latitude and longitude.  A metre
    # is about 0.00002° in longitude at our kind of latitude.
    prec = prec * 0.00002
    s = dict(
        type="statement", rank='normal', mainsnak=dict(
            snaktype="value", property="P1259", datavalue=dict(
                type="globecoordinate", value=dict(
                    globe="http://www.wikidata.org/entity/Q2",
                    # Contrary to documentation, latitude and longitude
                    # must be numbers and not strings.
                    latitude=float(latstr), longitude=float(lonstr),
                    precision=prec))))
    if view_direction != None:
        s['qualifiers'] = dict(P7787=[dict(
            snaktype="value", property="P7787", datavalue=dict(
                type="quantity", value=dict(
                    amount="{:+}".format(view_direction),
                    unit="http://www.wikidata.org/entity/Q28390")))])
    return s

def camera_grid_from_row(row, mapit = None):
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
    return grid, e, n, digits, heading, use6fig

def location_from_row(row, mapit = None):
    camera_grid = camera_grid_from_row(row)
    if camera_grid == None: return None
    grid, e, n, digits, heading, use6fig = camera_grid
    # Consensus on Commons seems to be that 1km is not sufficient for
    # camera location, but is acceptable for object location if that's
    # all we've got.
    if digits == 4:
        return None
    t = location_from_grid(grid, e, n, digits, heading, use6fig, mapit)
    return t

def camera_statement_from_row(row):
    camera_grid = camera_grid_from_row(row)
    if camera_grid == None: return None
    grid, e, n, digits, heading, use6fig = camera_grid
    # Consensus on Commons seems to be that 1km is not sufficient for
    # camera location, but is acceptable for object location if that's
    # all we've got.
    if digits == 4:
        return None
    s = statement_from_grid(grid, e, n, digits, heading, use6fig)
    return s

def object_grid_from_row(row):
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
    return grid, e, n, digits, heading, use6fig

def object_location_from_row(row, mapit = None):
    grid, e, n, digits, heading, use6fig = object_grid_from_row(row)
    # Consensus on Commons seems to be that 1km is not sufficient for
    # camera location, but is acceptable for object location if that's
    # all we've got.
    if digits == 4 and location_from_row(row) != None:
        return None
    t = location_from_grid(grid, e, n, digits, heading, use6fig, mapit)
    t.name = mwparserfromhell.parse("Object location")
    return t

def object_statement_from_row(row):
    grid, e, n, digits, heading, use6fig = object_grid_from_row(row)
    # Consensus on Commons seems to be that 1km is not sufficient for
    # camera location, but is acceptable for object location if that's
    # all we've got.
    if digits == 4 and camera_statement_from_row(row) != None:
        return None
    s = statement_from_grid(grid, e, n, digits, heading, use6fig)
    s['mainsnak']['property'] = "P9149"
    return s

# Determine whether a structured data statement is equivalent to a
# given template.  This is useful because we'd like to detect
# statements that are based on old data from Geograph by matching them
# against templates.  This wouldn't be necessary if statements could
# record their sources like templates can.
def statement_matches_template(statement, template):
    # A major point of this is to detect cases where BotMultichill has
    # copied co-ordinates from wikitext to SDC properties, so we need
    # to recognise its handiwork.

    # First check that the statement has the right property.
    if not ((statement['mainsnak']['property'] == 'P9149' and
             template.name in objtls) or
            (statement['mainsnak']['property'] == 'P1259' and
             template.name in loctls)):
        return False
    # Templates correspond to actual locations on Earth.
    if not (statement['mainsnak']['snaktype'] == 'value' and
            statement['mainsnak']['datavalue']['type'] == 'globecoordinate' and
            statement['mainsnak']['datavalue']['value']['globe'] ==
            "http://www.wikidata.org/entity/Q2"): return False
    statement_value = statement['mainsnak']['datavalue']['value']
    # Check lat/long between statement and template.
    if not (float(statement_value['latitude'])  == float(str(template.get(1)))
            and
            float(statement_value['longitude']) == float(str(template.get(2)))):
        return False
    # We deliberately ignore precision.
    # There might be a bearing.
    if (statement['mainsnak']['property'] in ('P1259', 'P9149') and
        list(statement.get('qualifiers', {}).keys()) not in
        ([], ['P7787'])): return False
    # If there is a bearing, check its structure.
    bearing_statements = statement.get('qualifiers', {}).get('P7787', [])
    if len(bearing_statements) > 1: return False
    statement_bearing = None
    if len(bearing_statements) == 1:
        bearing_statement = bearing_statements[0]
        if not (bearing_statement['snaktype'] == 'value' and
                bearing_statement['datavalue']['type'] == 'quantity' and
                bearing_statement['datavalue']['value']['unit'] ==
                'http://www.wikidata.org/entity/Q28390'): return False
        # Extract value of bearing.
        statement_bearing = (
            float(bearing_statement['datavalue']['value']['amount']))
    if statement_bearing != None:
        params = location_params(template)
        if 'heading' in params:
            if float(params['heading']) != statement_bearing: return False
    # If we've survived all that, they probably match.
    return True

def location_statement_from_row(row):
    """
    Notes:
    P9149 -> lat, lon, prec
    P1259 -> lat, lon, prec
      P7787 -> hdg, hdg - 11.25, hdg + 11.25, Q28390
    refs:
      P248 -> Q1503119
      P854 -> https://www.geograph.org.uk/photo/{gridimage_id}
      P577 -> {last_modified}
    """

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
    paramdict = { }
    try:
        paramstr = template.get(3).value
        for x in paramstr.split('_'):
            k, _, v = x.partition(':')
            paramdict[k] = v
    except AttributeError:
        # Probably passed None
        pass
    except ValueError:
        # Probably parameter not found
        pass
    return paramdict
    
