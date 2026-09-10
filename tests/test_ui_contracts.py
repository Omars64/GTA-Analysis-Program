"""Regression contracts for explicit scans, vehicle lookup and forgiving search."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from bs4 import BeautifulSoup
from knowledge_engine import answer_query
from vehicle_intelligence import enrich_vehicles, looks_like_vehicle
from vehicle_profiles import parse_profile, get_profile, BASES


class InterfaceContracts(unittest.TestCase):
    def test_current_and_legacy_vehicle_urls(self):
        for name, expected in [('Karin Woodlander', BASES[0] + 'woodlander'), ('Western Company Seabreeze', BASES[1] + 'western-seabreeze')]:
            soup = BeautifulSoup(f'<title>{name} | GTA 5 Online Vehicle Stats</title><meta property="og:image" content="https://example.com/vehicle.jpg">', 'html.parser')
            def fetch(url):
                if url == expected:
                    return soup
                raise ValueError('Page not found')
            with patch('vehicle_profiles.store') as storage, patch('vehicle_profiles.get_soup', side_effect=fetch):
                storage.get.return_value = {'available': False, 'checked_at': 9999999999}
                profile = get_profile(name)
            self.assertTrue(profile['available'])
            self.assertEqual(profile['source_url'], expected)
            self.assertTrue(profile['image_urls'])

    def test_typo_search(self):
        data = {'sections': {'Podium Vehicle': [{'item': 'Declasse Impaler SZ', 'details': 'Casino'}], 'Discounts': [{'item': 'Ocelot Jugular', 'details': '40% off'}]}}
        self.assertIn('Impaler', answer_query('what is the podum vehcle', data)['answer'])
        self.assertIn('Jugular', answer_query('ocelto juglar discount', data)['answer'])
        self.assertEqual(answer_query('quantum banana', data)['matches'], [])

    def test_vehicle_groups_and_challenges(self):
        self.assertFalse(looks_like_vehicle('Prize Ride', 'Place Top 2 in the LS Car Meet Series.', []))
        with patch('vehicle_intelligence.resolve_image', return_value=(None, 'placeholder')):
            rows = enrich_vehicles([{'category': 'Test Rides', 'item': 'Pfister Astron, Ocelot Jugular, and Canis Kamacho'}], {})
        self.assertEqual([r['name'] for r in rows], ['Pfister Astron', 'Ocelot Jugular', 'Canis Kamacho'])

    def test_sourced_profile_and_wrong_model(self):
        soup = BeautifulSoup('''<title>Declasse Impaler SZ | GTA 5 Online Vehicle Stats, Price, How To Get</title>
        <meta property="og:image" content="https://example.com/impaler.jpg">
        <div class="field-entry"><span class="field-label">Top Speed</span><span class="field-value">117 mph</span></div>
        <div class="gta5-stats"><div class="field-entry"><span class="field-label">Speed</span><span class="field-value">77.26</span></div></div>
        <div class="field-entry explosive-resistance"><div class="field-value"><p class="field-prefix">100% armor, occupied</p><table><tr><td>RPG</td><td>1</td></tr></table></div></div>''', 'html.parser')
        profile = parse_profile(soup, 'https://www.gtabase.com/vehicle', 'Declasse Impaler SZ')
        self.assertEqual(profile['performance']['Speed'], 77.26)
        self.assertEqual(profile['fields']['Top Speed'], '117 mph')
        self.assertEqual(profile['durability'][0]['hits'], '1')
        self.assertIn('occupied', profile['durability_conditions'])
        self.assertIsNone(parse_profile(soup, 'https://www.gtabase.com/vehicle', 'Declasse Impaler'))
