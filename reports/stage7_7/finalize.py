"""Generate the report from real artifacts and independently verify preservation."""
import main
import hashlib,json,re,sqlite3,statistics
from pathlib import Path
from contextlib import closing
from src.data.prepare import ROOT
OUT=ROOT/'reports/stage7_7'
def load(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def logtext(name):
 data=(OUT/name).read_bytes();return data.decode('utf-16') if data.startswith(b'\xff\xfe') else data.decode('utf-8')
hashes=load('preserved_hashes.json');changed=[name for name,digest in hashes.items() if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
tables={}
with closing(sqlite3.connect(ROOT/'data/market/market.sqlite3')) as con:
 con.row_factory=sqlite3.Row
 for table,old in load('legacy_sqlite.json').items():
  current=[dict(r) for r in con.execute('SELECT * FROM '+table)]
  tables[table]={'original':len(old),'current':len(current),'all_original_rows_retained':all(any(all(row.get(k)==v for k,v in prior.items()) for row in current) for prior in old)}
preservation={'files':len(hashes),'changed_or_missing':changed,'tables':tables,'passed':not changed and all(v['all_original_rows_retained'] for v in tables.values())}
(OUT/'preservation_results.json').write_text(json.dumps(preservation,ensure_ascii=False,indent=2),encoding='utf-8')
assert preservation['passed'],preservation
before=load('before_dialogue.json');http=load('http_results.json');browser=load('browser_results.json');after=http['dialogues'][:8]
assert all(x['passed'] for x in http['checks']) and browser['passed'] and not http.get('error')
backend=logtext('backend_tests.txt');assert backend.strip().endswith('OK')
back_count=int(re.findall(r'Ran (\d+) tests',backend)[-1])
front=re.sub(r'\x1b\[[0-9;]*m','',logtext('frontend_tests.txt'));front_count=int(re.findall(r'Tests\s+(\d+) passed',front)[-1])
performance=[]
for old,new in zip(before,after):
 performance.append({'question':new['question'],'before_seconds':old['seconds'],'after_seconds':new['seconds'],'before_characters':len(old['reply']['answer']),'after_characters':len(new['reply']['answer']),'before_llm_generations':sum(bool(p.get('actual_generation')) for p in old['reply']['provider_status']),'after_llm_generations':sum(bool(p.get('actual_generation')) for p in new['reply']['provider_status']),'tools_after':[t['tool'] for t in new['reply']['tools']]})
metrics={'checks':{'backend':back_count,'frontend':front_count,'http':len(http['checks']),'chrome':len(browser['checks'])},'performance':performance,'before_total_seconds':sum(x['before_seconds'] for x in performance),'after_total_seconds':sum(x['after_seconds'] for x in performance),'preservation':preservation}
(OUT/'summary.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
rows='\n'.join(f"| {i+1} | {p['before_seconds']:.3f} | {p['after_seconds']:.3f} | {p['before_characters']} → {p['after_characters']} | {', '.join(p['tools_after']) or 'повторное объяснение без инструментов'} |" for i,p in enumerate(performance))
examples='\n\n'.join(f"**Запрос:** {after[i]['question']}\n\nДо, фрагмент: «{before[i]['reply']['answer'][:300]}…»\n\nПосле: «{after[i]['reply']['answer']}»" for i in [1,2,7])
generations=[(p.get('model'),p.get('actual_generation')) for d in after for p in d['reply']['provider_status'] if p.get('actual_generation')]
report=f"""# BioReactor AI v7.7 — Clean Dashboard & Smart AI Agent

Дата проверки: 29 октября 2026 года. Реализация в существующем проекте v7.6, без переобучения и новых тяжёлых моделей.

## Изменения интерфейса

Из основной навигации и активных экранов убраны «Лабораторный потенциал метана», «Что выгоднее для вашей партии?», Process Optimizer и Experiment Lab. Их React-модули и backend не удалены. Старые ссылки #/prediction, #/economics, #/optimizer и #/experiments перенаправляются на #/substrates.

Substrate Advisor и Mixture Builder объединены в **«Сырьё и смеси» / Substrates & Mixtures**. Старые #/advisor и #/mixtures также ведут туда. Теперь это одна форма для одного или нескольких компонентов, с количеством в кг/литрах, добавлением, удалением и изменением состояния. Состав сохраняется между страницами в localStorage; серверная память диалогов и сценариев сохраняется отдельно.

Основной экран предлагает два действия: задать состав или спросить ассистента. Убраны лабораторные показатели, журнал внутренних обновлений, блоки архитектуры и дублирующая экономическая форма. Сохранены рынок с датами и статусами цен, мониторинг, источники и диагностика. Подключение проверяется лёгким /health, цены читаются отдельным запросом SQLite: главная страница не ждёт диагностики моделей. Исправлено повторное отображение валюты в единицах цен.

Оценка состава показывает короткий результат по газу, температуре, времени и экономике. Формулы, вклад компонентов, источники и полный JSON раскрываются отдельно. Простой и научный режимы используют один результат; переключение не отправляет повторный расчёт. Сравнение составов сохранено, но неподтверждённая оптимальность не объявляется.

По умолчанию интерфейс и разговорная смесь показывают **условный литературный сценарий** с допущением сопоставимости газовых условий. Это прямо поясняется рядом с результатом; в дополнительных параметрах допущение можно отключить. Строгий default существующего API не изменён. Измеренная влажность не превращается в сухой газ автоматически.

## Логика агента

Новая маршрутизация определяет текущую задачу до выбора инструментов: газ, температура, продолжительность, экономика, сравнение, состояние реактора, изменение состава и запрос подробностей. Текущий вопрос имеет приоритет над прежними намерениями.

* Газ: estimate_substrate_gas — сохранённая арифметика массы, органической части, потенциала и состава газа, без рынка и полного экономического отчёта.
* Температура/время: advise_substrate_conditions — сопоставимые исследования и проверка геометрии, без расчёта прибыли. Органическая нагрузка вычисляется только когда для неё переданы условия непрерывной подачи.
* Экономика: существующий v7.5/v7.6 движок с ценами, применимостью и затратами. Газ, энергия и цена сырья не становятся гарантированным доходом.
* Подробности/одна фраза: объяснение предыдущего результата; повторного вычисления нет, если запрос, задача и научные профили не изменились.
* Источники: ссылки реального результата или отобранные профили каталога, без выдуманных DOI и лишнего расчёта.

Неоднозначный новый вопрос передаётся локальной LLM для выбора допустимой задачи. Короткие однозначные уточнения обрабатываются грамматикой и текущим контекстом. Поэтому отсутствие нового запроса к LLM не выдаётся за ошибку модели.

Qwen предлагает намерение и буквальные фрагменты фактов; независимая грамматика, типы и Python проверяют их. Пояснения формируются ограниченным слоем проверенных данных: LLM не получает право самостоятельно придумывать выход, оптимум, прибыль или источник.

Обычный ответ ограничен 2–5 предложениями, простой — 1–3. Подробности раскрываются по просьбе. В основном тексте нет технических статусов и четырёх обязательных заголовков для каждого короткого уточнения. Однословное уточнение формы сырья даёт короткое подтверждение и числа, а не повтор отчёта.

## Память и кэш

142 л навоза сохраняются после вопросов о температуре и времени; добавление 20 кг пищевых отходов создаёт компонент с собственной единицей. «А теперь сколько газа?» использует обновлённый состав. Условное добавление через «если» хранится отдельно от подтверждённого наличия и остаётся активным для следующего расчёта.

Кэш результата привязан к задаче, входам и ревизии научных файлов. Запрос об экономике не может получить кэш только газового расчёта. Изменение количества, состава, свойств или профиля обновляет расчёт. Биологические справочные условия могут повторно использоваться при изменении количества, но геометрия пересчитывается и в аудите остаётся фактическое количество.

Файловый кэш ограничен восемью ревизиями; изменение mtime/размера обновляет чтение, вызывающий код получает независимую копию. Цены для нового экономического запроса не кэшируются как неизменно актуальные. Запрос «объясни подробнее» поясняет именно предыдущий снимок расчёта.

Системный промпт и передаваемый контекст сокращены: в память LLM попадают важные подтверждённые поля, активная цель и компактный состав, а не весь отчёт. Qwen3 8B остаётся основной моделью, qwen2.5:1.5b — резервной; параметры квантования и контекста не менялись.

## Реальная проверка восьми сообщений

Одинаковые восемь запросов измерены до изменения и после через локальную Ollama. После — также через настоящий HTTP-сервер на порту 8777, отдельную копию SQLite и установленный Chrome. Это наблюдение одного ноутбука, не статистический benchmark и не SLA.

| № запроса | До, с | После, с | Длина ответа, символов | Инструменты после |
|---|---:|---:|---:|---|
{rows}

Суммарно восемь ответов: **{metrics['before_total_seconds']:.3f} с → {metrics['after_total_seconds']:.3f} с**. В исходном прогоне LLM вызывалась восемь раз; для основных восьми новых сообщений — {sum(p['after_llm_generations'] for p in performance)} раз. Быстрые уточнения не требуют нового inference. Холодная загрузка первой модели включена во время и не скрыта.

Реальные генерации основного итогового прогона: {generations}. Доказательство основной модели: {http.get('primary_generation_evidence')}. В ранних попытках срабатывала сохранённая защита при RAM ниже 768 MiB и использовалась 1.5B. Порог не отключался; эти протоколы сохранены отдельно. Ускорение нельзя трактовать как независимое доказательство улучшения качества Qwen или гарантированную задержку на другом компьютере.

Полные входы, ответы, состояние, инструменты и метрики: [до](stage7_7/before_dialogue.json), [HTTP после](stage7_7/http_results.json), [сводка](stage7_7/summary.json).

## Примеры до и после

{examples}

Основной комбинированный запрос о 100 л навоза и 20 кг пищевых отходов проверен отдельно: газ и условия рассчитаны двумя нужными инструментами, экономический отчёт не запускается. Диапазон остаётся условной суммой профилей; число дней реальной партии не выдумывается.

## Тесты и совместимость

* Backend: **{back_count} тестов прошли**, включая прежние проверки моделей, единиц, научной применимости, цен, экономики и защит.
* Frontend: **{front_count} тест прошёл**; TypeScript и production-сборка выполнены.
* HTTP/Ollama/CLI: **{len(http['checks'])} проверок прошли**.
* Реальный Chrome: **{len(browser['checks'])} проверки прошли** — объединённая форма, все шесть старых ссылок, расчёт, сравнение, сохранение количества, RU-интерфейс, мобильные 390 px, переключение режимов и восьмиходовой диалог.
* Проверены новые CLI-инструменты и старый get_model_info; прежний /api/research/decision сохраняет результат RM1, а process/experiments/monitoring API доступны.

Два старых тестовых ожидания отображения обновлены под задание: вопрос о газе больше не обязан спрашивать назначение газа; краткий ответ больше не обязан содержать набор разделов. Научные, численные и модельные проверки не ослаблялись. UI-тесты обновлены под новую подпись кнопки и явно условный сценарий формы.

Журналы: [backend](stage7_7/backend_tests.txt), [frontend](stage7_7/frontend_tests.txt), [браузер](stage7_7/browser_results.json), [CLI](stage7_7/cli_results.json).

## Сохранность

**{len(hashes)} прежних файлов** моделей, исходных и обработанных данных, научных профилей и отчётов совпали по SHA-256. Сохранены все исходные строки SQLite, в том числе 28 ценовых наблюдений и история диалогов. QA не использует рабочую базу для тестовых записей. Ни новый проект, ни переобучение, ни синтетические рыночные цены не создавались.

Проверка: [preservation_results.json](stage7_7/preservation_results.json). Backend экономического анализа, ML, мониторинга, биогаза и смесей сохранён; удаление относится к интерфейсу.

## Скриншоты

* [Новый главный экран](stage7_7/home_1440.png).
* [Сырьё и смеси, 1440 px](stage7_7/substrates_1440.png).
* [Мобильная форма, 390 px](stage7_7/substrates_390.png).
* [Короткий сохранённый диалог](stage7_7/smart_chat_1440.png).
* [Предыдущий интерфейс v7.6](stage7_6/mixture_simple_1440.png).

## Известные ограничения

1. Численные профили по-прежнему есть только для двух видов сырья; количество распознаваемых названий не означает покрытие проверенными оценками.
2. Литературный потенциал не является реальной выработкой установки. Влажность, газовый базис, физическая форма и подготовка должны быть сопоставимы. Для общего биогаза смеси нужна подходящая доля метана.
3. 35 °C — изученный мезофильный ориентир, не вычисленный из литров оптимум. BMP 27/30 суток не назначает срок партии; HRT, SRT и запуск различаются.
4. Без полной экономики, покупателя и проверки стабильности победитель не объявляется. Без датчиков нет реальных показаний и аппаратных команд.
5. Неоднозначные свободные формулировки иногда требуют одного уточнения; это ограниченная предметная система, не универсальный разговорный ассистент.
6. LLM ограничена ресурсами ноутбука. RAM guard, резервная модель, таймауты и честный режим без LLM сохранены. Наблюдаемые задержки зависят от загрузки.
7. Сетевой сбор новых научных/рыночных данных не объявляется успешно обновлённым в v7.7: используются прежние проверенные профили и сохранённые цены с их датами. Механизм обновлений и ограничения источников v7.6 сохранены.

## Запуск

Из существующей папки BioReactor_AI: python main.py dashboard --port 8765 --no-scheduler. Откройте http://127.0.0.1:8765/dashboard/#/substrates. Для обычного планировщика цен уберите --no-scheduler; в проверяемой демонстрации он выключен.

Проверка: python -m unittest discover -s tests -v; в frontend — npm.cmd test и npm.cmd run build. Реальная интеграционная проверка: python verify_stage7_7.py; для повторного запуска нужен новый BIOREACTOR_STAGE7_7_QA_DB, старые QA-базы не удаляются.
"""
(ROOT/'reports/stage7_7_smart_agent_dashboard.md').write_text(report,encoding='utf-8')
print(json.dumps({'tests':metrics['checks'],'preserved_files':len(hashes),'before_total_seconds':metrics['before_total_seconds'],'after_total_seconds':metrics['after_total_seconds'],'report':'reports/stage7_7_smart_agent_dashboard.md'},ensure_ascii=False))
