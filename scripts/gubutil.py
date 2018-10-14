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
