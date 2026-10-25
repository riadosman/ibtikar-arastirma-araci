import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.collection import run_next
from app.services.discovery import PublicSearchProvider, SearchHit, build_queries
from app.services.extraction import extract_profiles, person_name
from app.services.search_quality import REGIONS, language_matches

CASES = json.loads((Path(__file__).parent / 'fixtures/search_cases_100.json').read_text(encoding='utf-8'))

@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'] + '-' + c['category'])
def test_fictional_corpus_through_collection(auth, case):
    endpoint = '/api/v1/research-requests'
    response = auth.post(endpoint, json=case['research'])
    assert response.status_code == 201, response.text
    rid = response.json()['id']
    assert response.json()['search_language'] == case['research']['search_language']
    assert auth.post(f'{endpoint}/{rid}/collect').status_code == 202
    class Search:
        def discover(self, query, limit, page=1):
            return [SearchHit(case['url'], case['title'], '')]
    class Fetch:
        def fetch(self, url):
            return url, case['html'].encode('utf-8')
    assert run_next(Search(), Fetch())
    actual = auth.get(f'{endpoint}/{rid}/candidates').json()['items']
    assert sorted(p['full_name'] for p in actual) == sorted(case['expected'])
    state = auth.get(f'{endpoint}/{rid}/collection').json()
    assert state['job']['status'] == ('COMPLETED' if case['expected'] else 'NO_RESULTS')

@pytest.mark.parametrize('language', ['tr','en','de','fr','es','ar'])
def test_language_role_intent_and_persistence(auth, language):
    brief = {**CASES[0]['research'], 'target_type': 'Muhendis', 'description': 'bir cto veya teknik sirket kuruculari', 'search_language': language, 'field': 'IT'}
    research = SimpleNamespace(**brief, notes='')
    queries = build_queries(research)
    assert any('CTO' in q for q in queries)
    assert not any('Muhendis' in q or 'biyografi' in q for q in queries) if language != 'tr' else True
    assert PublicSearchProvider(language).region == REGIONS[language]
    response = auth.post('/api/v1/research-requests', json=brief)
    assert response.status_code == 201
    rid = response.json()['id']
    payload = {**brief, 'status': 'CREATED'}
    payload.pop('search_language')
    assert auth.patch(f'/api/v1/research-requests/{rid}', json=payload).json()['search_language'] == language
    page = auth.get(f'/panel/research/{rid}/edit')
    assert page.status_code == 200
    assert f'value="{language}" selected' in page.text

def test_language_validation_and_unicode_names(auth):
    assert auth.post('/api/v1/research-requests', json={**CASES[0]['research'], 'search_language': 'unknown'}).status_code == 422
    assert not language_matches('<html lang="tr-TR">', 'en')
    assert language_matches('<html lang="en-US">', 'en')
    assert language_matches('<html>', 'en')
    assert person_name('İstanbul Mühendis İş İlanları') is None
    assert person_name('Steve Jobs') == 'Steve Jobs'
    assert person_name('أحمد حسن') == 'أحمد حسن'

def test_personal_homepage_with_adjacent_role_and_no_name_in_path():
    html = '<title>Deniz Acar | CTO</title><h1>Deniz Acar</h1><h2>Chief Technology Officer based in Istanbul</h2>'
    people = extract_profiles(html, 'https://denizacar.example/', 'Deniz Acar | CTO')[1]
    assert len(people) == 1 and people[0].full_name == 'Deniz Acar'
    assert people[0].source_type == 'profile_intro'
    assert extract_profiles(html.replace('<h2>', '<footer><h2>').replace('</h2>', '</h2></footer>'), 'https://denizacar.example/')[1] == []

def test_provider_sends_selected_region(monkeypatch):
    from app.services import discovery
    captured = {}
    class Engine:
        def __init__(self, **kwargs): pass
        def text(self, query, **kwargs):
            captured.update(kwargs)
            return []
    monkeypatch.setattr(discovery, 'DDGS', Engine)
    PublicSearchProvider('de').discover('Istanbul CTO', 10)
    assert captured['region'] == 'de-de'

def test_source_in_another_language_is_kept_with_a_note(auth):
    # The search language is a preference: Istanbul universities' English staff pages and
    # Turkish sites that declare lang="en" must not vanish from a Turkish search.
    case = CASES[0]
    brief = {**case['research'], 'search_language': 'en'}
    rid = auth.post('/api/v1/research-requests', json=brief).json()['id']
    endpoint = f'/api/v1/research-requests/{rid}'
    auth.post(endpoint + '/collect')
    class Search:
        def discover(self, query, limit, page=1): return [SearchHit(case['url'], case['title'], '')]
    class Fetch:
        def fetch(self, url): return url, case['html'].encode('utf-8')
    run_next(Search(), Fetch())
    names = [c['full_name'] for c in auth.get(endpoint + '/candidates').json()['items']]
    assert names == case['expected']
    source = auth.get(endpoint + '/collection').json()['sources'][0]
    assert source['status'] == 'EXTRACTED' and 'dili' in source['error']
