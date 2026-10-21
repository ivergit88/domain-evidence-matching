"""Чтение исходных фраз. SQL здесь не выполняется."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path


def normalize(text):
    text = unicodedata.normalize('NFKC', text).casefold().replace('ё', 'е')
    return ' '.join(''.join('-' if unicodedata.category(c) == 'Pd' else c for c in text).split())


def decode_list(text):
    repaired = False
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        if not (text.startswith('"{') and text.endswith(']}')):
            raise ValueError('Неизвестный формат списка доменов') from None
        try:
            interior = json.loads('"' + text[2:-2] + '"')
            result = json.loads('[' + interior + ']')
        except json.JSONDecodeError as exc:
            raise ValueError('Не удалось восстановить список') from exc
        repaired = True
    if not isinstance(result, list) or any(not isinstance(s, str) or not s.strip() for s in result):
        raise ValueError('Ожидался список непустых строк')
    return result, repaired


def load_candidates(path):
    source = Path(path).read_text(encoding='utf-8-sig')
    header = re.match(r'\s*INSERT\s+INTO\s+"avtopodbor"\."resumes_domains"\s*'
                      r'\(\s*"id"\s*,\s*"business_domains"\s*\)\s*VALUES\s*', source, re.I)
    if not header:
        raise ValueError('Ожидался исходный INSERT из задания')
    pattern = re.compile(r"\('([0-9]+)',\s*'((?:''|[^'])*)'\)")
    cursor, rows, seen, repairs = header.end(), [], set(), 0
    while True:
        match = pattern.match(source, cursor)
        if not match:
            raise ValueError(f'Непонятная запись в позиции {cursor}')
        candidate_id = int(match[1])
        if candidate_id in seen:
            raise ValueError('Повтор ID кандидата')
        seen.add(candidate_id)
        domains, repaired = decode_list(match[2].replace("''", "'"))
        rows.append({'id': candidate_id, 'domains': domains})
        repairs += repaired
        cursor = match.end()
        separator = re.match(r'\s*,\s*', source[cursor:])
        if separator:
            cursor += separator.end()
            continue
        if not re.fullmatch(r'\s*;\s*', source[cursor:]):
            raise ValueError('После данных есть другой SQL. Ничего не выполнено.')
        break
    return rows, {'rows': len(rows), 'mentions': sum(len(r['domains']) for r in rows),
                  'unique_phrases': len({normalize(s) for r in rows for s in r['domains']}),
                  'repaired_rows': repairs,
                  'source_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest()}
