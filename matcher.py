"""Проверка требования по исходной фразе. Общего графа доменов нет."""
import json
import re
from pathlib import Path

from data import normalize

NEGATION = re.compile(r'\bне\s+(?:занимал|работал|интегрировал|участвовал)\w*|'
                      r'\bнет\s+опыт\w*|\bбез\s+опыт\w*')


def load_cards(path):
    cards = json.loads(Path(path).read_text(encoding='utf-8'))
    for card_id, card in cards.items():
        if not card.get('text') or not card.get('groups'):
            raise ValueError(f'Пустая карточка {card_id}')
        for patterns in card['groups'].values():
            if not patterns:
                raise ValueError(f'Пустое условие в {card_id}')
            for pattern in patterns:
                re.compile(pattern)
    return cards


def _check_clause(phrase, card):
    text = normalize(phrase)
    found = {name: next((match.group() for pattern in patterns if (match := re.search(pattern, text))), None)
             for name, patterns in card['groups'].items()}
    missing = [name for name, match in found.items() if match is None]
    warning = None
    if not missing:
        status = 'contradicted' if NEGATION.search(text) else 'confirmed'
        remainder = re.sub(r'\b(?:не\s+только|not\s+only)\b', '', text)
        if status == 'confirmed' and re.search(r"\b(?:не|нет|никогда|без|not|no|never|without)\b|n['’]t\b", remainder):
            status, warning = 'review', 'Возможное отрицание. Нужен просмотр текста.'
    elif any(found.values()) or any(normalize(term) in text for term in card.get('review_terms', [])):
        status = 'review'
    else:
        status = 'unknown'
    return {'status': status, 'quote': phrase if status != 'unknown' else None,
            'found': found, 'missing': missing, 'warning': warning}


def check_phrase(phrase, card):
    """Сначала отделяем простые части фразы. Это эвристика, не синтаксический разбор."""
    clauses = [s.strip() for s in re.split(r'[;.!?,]|\b(?:но|однако|зато|и)\b', phrase, flags=re.I) if s.strip()]
    checks = [_check_clause(clause, card) for clause in clauses]
    if not checks:
        checks = [_check_clause(phrase, card)]
    priority = {'confirmed': 3, 'contradicted': 2, 'review': 1, 'unknown': 0}
    best = max(checks, key=lambda c: (priority[c['status']], sum(x is not None for x in c['found'].values())))
    statuses = {c['status'] for c in checks}
    if 'confirmed' in statuses and 'contradicted' in statuses:
        best = {**best, 'status': 'review', 'warning': 'Во фразе есть противоречие.'}
    return {**best, 'source_text': phrase}


def check_candidate(units, card):
    checks, seen = [], set()
    for index, unit in enumerate(units):
        item = {'text': unit} if isinstance(unit, str) else unit
        key = (normalize(item['text']), item.get('project_id'))
        if key in seen:
            continue
        seen.add(key)
        checks.append({**check_phrase(item['text'], card), 'unit': index,
                       'project_id': item.get('project_id')})
    statuses = {c['status'] for c in checks}
    if 'confirmed' in statuses and 'contradicted' in statuses:
        best = next(c for c in checks if c['status'] == 'contradicted')
        return {**best, 'status': 'review', 'warning': 'В исходных фразах есть противоречие.'}
    priority = {'confirmed': 3, 'contradicted': 2, 'review': 1, 'unknown': 0}
    if not checks:
        return {'status': 'unknown', 'quote': None, 'found': {}, 'missing': list(card['groups']),
                'unit': None, 'project_id': None, 'warning': None}
    return max(checks, key=lambda c: (priority[c['status']], sum(x is not None for x in c['found'].values())))


def rank_candidates(rows, request, cards, similarity=None):
    if not isinstance(request, list) or not request:
        raise ValueError('Нужен непустой список требований')
    seen = set()
    for requirement in request:
        if requirement.get('card') not in cards or 'required' not in requirement or type(requirement['required']) is not bool:
            raise ValueError('Нужны известная карточка и required со значением true или false')
        if requirement['card'] in seen:
            raise ValueError('Требование повторяется')
        seen.add(requirement['card'])
    result = []
    for row in rows:
        checks = [{**requirement, 'text': cards[requirement['card']]['text'],
                   **check_candidate(row['domains'], cards[requirement['card']])}
                  for requirement in request]
        required = [c for c in checks if c.get('required', False)]
        desired = [c for c in checks if not c.get('required', False)]
        result.append({'id': row['id'], 'eligible': all(c['status'] == 'confirmed' for c in required),
                       'required_confirmed': sum(c['status'] == 'confirmed' for c in required),
                       'desired_confirmed': sum(c['status'] == 'confirmed' for c in desired),
                       'search_score': (similarity or {}).get(row['id'], 0), 'checks': checks})
    return sorted(result, key=lambda c: (not c['eligible'], -c['required_confirmed'],
                                         -c['desired_confirmed'], -c['search_score'], c['id']))
