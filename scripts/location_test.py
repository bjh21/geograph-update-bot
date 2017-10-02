from __future__ import division, print_function, unicode_literals

import unittest
from location import bng, ig, location_from_grid, location_from_row, en_from_gr

class FromGridTests(unittest.TestCase):
    def test_from_grid(self):
        a = location_from_grid(bng, 380980, 201340, 8, 292, True)
        self.assertEqual(a,
            '{{Location|51.71051|-2.2766|source:geograph_heading:292|prec=70}}')

class GridLetterTests(unittest.TestCase):
    def test_bng(self):
        self.assertEqual(en_from_gr('SO8318'), (383000, 218000))
    def test_ig(self):
        self.assertEqual(en_from_gr('G6035'), (160000, 335000))
        
class FromRowTests(unittest.TestCase):
    def setUp(self):
        self.full_row = dict(gridimage_id=4,
            grid_reference='SO8001', reference_index=1,
            nateastings=380930, natnorthings=201360, natgrlen='8',
            viewpoint_eastings=380980, viewpoint_northings=201340,
            viewpoint_grlen='8', view_direction=292, use6fig=1)
        self.min_row = dict(gridimage_id=5,
            grid_reference='SO8201', reference_index=1,
            nateastings=0, natnorthings=0, natgrlen='4',
            viewpoint_eastings=0, viewpoint_northings=0,
            viewpoint_grlen='0', view_direction=-1, use6fig=0)
        self.mid_row = dict(gridimage_id=2913,
            grid_reference='W2076', reference_index=2,
            nateastings=120800, natnorthings=76500, natgrlen='6',
            viewpoint_eastings=0, viewpoint_northings=0,
            viewpoint_grlen='0', view_direction=-1, use6fig=0)
        self.high_row = dict(gridimage_id=715,
            grid_reference='SO8474', reference_index=1,
            nateastings=0, natnorthings=0, natgrlen='4',
            viewpoint_eastings=384732, viewpoint_northings=274929,
            viewpoint_grlen='10', view_direction=-1, use6fig=0)
    def test_full_row(self):
        s = str(location_from_row(self.full_row))
        self.assertEqual(s,
            "{{Location|51.71051|-2.2766|source:geograph_heading:292|prec=70}}")
    def test_minimal_row(self):
        s = str(location_from_row(self.min_row))
        self.assertEqual(s,
            "{{Object location|51.712|-2.25|source:geograph|prec=700}}")
    def test_medium_row(self):
        s = str(location_from_row(self.mid_row))
        self.assertEqual(s,
            "{{Object location|51.9360|-9.152|source:geograph|prec=70}}")
    def test_high_row(self):
        s = str(location_from_row(self.high_row))
        self.assertEqual(s,
            "{{Location|52.372194|-2.22568|source:geograph|prec=0.7}}")
        
if __name__ == '__main__':
    unittest.main()
