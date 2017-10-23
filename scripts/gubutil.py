# Useful stuff for all tasks of Geograph Update Bot.

from functools import partial

# Template searching functions.

def titlematch(a, b):
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
    return int(str(tlgetone(tree, geographtls).get(1)))
