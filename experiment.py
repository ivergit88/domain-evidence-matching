"""Запуск примера и сравнение способов поиска на исходном SQL."""
import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean
from time import perf_counter

from data import load_candidates
from matcher import load_cards, rank_candidates
from search import Embeddings, lexical_scores

ROOT = Path(__file__).resolve().parent


def ndcg(order, labels, k=2):
    if set(order) != set(labels) or len(order) != len(set(order)):
        raise ValueError('Нужно оценивать ровно тех кандидатов, для которых есть разметка')
    def dcg(grades):
        return sum((2**g-1)/math.log2(i+2) for i, g in enumerate(grades[:k]))
    ideal = dcg(sorted(labels.values(), reverse=True))
    return dcg([labels[i] for i in order])/ideal if ideal else 0


def aggregate(rows, request, cards, scorer):
    result = {r['id']: 0.0 for r in rows}
    for requirement in request:
        scores = scorer(cards[requirement['card']]['text'])
        for candidate_id in result:
            result[candidate_id] += scores[candidate_id]/len(request)
    return result


def search_order(scores):
    return sorted(scores, key=lambda i: (-scores[i], i))


def run(offline=False, cache=None, benchmark=10000):
    rows, audit = load_candidates(ROOT/'data/domains.sql')
    cards = load_cards(ROOT/'cards.json')
    request = json.loads((ROOT/'request.json').read_text(encoding='utf-8'))
    fixture = json.loads((ROOT/'checks.json').read_text(encoding='utf-8'))
    queries = [card['text'] for card in cards.values()]
    started = perf_counter()
    model = None if offline else Embeddings(rows, queries, cache or ROOT/'.cache')
    index_seconds = perf_counter()-started
    lexical_cache = {q: lexical_scores(rows, q) for q in queries}
    methods, per_case, orders = {}, [], {}
    for case in fixture['cases']:
        req = case['requirements']
        lex = aggregate(rows, req, cards, lambda q: lexical_cache[q])
        ranked = {'Поиск по словам': search_order(lex)}
        scores = model and aggregate(rows, req, cards, model.scores)
        if model:
            ranked['Эмбеддинги фраз'] = search_order(scores)
        ranked['Проверка по карточке'] = [c['id'] for c in rank_candidates(rows, req, cards, scores or lex)]
        labels = {j['candidate_id']: j['grade'] for j in case['judgments']}
        orders[case['id']] = {}
        for method, order in ranked.items():
            selected = [i for i in order if i in labels]
            score = ndcg(selected, labels)
            per_case.append({'case': case['id'], 'method': method, 'ndcg_at_2': score})
            orders[case['id']][method] = {'selected_order': selected, 'top10': order[:10]}
    for name in ranked:
        methods[name] = mean(r['ndcg_at_2'] for r in per_case if r['method'] == name)
    lex = aggregate(rows, request['requirements'], cards, lambda q: lexical_cache[q])
    similarity = model and aggregate(rows, request['requirements'], cards, model.scores)
    demo = rank_candidates(rows, request['requirements'], cards, similarity or lex)
    timing = {'model_or_cache_load_seconds': index_seconds}
    if benchmark:
        repeated = [{'id': i+1, 'domains': rows[i%len(rows)]['domains']} for i in range(benchmark)]
        started = perf_counter()
        ranked = rank_candidates(repeated, request['requirements'], cards)
        timing['repeat_profiles'] = {'rows': len(ranked), 'seconds': perf_counter()-started,
            'note': 'Повтор исходных 117 профилей. Замер проверки карточек без извлечения и расчёта эмбеддингов.'}
    report = {'data': audit, 'methods': methods, 'per_case': per_case, 'orders': orders,
              'demo': demo, 'request': request, 'model': model.info if model else None,
              'timing': timing, 'case_count': len(fixture['cases']),
              'judgment_count': sum(len(c['judgments']) for c in fixture['cases']),
              'scope': 'Авторские примеры. Оценка только внутри выбранных подмножеств, не на всех кандидатах.',
              'approach': 'Карточка проверяет нужные признаки в одной исходной фразе. Общий граф не строится.'}
    output = ROOT/'results'
    output.mkdir(exist_ok=True)
    (output/'experiment.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (output/'metrics.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['case', 'method', 'ndcg_at_2'])
        writer.writeheader()
        writer.writerows(per_case)
    print(json.dumps({'данные': audit, 'nDCG@2': methods, 'модель': bool(model)}, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Без модели и загрузки весов')
    parser.add_argument('--cache', type=Path, default=ROOT/'.cache')
    parser.add_argument('--benchmark', type=int, default=10000)
    args = parser.parse_args()
    if args.benchmark < 0:
        parser.error('--benchmark должен быть неотрицательным')
    run(args.offline, args.cache, args.benchmark)
