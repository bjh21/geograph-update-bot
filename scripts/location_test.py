from __future__ import division, print_function, unicode_literals

import unittest
from gubutil import tlgetone
from location import (bng, ig, location_from_grid, location_from_row,
                      object_location_from_row,
                      en_from_gr, bngr_from_en, format_row,
                      set_location, set_object_location,
                      get_location, get_object_location,
                      statement_matches_template)
import mwparserfromhell
from mwparserfromhell.nodes.template import Template

class FromGridTests(unittest.TestCase):
    def test_from_grid(self):
        a = location_from_grid(bng, 380980, 201340, 8, 292, True)
        self.assertEqual(a,
            '{{Location|51.71051|-2.2766|'
            'source:geograph-osgb36(SO80980134)_region:GB-EAW_heading:292|'
            'prec=100}}')

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
            "source:geograph-osgb36(SO80980134)_region:GB-EAW_heading:292|"
            "prec=100}}")
        f = format_row(self.full_row)
        self.assertEqual(f,
            "subject SO80930136; viewpoint SO80980134; looking WNW; "
                         "use6fig; geograph")
    def test_minimal_row(self):
        self.assertEqual(location_from_row(self.min_row), None)
        s = str(object_location_from_row(self.min_row))
        self.assertEqual(s,
            "{{Object location|51.712|-2.25|"
            "source:geograph-osgb36(SO8201)_region:GB-EAW|prec=1000}}")
        f = format_row(self.full_row)
        self.assertEqual(f,
            "subject SO80930136; viewpoint SO80980134; looking WNW; "
                         "use6fig; geograph")
    def test_low_row(self):
        self.assertEqual(location_from_row(self.low_row), None)
        s = str(object_location_from_row(self.low_row))
        self.assertEqual(s,
            "{{Object location|55.174|-4.93|"
            "source:geograph-osgb36(NX1390)_heading:225|prec=1000}}")
        f = format_row(self.low_row)
        self.assertEqual(f,
            "subject NX1390; viewpoint NX1390; looking SW; geograph")
    def test_medium_row(self):
        s = str(object_location_from_row(self.mid_row))
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
            "source:geograph-osgb36(SO8473274929)_region:GB-EAW|prec=1}}")
        f = format_row(self.high_row)
        self.assertEqual(f,
            "subject SO8474; viewpoint SO8473274929; geograph")
    def test_high_row(self):
        s = str(object_location_from_row(self.supp_row))
        self.assertEqual(s,
            "{{Object location|50.615|-2.23|"
            "source:geograph-osgb36(SY8379)|prec=1000}}")
        f = format_row(self.supp_row)
        self.assertEqual(f,
            "subject SY8379")

class EditingTest1(unittest.TestCase):
    def setUp(self):
        self.tree = mwparserfromhell.parse("{{Information}}\n{{location dec}}")
    def test_loc(self):
        loc = Template('Location')
        loc.add(1, "one")
        set_location(self.tree, loc)
        self.assertEqual(str(self.tree), "{{Information}}\n{{Location|one}}")
    def test_objloc(self):
        loc = Template('Object location')
        loc.add(1, "one")
        set_object_location(self.tree, loc)
        self.assertEqual(str(self.tree), "{{Information}}\n{{location dec}}\n{{Object location|one}}")

class EditingTest2(unittest.TestCase):
    def setUp(self):
        self.tree = mwparserfromhell.parse("{{object location}}")
    def test_loc(self):
        loc = Template('Location')
        loc.add(1, "one")
        set_location(self.tree, loc)
        self.assertEqual(str(self.tree), "{{Location|one}}\n{{object location}}")
    def test_objloc(self):
        loc = Template('Object location')
        loc.add(1, "one")
        set_object_location(self.tree, loc)
        self.assertEqual(str(self.tree), "{{Object location|one}}")

class EditingTest3(unittest.TestCase):
    def setUp(self):
        self.tree = mwparserfromhell.parse(
"""
== {{int:filedesc}} ==
{{Information
|description={{en|1=Street Waste Bin Waste bin on the street outside Crosby and Blundellsands Station}}
|date=2010-04-11
|source=From [http://www.geograph.org.uk/photo/1801330 geograph.org.uk]
|author=[http://www.geograph.org.uk/profile/46411 Paul Glover]
|permission=
|other_versions=
}}
{{Location dec|53.487763|-3.040917}}

== {{int:license-header}} ==
{{Geograph|1801330|Paul Glover}}

[[Category:Streets in Sefton]]
[[Category:Geograph images in Merseyside]]
""")
    def test_loc_objloc(self):
        loc = Template('Object location')
        loc.add(1, "one")
        set_location(self.tree, None)
        set_object_location(self.tree, loc)
        # Might be better without the spurious newline, but this will do.
        self.assertEqual(str(self.tree),
"""
== {{int:filedesc}} ==
{{Information
|description={{en|1=Street Waste Bin Waste bin on the street outside Crosby and Blundellsands Station}}
|date=2010-04-11
|source=From [http://www.geograph.org.uk/photo/1801330 geograph.org.uk]
|author=[http://www.geograph.org.uk/profile/46411 Paul Glover]
|permission=
|other_versions=
}}
{{Object location|one}}


== {{int:license-header}} ==
{{Geograph|1801330|Paul Glover}}

[[Category:Streets in Sefton]]
[[Category:Geograph images in Merseyside]]
""")

class SDCEqualityTests(unittest.TestCase):
    def setUp(self):
        # These come from File:Dun Gallain (geograph 1855936).jpg
        self.templates = mwparserfromhell.parse("""
{{Location|56.05814|-6.2592|source:geograph-osgb36(NR34949321)_heading:202|prec=100}}
{{Object location|56.05694|-6.2600|source:geograph-osgb36(NR34889308)_heading:202|prec=100}}
""")
        self.sdc = {
            "statements": {
                "P1259": [
                    {
                        "mainsnak": {
                            "snaktype": "value",
                            "property": "P1259",
                            "hash": "bd6d05faaed76842fa29c241627838d506dfe603",
                            "datavalue": {
                                "value": {
                                    "latitude": 56.05814,
                                    "longitude": -6.2592,
                                    "altitude": None,
                                    "precision": 1.0e-5,
                                    "globe": "http://www.wikidata.org/entity/Q2"
                                },
                                "type": "globecoordinate"
                            }
                        },
                        "type": "statement",
                        "qualifiers": {
                            "P7787": [
                                {
                                    "snaktype": "value",
                                    "property": "P7787",
                                    "hash": "e53735673ad2bfdddb52501fe7abfd7539923afb",
                                    "datavalue": {
                                        "value": {
                                            "amount": "+202",
                                            "unit": "http://www.wikidata.org/entity/Q28390"
                                        },
                                        "type": "quantity"
                                    }
                                }
                            ]
                        },
                        "qualifiers-order": [
                            "P7787"
                        ],
                        "id": "M87185965$7A4DC13E-49A9-4BE2-AA8B-A27F42CD0C69",
                        "rank": "normal"
                    }
                ],
                "P625": [
                    {
                        "mainsnak": {
                            "snaktype": "value",
                            "property": "P625",
                            "hash": "d51d0bf4d806fff7610428a20b9462eb8db3eb2b",
                            "datavalue": {
                                "value": {
                                    "latitude": 56.05694,
                                    "longitude": -6.26,
                                    "altitude": None,
                                    "precision": 1.0e-5,
                                    "globe": "http://www.wikidata.org/entity/Q2"
                                },
                                "type": "globecoordinate"
                            }
                        },
                        "type": "statement",
                        "id": "M87185965$5F1AB790-6C68-4910-9577-2EF1BB7CA329",
                        "rank": "normal"
                    }
                ]
            }
        }        
    def test_match_camera(self):
        self.assertTrue(
            statement_matches_template(self.sdc['statements']['P1259'][0],
                                      get_location(self.templates)))
    def test_match_object(self):
        self.assertTrue(
            statement_matches_template(self.sdc['statements']['P625'][0],
                                      get_object_location(self.templates)))
    def test_nomatch_lat(self):
        (self.sdc['statements']['P1259'][0]['mainsnak']
         ['datavalue']['value']['latitude']) += 1
        self.assertFalse(
            statement_matches_template(self.sdc['statements']['P1259'][0],
                                      get_location(self.templates)))
    def test_nomatch_hdg(self):
        (self.sdc['statements']['P1259'][0]['qualifiers']['P7787'][0]
         ['datavalue']['value']['amount']) = '+1'
        self.assertFalse(
            statement_matches_template(self.sdc['statements']['P1259'][0],
                                      get_location(self.templates)))
    def test_nomatch_globe(self):
        (self.sdc['statements']['P1259'][0]['mainsnak']
         ['datavalue']['value']['globe']) = (
             "http://www.wikidata.org/entity/Q19907")
        self.assertFalse(
            statement_matches_template(self.sdc['statements']['P1259'][0],
                                      get_location(self.templates)))

        
if __name__ == '__main__':
    unittest.main()
