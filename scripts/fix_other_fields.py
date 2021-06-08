#! /usr/bin/python3

import pywikibot
from pywikibot import pagegenerators, bot
from pywikibot.bot import SingleSiteBot, ExistingPageBot, NoRedirectPageBot
import mwparserfromhell

from gubutil import tlgetone
from creditline import infoboxes, otherfieldses

class FixOtherFieldsBot (SingleSiteBot, ExistingPageBot, NoRedirectPageBot):
    def treat_page(self):
        t = mwparserfromhell.parse(self.current_page.text)
        info = tlgetone(t, infoboxes)
        others = [f for f in otherfieldses if info.has(f)]
        if len(others) > 1:
            bot.warning("excess other_fields in %s" % (self.current_page,))

def main(*args):
    local_args = pywikibot.handle_args(args)
    genFactory = pywikibot.pagegenerators.GeneratorFactory()
    for arg in local_args:

        # Catch the pywikibot.pagegenerators options
        if genFactory.handle_arg(arg):
            continue  # nothing to do here
    gen = genFactory.getCombinedGenerator(preload=True)
    if gen:
        # pass generator and private options to the bot
        bot = FixOtherFieldsBot()
        bot.generator = gen
        bot.run()  # guess what it does
        return True
    else:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False

main()
