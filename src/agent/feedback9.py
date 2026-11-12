"""Auditable, bounded verifier feedback for one model repair attempt."""
import re

GUIDANCE={
 'absolute_lab_transfer_denial':('Категоричное отрицание переноса не подтверждено: применимость лабораторных данных зависит от различий условий.', ['Условия лабораторного теста и конкретного реактора'], 'Лабораторная кинетика может быть ориентиром после проверки применимости; не обещайте автоматический перенос.'),
 'capacity_conclusion_from_nominal_only':('Номинальная ёмкость не устанавливает рабочий объём и не доказывает допустимость загрузки или выход.', ['Рабочий объём, вода, инокулят и технологические ограничения','Масса сырья или подтверждённая плотность, TS/VS, применимый BMP, кинетика и срок'], 'Разделите вместимость и выход; укажите неизвестные параметры и задайте один вопрос, без численного прогноза.'),
 'bmp_theoretical_values_unconditionally_unequal':('Разные методы определения BMP и теоретического выхода не доказывают обязательное численное неравенство.', ['Сопоставимый состав и база измерения'], 'Назовите разные понятия и методы; численные значения могут совпадать.'),
 'methanogenesis_only_organic_substrates':('Утверждение без оговорки может скрывать разнообразие путей: среди субстратов есть также H₂ и CO₂.', ['Подтверждённый научный источник о путях метаногенеза'], 'Не обобщайте один субстрат на все метаногены; упоминайте пути только по источнику.'),
 'repeated_model_text':('Основная мысль повторяется в нескольких полях.', [], 'Объедините повторяющиеся утверждения без изменения смысла.'),
 'text_at_limit_incomplete':('Текст достигает границы поля и заканчивается посреди фразы.', [], 'Сократите текст и закончите каждое предложение.'),
 'incomplete_enumeration_or_clause':('Фраза или перечисление явно не завершены.', [], 'Закончите фразу без добавления неподтверждённых фактов.'),
 'generation_truncated':('Генерация остановлена по пределу длины.', [], 'Ответьте короче и завершите все фразы.'),
 'ungrounded_quantity_or_wrong_unit':('Число или его физическая роль не подтверждены доступными данными.', ['Подтверждённая величина, единица и физическая роль'], 'Используйте только результат инструмента или подтверждённую пользовательскую величину в той же роли.'),
 'internal_parameter_name_in_prose':('В ответ попало техническое имя вместо понятной формулировки.', [], 'Замените техническое имя понятными словами; не добавляйте значения.'),
 'missing_input_clarification_omitted':('Для запрошенной оценки не хватает данных, но уточняющий вопрос отсутствует.', ['Масса или плотность, VS и применимый BMP; для срока — кинетика'], 'Задайте один наиболее важный вопрос о недостающем параметре.'),
 'no_known_scientific_contradiction':('Проверка выявила конкретное научное противоречие, перечисленное в других замечаниях.', ['Подтверждённые данные из результатов научных инструментов'], 'Исправьте конкретное противоречие, сохранив подтверждённые утверждения.'),
 'unchanged_rejected_draft':('Повторная попытка воспроизводит отклонённый текст.', [], 'Исправьте конкретные ранее указанные утверждения, не добавляя фактов.'),
 'unresolved_prior_scientific_issue':('Повторная попытка сохранила ранее обнаруженную ошибку.', ['Подтверждённые сведения по указанному противоречию'], 'Устраните именно повторившееся противоречие, не меняя подтверждённых фактов.'),
}


def public_text(payload):
    return [payload.get('conclusion',''),payload.get('explanation',''),*(payload.get('limitations') or []),payload.get('next_question') or '']


def structured_feedback(payload,issues,quantity_differences=()):
    from src.agent.verification9 import scientific_assertions
    texts=public_text(payload); assertions=[a for text in texts for a in scientific_assertions(text) if not a['passed']]
    rows=[]
    for issue in dict.fromkeys(issues):
        reason,required,correction=GUIDANCE.get(issue,('Утверждение не прошло соответствующую проверку.', ['Проверенное подтверждение утверждения'], 'Удалите неподтверждённое утверждение или уточните его только по результатам инструментов.'))
        found=next((a['statement'] for a in assertions if a['rule']==issue),None)
        if not found and issue in {'no_known_scientific_contradiction','unchanged_rejected_draft','unresolved_prior_scientific_issue'} and assertions:
            found=assertions[0]['statement']
        if not found and issue=='capacity_conclusion_from_nominal_only':
            found=next((s.strip() for t in texts for s in re.split(r'(?<=[.!?])\s+|[;\n]',t) if re.search(r'номинальн|nominal',s,re.I) and re.search(r'не\s+влия|does\s+not\s+affect',s,re.I)),None)
        if not found and issue=='ungrounded_quantity_or_wrong_unit' and quantity_differences:
            d=quantity_differences[0];found=f"{d.get('rejected_value')} {d.get('unit') or ''}".strip()
        if not found:found=next((t for t in texts if t), '')
        rows.append({'issue_type':issue,'statement':found[:500],'why_unreliable':reason,
                     'required_information':required,'allowed_correction':correction})
    return rows


def substantive_fingerprint(payload):
    """Compare prose only; do not expose chain-of-thought or alter user facts."""
    return ' '.join(re.findall(r'\w+', ' '.join(public_text(payload)).casefold()))
