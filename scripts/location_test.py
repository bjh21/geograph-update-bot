import unittest
from location import bng, ig, location_from_grid, location_from_row, en_from_gr

class FromGridTests(unittest.TestCase):
    def test_from_grid(self):
        a = location_from_grid(bng, 380980, 201340, 8, 292, True)
        self.assertEqual(a,
            ['51.71051', '-2.2766', 'source:geograph_heading:292', 'prec=70'])

class GridLetterTests(unittest.TestCase):
    def test_bng(self):
        self.assertEqual(en_from_gr('SO8318'), (383000, 218000))
    def test_ig(self):
        self.assertEqual(en_from_gr('G6035'), (160000, 335000))
        
class FromRowTests(unittest.TestCase):
    def setUp(self):
        self.full_row = dict(
            grid_reference='SO8001', reference_index=1,
            nateastings=380930, natnorthings=201360, natgrlen='8',
            viewpoint_eastings=380980, viewpoint_northings=201340,
            viewpoint_grlen='8', view_direction=292, use6fig=1)
        self.min_row = dict(
            grid_reference='SO8201', reference_index=1,
            nateastings=0, natnorthings=0, natgrlen='4',
            viewpoint_eastings=0, viewpoint_northings=0,
            viewpoint_grlen='0', view_direction=-1, use6fig=0)
    def test_full_row(self):
        s = str(location_from_row(self.full_row))
        self.assertEqual(s,
            "{{Location|51.71051|-2.2766|source:geograph_heading:292|prec=70}}")
    def test_minimal_row(self):
        s = str(location_from_row(self.min_row))
        self.assertEqual(s,
            "{{Location|51.711956|-2.254684|source:geograph|prec=700}}")
        
if __name__ == '__main__':
    unittest.main()
