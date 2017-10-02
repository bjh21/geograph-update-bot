from __future__ import division, print_function, unicode_literals

import pyproj

from mwparserfromhell.nodes.template import Template

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
        gridlettermap[letter] = (j, 5-i)

def en_from_gr(gr):
    # Convert a 4-figure grid reference to eastings and northings of
    # SW corner.
    if len(gr) == 6:
        # British grid: two grid letters
        e = -1000000 + gridlettermap[gr[0]][0] * 500000
        n = -1100000 + gridlettermap[gr[0]][1] * 500000
    else:
        # Irish grid: one grid letter
        assert(len(gr) == 5)
        e = 0
        n = -100000
    e += gridlettermap[gr[-5]][0] * 100000
    n += gridlettermap[gr[-5]][1] * 100000
    e += int(gr[-4:-2]) * 1000
    n += int(gr[-2:]) * 1000
    return (e, n)

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
    # Since each grid reference describes a square, and we've
    # converted its centre, the radius of the circle within which the
    # true position falls is roughly 1/2*sqrt(2) times the width of
    # the square.  We approximate 1/2*sqrt(2) as 0.7.
    precstr = "{:g}".format(0.7 * square)
    # but if use6fig is set, our accuracy is less
    if use6fig: precstr = "70"
    paramstr = "source:geograph"
    if view_direction != None:
        paramstr += "_heading:{}".format(view_direction)
    return [latstr, lonstr, paramstr, "prec=" + precstr]

def location_from_row(row):
    # Row is assumed to be a database row.
    grids = { 1: bng, 2: ig }
    grid = grids[row['reference_index']]
    if row['viewpoint_grlen'] != '0':
        e, n, digits = (row['viewpoint_eastings'], row['viewpoint_northings'],
                        int(row['viewpoint_grlen']))
        template = "Location"
    elif row['natgrlen'] in ('6', '8', '10'):
        e, n, digits = (row['nateastings'], row['natnorthings'],
                        int(row['natgrlen']))
        template = "Object location"
    else:
        # extract from grid_reference
        e, n = en_from_gr(row['grid_reference'])
        digits = int(row['natgrlen'])
        template = "Object location"
    heading = int(row['view_direction'])
    if heading == -1: heading = None
    use6fig = bool(row['use6fig'])
    return Template(template, location_from_grid(grid, e, n, digits,
                                                     heading, use6fig))
