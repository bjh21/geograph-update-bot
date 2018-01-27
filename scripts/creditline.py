from __future__ import division, print_function, unicode_literals

import mwparserfromhell
from mwparserfromhell import parse
from mwparserfromhell.nodes import Tag, Template, Text
from mwparserfromhell.wikicode import Wikicode

def creditline_from_row(row):
    t = Template(parse('Credit line'))
    t.add("Author", Text(row['realname']))
    title = Text(row['title'])
    if ("''" in title or '}}' in title or '|' in title or '[[' in title):
        title = Tag('nowiki', title)
    t.add("Other", Tag('i', title, wiki_markup="''"))
    t.add("License",
        parse('[https://creativecommons.org/licenses/by-sa/2.0/ CC BY-SA 2.0]'))
    return t
