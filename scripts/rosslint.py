#! /usr/bin/python

from __future__ import print_function
import pywikibot.data.api as api

import pywikibot
import mwparserfromhell
import requests
import re
import sqlite3
from urllib.parse import urlencode

from gubutil import tlgetone

site = pywikibot.Site()

geodb = sqlite3.connect('../geograph-db/geograph.sqlite3')
geodb.row_factory = sqlite3.Row

client = requests.Session()
client.headers['User-Agent'] = "rosslint (bjh21@bjh21.me.uk)"

def get_geograph_info(gridimage_id):
    # Use the oEmbed API
    r = client.get("https://api.geograph.org.uk/api/oembed",
                     params={'url': 'https://www.geograph.org.uk/photo/%d' %
                                    gridimage_id,
                             'format': 'json'})
    r.raise_for_status()
    j = r.json()
    return j

def get_geograph_full_url(gridimage_id, info):
    # Evil hack, but better than digging it out of HTML.
    m = re.search(r"_([0-9a-f]{8})\.jpg$", info['url'])
    if not m:
        raise StrangeURL(info['url'])
    imgkey = m.group(1)
    return ("https://www.geograph.org.uk/reuse.php?" +
            urlencode({'id': gridimage_id,
                       'download': imgkey,
                       'size': 'original'}))

def RossUploads(parameters = None, **kwargs):
    if parameters == None: parameters = { }
    parameters['gaiuser'] = 'Ross4587'
    parameters['gaisort'] = 'timestamp'
    print(parameters)
    return api.PageGenerator("allimages", parameters=parameters, **kwargs)

def find_undersized():
    for item in RossUploads():
        fi = item.latest_file_info
        tree = mwparserfromhell.parse(item.text)
        try:
            geograph_template = tlgetone(tree, ['Geograph'])
        except IndexError:
            continue
        gridimage_id = int(str(geograph_template.get(1).value))
        commons_author = str(geograph_template.get(2).value)
        if commons_author != "Ross Watson": continue
        c = geodb.cursor()
        c.execute("""
            SELECT * FROM gridimage_size
               WHERE gridimage_id = ?
            """, (gridimage_id,))
        row = c.fetchone()
        gi = get_geograph_info(gridimage_id)
        if row['original_width'] <= fi.width: continue
        uploadurl = "https://commons.wikimedia.org/w/index.php?" + urlencode(
            {'title': 'Special:Upload',
             'wpDestFile': item.title(underscore=True, withNamespace=False),
             'wpForReUpload': '1',
             'wpSourceType': 'url',
             'wpUploadFileURL': get_geograph_full_url(gridimage_id, gi),
             'wpUploadDescription': 'Higher-resolution version from Geograph'})
        print("* [%s %d × %d → %d × %d] %s" %
              (uploadurl, fi.width, fi.height,
               row['original_width'], row['original_height'],
               item.title(asLink=True, textlink=True)))


find_undersized()
