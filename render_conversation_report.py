"""Render reviewable dialogues from actual archived evaluation responses (no inference)."""
import json
from pathlib import Path


def render():
    root = Path(__file__).resolve().parent / 'reports' / 'stage5_6'
    after = json.loads((root / 'ollama_eval.json').read_text(encoding='utf-8'))
    before = json.loads((root / 'baseline_dialogues.json').read_text(encoding='utf-8'))
    lines = ['# Фактические диалоги v5.6 с локальной Ollama', '',
             'Ответы дословно взяты из `ollama_eval.json`. Это заданные регрессионные случаи, '
             'а не независимая оценка качества на новых пользователях.', '']
    for case in after['cases']:
        reply = case['reply']
        lines += [f"## {case['id']} · диалог {case['conversation']}", '',
                  f"**Пользователь:** {case['message']}", '', reply['answer'], '',
                  f"Время: {case['latency_seconds']:.3f} с. "
                  f"Фактических инструментов: {len(reply['tools'])}. Проверки: {case['passed']}.", '']
    (root / 'actual_dialogues.md').write_text('\n'.join(lines), encoding='utf-8')
    old = {case['id']: case for case in before['cases']}
    lines = ['# До и после: одинаковые пользовательские сообщения', '',
             'Старая реализация запускалась до изменений. Новая — с реальной `qwen2.5:1.5b`. '
             'Полные исходные ответы сохранены в JSON; ниже вывод без редактирования.', '']
    for case in after['cases']:
        if case['id'] not in {'manure_800', 'cattle_followup', 'sale_offer', 'reactor_capacity'}:
            continue
        previous = old[case['id']]
        lines += [f"## {case['id']}", '', f"**Пользователь:** {case['message']}", '',
                  f"### До · {len(previous['reply']['tools'])} инструментов", '',
                  previous['reply']['answer'], '',
                  f"### После · {len(case['reply']['tools'])} инструментов", '',
                  case['reply']['answer'], '']
    (root / 'before_after.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    render()
