from __future__ import division, print_function, unicode_literals

import mwparserfromhell
from mwparserfromhell import parse
from mwparserfromhell.nodes import Tag, Template, Text
from mwparserfromhell.nodes.extras import Parameter
from mwparserfromhell.wikicode import Wikicode

import re

from gubutil import tlgetall, tlgetone, canonicalise_name, TooManyTemplates

def wikify(x):
    # Convert a string from the Geograph database into Wikicode.
    x = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), x)
    if ("''" in x or '}}' in x or '|' in x or '[[' in x):
        return Tag('nowiki', Text(x))
    return Text(x)

def creditline_from_row(row):
    t = Template(parse('Credit line\n '))
    t.add("DUMMY ", " VALUE\n ") # to set the formatting
    t.add("Author", wikify(row['realname']))
    t.add("Other", Tag('i', wikify(row['title']), wiki_markup="''"))
    t.add("License",
        parse('[https://creativecommons.org/licenses/by-sa/2.0/ CC BY-SA 2.0]'))
    t.remove("DUMMY")
    return t

def otherfields_from_row(row):
    return Parameter("other fields", creditline_from_row(row))

# Known infobox templates
# https://commons.wikimedia.org/wiki/Commons:Infobox_templates
infoboxes = ("Information", "Artwork", "Photograph", "Art photo", "Book",
             "Map", "Musical work", "Information2", "COAInformation",
             "Bus-Information", "Infobox aircraft image", "Spoken article",
             "Specimen")

otherfieldses = ("Other fields", "Other_fields", "other fields",
                 "Other_fields")

def add_creditline(t, line):
    assert(len(tlgetall(t, ['Credit line'])) == 0)
    info = tlgetone(t, infoboxes)
    for f in otherfieldses:
        if info.has(f):
            otherfields = info.get(f)
            otherfields.value.append(Text(" "))
            otherfields.value.append(line)
            otherfields.value.append(Text("\n"))
            return
    info.add("other fields", line)

def can_add_creditline(t, line):
    if len(tlgetall(t, ['Credit line'])) != 0:
        return False # Already have a credit line
    try:
        geo = tlgetone(t, ['Geograph'])
    except IndexError:
        return False
    except TooManyTemplates:
        return False
    geo_author = geo.get(2).value
    cl_author = line.get('Author').value
    if canonicalise_name(geo_author) != canonicalise_name(cl_author):
        # Don't add a credit line with wrong author
        return False
    return True
