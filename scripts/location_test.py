from __future__ import division, print_function, unicode_literals

import unittest
from location import (bng, ig, location_from_grid, location_from_row,
                      en_from_gr, bngr_from_en, format_row)

class FromGridTests(unittest.TestCase):
    def test_from_grid(self):
        a = location_from_grid(bng, 380980, 201340, 8, 292, True)
        self.assertEqual(a,
            '{{Location|51.71051|-2.2766|'
            'source:geograph-osgb36(SO80980134)_heading:292|prec=100}}')

class GridLetterTests(unittest.TestCase):
    def test_bng(self):
        self.assertEqual(en_from_gr('SO8318'), (383000, 218000))
    def test_ig(self):
        self.assertEqual(en_from_gr('G6035'), (160000, 335000))
    def test_bng_reverse(self):
        self.assertEqual(bngr_from_en(380930, 201360, 6), "SO809013")
        
class FromRowTests(unittest.TestCase):
    def setUp(self):
        self.full_row = dict(gridimage_id=4, moderation_status='geograph',
            grid_reference='SO8001', reference_index=1,
            nateastings=380930, natnorthings=201360, natgrlen='8',
            viewpoint_eastings=380980, viewpoint_northings=201340,
            viewpoint_grlen='8', view_direction=292, use6fig=1)
        self.min_row = dict(gridimage_id=5, moderation_status='geograph',
            grid_reference='SO8201', reference_index=1,
            nateastings=0, natnorthings=0, natgrlen='4',
            viewpoint_eastings=0, viewpoint_northings=0,
            viewpoint_grlen='0', view_direction=-1, use6fig=0)
        self.low_row = dict(gridimage_id=1803781, moderation_status='geograph',
            grid_reference='NX1390', reference_index=1,
            nateastings=0, natnorthings=0, natgrlen='4',
            viewpoint_eastings=213000, viewpoint_northings=590000,
            viewpoint_grlen='4', view_direction=225, use6fig=1)
        self.mid_row = dict(gridimage_id=2913, moderation_status='geograph',
            grid_reference='W2076', reference_index=2,
            nateastings=120800, natnorthings=76500, natgrlen='6',
            viewpoint_eastings=0, viewpoint_northings=0,
            viewpoint_grlen='0', view_direction=-1, use6fig=0)
        self.high_row = dict(gridimage_id=715, moderation_status='geograph',
            grid_reference='SO8474', reference_index=1,
            nateastings=0, natnorthings=0, natgrlen='4',
            viewpoint_eastings=384732, viewpoint_northings=274929,
            viewpoint_grlen='10', view_direction=-1, use6fig=0)
        self.supp_row = dict(gridimage_id=15, moderation_status='accepted',
            grid_reference='SY8379', reference_index=1,
            nateastings=0, natnorthings=0, natgrlen='4',
            viewpoint_eastings=0, viewpoint_northings=0,
            viewpoint_grlen='0', view_direction=-1, use6fig=0)
    def test_full_row(self):
        s = str(location_from_row(self.full_row))
        self.assertEqual(s,
            "{{Location|51.71051|-2.2766|"
            "source:geograph-osgb36(SO80980134)_heading:292|prec=100}}")
        f = format_row(self.full_row)
        self.assertEqual(f,
            "subject SO80930136; viewpoint SO80980134; 292°; use6fig; geograph")
    def test_minimal_row(self):
        s = str(location_from_row(self.min_row))
        self.assertEqual(s,
            "{{Location|51.712|-2.25|"
            "source:geograph-osgb36(SO8201)|prec=1000}}")
        f = format_row(self.full_row)
        self.assertEqual(f,
            "subject SO80930136; viewpoint SO80980134; 292°; use6fig; geograph")
    def test_low_row(self):
        s = str(location_from_row(self.low_row))
        self.assertEqual(s,
            "{{Location|55.174|-4.93|"
            "source:geograph-osgb36(NX1390)_heading:225|prec=1000}}")
        f = format_row(self.low_row)
        self.assertEqual(f,
            "subject NX1390; viewpoint NX1390; 225°; geograph")
    def test_medium_row(self):
        s = str(location_from_row(self.mid_row))
        self.assertEqual(s,
            "{{Object location|51.9360|-9.152|"
            "source:geograph-irishgrid(W208765)|prec=100}}")
        f = format_row(self.mid_row)
        self.assertEqual(f,
            "subject W208765; geograph")
    def test_high_row(self):
        s = str(location_from_row(self.high_row))
        self.assertEqual(s,
            "{{Location|52.372194|-2.22568|"
            "source:geograph-osgb36(SO8473274929)|prec=1}}")
        f = format_row(self.high_row)
        self.assertEqual(f,
            "subject SO8474; viewpoint SO8473274929; geograph")
    def test_high_row(self):
        s = str(location_from_row(self.supp_row))
        self.assertEqual(s,
            "{{Object location|50.615|-2.23|"
                         "source:geograph-osgb36(SY8379)|prec=1000}}")
        f = format_row(self.supp_row)
        self.assertEqual(f,
            "subject SY8379")

if __name__ == '__main__':
    unittest.main()
