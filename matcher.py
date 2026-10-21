"""Проверка требования по исходной фразе. Общего графа доменов нет."""
import json
import re
from pathlib import Path

from data import normalize

NEGATION = re.compile(r'\bне\s+(?:занимал|работал|интегрировал|участвовал)\w*|'
                      r'\bнет\s+опыт\w*|\bбез\s+опыт\w*')
NOT_ONLY = re.compile(r'\b(?:не\s+только|not\s+only)\b')
POSSIBLE_NEGATION = re.compile(r"\b(?:не|нет|никогда|без|not|no|never|without)\b|n['’]t\b")
CLAUSE_SEPARATOR = re.compile(r'(,|\b(?:но|однако|зато|и|but|however|and)\b)', re.I)
CONTRAST = re.compile(r'^(?:но|однако|зато|but|however)$', re.I)


def _has_negation(text):
    return POSSIBLE_NEGATION.search(NOT_ONLY.sub('', text)) is not None


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
        if status == 'confirmed' and _has_negation(text):
            status, warning = 'review', 'Возможное отрицание. Нужен просмотр текста.'
    elif any(found.values()) or any(normalize(term) in text for term in card.get('review_terms', [])):
        status = 'review'
    else:
        status = 'unknown'
    return {'status': status, 'quote': phrase if status != 'unknown' else None,
            'found': found, 'missing': missing, 'warning': warning}


def check_phrase(phrase, card):
    """Признаки не склеиваются, общее отрицание в перечислении требует просмотра."""
    checks = []
    for sentence in re.split(r'[;.!?]', phrase):
        negated_context = False
        for part in CLAUSE_SEPARATOR.split(sentence):
            clause = part.strip()
            if not clause:
                continue
            if CONTRAST.fullmatch(clause):
                negated_context = False
                continue
            if clause.casefold() in (',', 'и', 'and'):
                continue
            check = _check_clause(clause, card)
            if negated_context and check['status'] == 'confirmed':
                check = {**check, 'status': 'review', 'quote': sentence.strip(),
                         'warning': 'В предыдущей части перечисления есть отрицание. Нужен просмотр текста.'}
            checks.append(check)
            negated_context = negated_context or _has_negation(normalize(clause))
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
