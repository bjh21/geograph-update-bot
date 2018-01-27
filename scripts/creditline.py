from __future__ import division, print_function, unicode_literals

import mwparserfromhell
from mwparserfromhell import parse
from mwparserfromhell.nodes import Tag, Template, Text
from mwparserfromhell.nodes.extras import Parameter
from mwparserfromhell.wikicode import Wikicode

import re

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
