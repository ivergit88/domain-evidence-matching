"""Собрать блокнот и выполнить все ячейки."""
import json
import os
import sys
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parent


def build():
    md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
    notebook = nbf.v4.new_notebook(cells=[
        md('# Проверка опыта по требованиям вакансии\n\n'
           'Я начал с простого условия: нужные признаки должны быть в одной исходной фразе. '
           'Для каждого требования есть своя карточка. Общий граф доменов я не строю. '
           'Эмбеддинги помогают найти похожий опыт, затем карточка проверяет, хватает ли фактов.\n\n'
           'В SQL 117 кандидатов и 695 упоминаний. Полных резюме и проектов в нём нет.'),
        code("from pathlib import Path\nimport sys, os, json\n"
             "ROOT = Path.cwd()\nsys.path.insert(0, str(ROOT))\n"
             "from data import load_candidates\nfrom matcher import load_cards, check_phrase, rank_candidates\n"
             "from experiment import run\n"
             "rows, audit = load_candidates(ROOT / 'data/domains.sql')\n"
             "cards = load_cards(ROOT / 'cards.json')\nprint(audit)"),
        md('## Как работает карточка\n\n'
           'Для интеграции банковского ядра нужны три признака: действие, объект и банковский контекст. '
           'Одно слово про банк не подтверждает работу с ядром. '
           'Карточка хранит варианты формулировок только для своего требования. '
           'Её можно менять, не перестраивая общий справочник.'),
        code("core = cards['bank_core_integration']\nprint('Проверяем:', core['text'])\n"
             "print('Нужны признаки:', list(core['groups']))\n"
             "by_id = {r['id']: r['domains'] for r in rows}\n"
             "for candidate_id in (79, 6, 50, 83):\n"
             "    result = rank_candidates([{'id': candidate_id, 'domains': by_id[candidate_id]}],\n"
             "                             [{'card': 'bank_core_integration', 'required': True}], cards)[0]\n"
             "    check = result['checks'][0]\n"
             "    print(candidate_id, check['status'], check['quote'], 'не хватает:', check['missing'])"),
        md('## Примеры, которые легко перепутать\n\n'
           'Следующие фразы придуманы для проверки правил. В исходном SQL нет отрицаний '
           'и описаний отдельных проектов. Проверка нескольких таких фраз не заменяет разбор '
           'настоящего резюме.'),
        code("from matcher import check_candidate\n"
             "for text in ['интеграцией банковского ядра не занимался',\n"
             "             'интеграция ABS автомобиля', 'тестирование АБС банка']:\n"
             "    print(text, check_phrase(text, core)['status'])\n"
             "split = [{'text': 'интеграция CRM', 'project_id': 'A'},\n"
             "         {'text': 'ядро банковской системы', 'project_id': 'B'}]\n"
             "print('Разные проекты:', check_candidate(split, core)['status'])"),
        md('## Сравнение на данных задания\n\n'
           'Сравниваю три варианта: поиск по словам, локальные эмбеддинги и проверку по карточке. '
           'В последнем варианте эмбеддинги задают порядок только при равном числе подтверждений. '
           'Сама похожесть не закрывает обязательное условие.\n\n'
           'В checks.json есть 10 авторских сценариев и 34 оценки выбранных пар. '
           'Они нужны для начальной проверки. Это не независимая экспертная разметка всей базы. '
           'nDCG@2 считается только среди тех кандидатов, которым заранее дали оценку.'),
        code("cache = Path(os.environ.get('DOMAIN_CACHE', str(ROOT / '.cache')))\n"
             "report = run(cache=cache, benchmark=10000)\n"
             "print('Средняя nDCG@2:')\n"
             "for method, value in report['methods'].items():\n    print(method, round(value, 3))"),
        md('## Запрос из задания\n\n'
           'Финтех обязателен, интеграция ядра желательна. '
           'Сначала идут кандидаты, у которых есть все обязательные подтверждения. '
           'Затем учитывается желательный опыт. Балла вероятности найма здесь нет.'),
        code("for candidate in report['demo'][:3]:\n"
             "    print('Кандидат', candidate['id'], 'обязательные:', candidate['required_confirmed'],\n"
             "          'желательные:', candidate['desired_confirmed'])\n"
             "    for check in candidate['checks']:\n"
             "        print(' ', check['text'], check['status'], check['quote'])\n"
             "print(report['timing'])"),
        md('## Что я из этого понял\n\n'
           'На этих коротких фразах карточки помогают отделить подтверждение от общей тематики. '
           'Но правила пока написаны вручную. Новое требование тоже требует своей карточки. '
           'Следующий шаг я бы проверял на полных резюме: извлечение цитат через LLM и '
           'проверку спорных пар с учётом проекта. В текущем опыте LLM не запускалась.\n\n'
           'Для 10 000 кандидатов разумно заранее хранить фразы и векторы. '
           'Здесь замер повторяет исходные 117 профилей, поэтому он показывает только время проверки '
           'карточек. Он не измеряет обработку 10 000 новых резюме.\n\n'
           'Модель: [multilingual MiniLM](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2). '
           'Она работает локально на CPU. Веса и их версия указаны в results/experiment.json.'),
    ])
    notebook.metadata['kernelspec'] = {'name': 'python3', 'display_name': 'Python 3', 'language': 'python'}
    kernel_root = ROOT/'tmp/jupyter'
    spec = kernel_root/'kernels/local-project'
    spec.mkdir(parents=True, exist_ok=True)
    (spec/'kernel.json').write_text(json.dumps({'argv': [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
                                             'display_name': 'Local project', 'language': 'python'}), encoding='utf-8')
    os.environ['JUPYTER_PATH'] = str(kernel_root)+os.pathsep+os.environ.get('JUPYTER_PATH', '')
    if (ROOT.parent/'.model-cache').exists():
        os.environ['DOMAIN_CACHE'] = str(ROOT.parent/'.model-cache')
    path = ROOT/'solution.ipynb'
    try:
        NotebookClient(notebook, timeout=300, kernel_name='local-project',
                       resources={'metadata': {'path': str(ROOT)}}).execute()
    finally:
        nbf.write(notebook, path)
    print('Все 5 ячеек выполнены:', path)


if __name__ == '__main__':
    build()
