import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from intelligence_engine import _merge_rows
from vehicle_intelligence import enrich_vehicles
from knowledge_engine import answer_query
from gta_weekly_scraper import parse_weekly_soup
from bs4 import BeautifulSoup

class CoreTests(unittest.TestCase):
    def test_consensus_merge(self):
        a={'url':'https://a','provider':'A','label':'A'}; b={'url':'https://b','provider':'B','label':'B'}
        rows=_merge_rows([(a,[{'category':'Podium Vehicle','item':'Grotti Turismo Omaggio','details':'Casino','source_url':'https://a'}]),(b,[{'category':'Podium Vehicle','item':'Grotti Turismo Omaggio','details':'Lucky Wheel Casino','source_url':'https://b'}])])
        self.assertEqual(len(rows),1); self.assertTrue(rows[0]['verified']); self.assertEqual(rows[0]['source_count'],2)
    def test_vehicle_enrichment(self):
        rows=[{'category':'Podium Vehicle','item':'Grotti Turismo Omaggio','details':'Casino','confidence':.9,'verified':True,'source_count':2,'source_urls':[]}]
        rows[0]['source_urls']=['fixture://weekly']
        vehicles=enrich_vehicles(rows,{'fixture://weekly':[{'url':'https://example.invalid/turismo.jpg','text':'Grotti Turismo Omaggio vehicle'}]})
        self.assertEqual(vehicles[0]['manufacturer'],'Grotti')
    def test_structural_extractor(self):
        html='<article><h2>Podium Vehicle</h2><p>Grotti Turismo Omaggio</p><h2>Bonuses</h2><ul><li>3x GTA$ and RP on Community Series</li></ul></article>'
        rows=parse_weekly_soup(BeautifulSoup(html, 'html.parser'),'fixture://weekly')
        self.assertTrue(any(r['category']=='Podium Vehicle' and 'Turismo' in r['item'] for r in rows))
        self.assertTrue(any(r['category']=='Bonuses' for r in rows))
    def test_grounded_query(self):
        data={'sections':{'Podium Vehicle':[{'item':'Test Car','details':''}]},'vehicles':[]}
        self.assertIn('Test Car',answer_query('podium vehicle',data)['answer'])
if __name__=='__main__': unittest.main()
