from __future__ import division, print_function, unicode_literals

import unittest

import mwparserfromhell
from mwparserfromhell.nodes import Template

from creditline import add_creditline

class EditingTest(unittest.TestCase):
    def test_simple(self):
        t = mwparserfromhell.parse("{{Information\n|author=me\n}}")
        cl = mwparserfromhell.parse("{{Credit line\n |Author = me\n }}")
        add_creditline(t, cl)
        self.assertEqual(str(t),
            "{{Information\n|author=me\n"
            "|other fields={{Credit line\n |Author = me\n }}\n}}")
    def test_otherfields(self):
        t = mwparserfromhell.parse("{{Information\n|author=me\n"
                                   "|Other_fields={{address|foo}}\n}}")
        cl = mwparserfromhell.parse("{{Credit line\n |Author = me\n }}")
        add_creditline(t, cl)
        self.assertEqual(str(t),
            "{{Information\n|author=me\n"
            "|Other_fields={{address|foo}}\n {{Credit line\n |Author = me\n }}\n}}")

if __name__ == '__main__':
    unittest.main()
