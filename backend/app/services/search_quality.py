"""Shared multilingual intent and evidence rules for automatic collection."""
import re
import unicodedata

from bs4 import BeautifulSoup

LANGUAGES = {'auto': 'Otomatik / çok dilli', 'tr': 'Türkçe', 'en': 'İngilizce', 'de': 'Almanca', 'fr': 'Fransızca', 'es': 'İspanyolca', 'ar': 'Arapça'}
REGIONS = {'auto': 'us-en', 'tr': 'tr-tr', 'en': 'us-en', 'de': 'de-de', 'fr': 'fr-fr', 'es': 'es-es', 'ar': 'sa-ar'}
ROLES = {
    'cto': ['CTO', 'chief technology officer', 'teknoloji direktörü', 'teknik direktör'],
    'founder': ['founder', 'cofounder', 'co-founder', 'kurucu', 'kurucular', 'kuruculari', 'girişimci', 'Gründer', 'Gründerin', 'Fondateur', 'Fondatrice', 'Fundador', 'Fundadora', 'مؤسس'],
    'professor': ['professor', 'prof', 'dr', 'profesör', 'akademisyen', 'academic', 'faculty', 'researcher', 'scientist', 'lecturer', 'öğretim', 'professeur', 'profesor', 'أستاذ'],
    'chef': ['chef', 'executive chef', 'şef', 'aşçı', 'gastronomi', 'koch', 'طاه'],
    'doctor': ['doctor', 'doktor', 'arzt', 'médecin', 'médico', 'طبيب'],
    'engineer': ['engineer', 'mühendis', 'muhendis', 'ingenieur', 'ingénieur', 'ingeniero', 'مهندس'],
}
TRANSLATIONS = {
 'cto': ['CTO'] * 6,
 'founder': ['kurucu', 'founder', 'Gründer', 'fondateur', 'fundador', 'مؤسس'],
 'professor': ['akademisyen', 'professor university', 'Professor', 'professeur', 'profesor', 'أستاذ'],
 'chef': ['şef', 'chef', 'Koch', 'chef', 'chef', 'طاه'],
 'doctor': ['doktor', 'doctor', 'Arzt', 'médecin', 'médico', 'طبيب'],
 'engineer': ['mühendis', 'engineer', 'Ingenieur', 'ingénieur', 'ingeniero', 'مهندس'],
}

def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', (value or '').casefold().replace('ı', 'i')) if not unicodedata.combining(c))

def contains(text, phrase):
    return bool(re.search(r'(?<!\w)' + re.escape(normalize(phrase)) + r'(?!\w)', normalize(text)))

def roles_in(text):
    return {role for role, aliases in ROLES.items() if any(contains(text, alias) for alias in aliases)}

def requested_roles(research):
    target = roles_in(research.target_type)
    context = roles_in(' '.join([getattr(research, 'description', '') or '', getattr(research, 'notes', '') or '']))
    # Explicit leadership requests take precedence over a broad engineer/expert form value.
    if context & {'cto', 'founder'} and (not target or target <= {'engineer', 'cto', 'founder'}):
        return context & {'cto', 'founder'}
    return target

def language_matches(html, language):
    if language == 'auto':
        return True
    root = BeautifulSoup(html, 'html.parser').find('html')
    declared = (root.get('lang', '') if root else '').lower().replace('_', '-').split('-')[0]
    return not declared or declared == language

def job_listing(value):
    return any(contains(value, phrase) for phrase in ('iş ilanları', 'is ilanlari', 'iş fırsatları', 'job openings', 'jobs in', 'engineering jobs', 'software jobs', 'vacancies', 'stellenangebote', 'offres emploi', 'ofertas empleo', 'وظائف'))
