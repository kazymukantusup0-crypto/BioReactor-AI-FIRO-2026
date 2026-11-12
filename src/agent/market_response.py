"""Grounded partial explanations for market questions the calculator cannot price."""
import re


def digestate_valuation_explanation(results, state, include_question=True):
    """Explain why digestate volume alone cannot support an NPK valuation."""
    if state.value('market_commodity') != 'digestate' and 'digestate_management' not in state.intents:
        return None

    market = results.get('get_market_prices')
    rows = market.get('prices', []) if isinstance(market, dict) else []
    direct = [row for row in rows if isinstance(row, dict)
              and row.get('commodity') in {'digestate', 'organic_fertilizer'}]
    # Let the normal evidence renderer/model handle an actual directly relevant
    # observation; this fallback must not hide a saved quote.
    if direct:
        return None
    region_fact=state.assumptions.get('market_region')
    region=state.value('market_region') or (region_fact.value if region_fact else None)
    if region and region_fact and region_fact.provenance=='ASSUMED_FOR_SCENARIO':
        region_ru=f'для региона {region}, выбранного системой по умолчанию и не подтверждённого пользователем'
        region_en=f'for default region {region}, which the user has not confirmed'
        region_kk=f'{region} әдепкі өңірі үшін (пайдаланушы растаған жоқ)'
    else:
        region_ru=f'для региона {region}' if region else 'для выбранного региона'
        region_en=f'for region {region}' if region else 'for the selected region'
        region_kk=f'{region} өңірі үшін' if region else 'таңдалған өңір үшін'

    if state.language == 'ru':
        parts = []
        quantity = state.value('quantity')
        unit = state.value('unit')
        if quantity is not None and unit in {'L', 'l'}:
            parts.append(f'Указано {quantity:g} л дигестата. Это объём; он сам по себе не определяет массу и количество питательных элементов.')
        else:
            parts.append('Дигестат в этой задаче рассматривается как отдельный продукт, а не как измеренная масса сырья для выхода метана.')
        parts.append('Приписать ему цену минерального NPK нельзя: для сопоставимой стоимости нужны состав и доступность питательных веществ, а также подтверждённая пригодность и спрос именно на этот продукт.')
        if isinstance(market, dict) and market.get('status') == 'needs_input' and not rows:
            parts.append(f'Проверка сохранённых рыночных данных не вернула подходящей цены на дигестат {region_ru}; цена и доход от продажи не установлены.')
        elif isinstance(market, dict) and market.get('status') == 'error':
            parts.append('Проверка рынка завершилась ошибкой, поэтому наличие и величину актуальной цены подтвердить не удалось.')
        elif market is None:
            parts.append('Рыночная проверка для дигестата в этом ответе не выполнена; цену и доход от продажи подтвердить нельзя.')
        sources = results.get('search_scientific_sources')
        if isinstance(sources, dict) and sources.get('status') == 'ok' and not sources.get('sources') and not sources.get('claims'):
            parts.append('Локальный научный поиск в этом запуске также не вернул применимых источников о составе или товарной пригодности этой партии.')
        request=' Для оценки пригодности нужен лабораторный анализ сухого вещества и N/P/K; для денежной оценки — подтверждённый региональный прайс на дигестат и масса партии.'
        if include_question:request+=' Какие значения сухого вещества и N/P/K показал анализ, если он проводился?'
        parts.append(request.strip())
        return ' '.join(parts)

    if state.language == 'kk':
        parts=['Дигестаттың көлемі ғана оның массасы мен қоректік заттарын анықтамайды. Минералды NPK бағасын оған тікелей қолдануға болмайды: салыстыру үшін құрам, қоректік заттардың қолжетімділігі және өнімнің жарамдылығы дәлелденуі керек.']
        if isinstance(market,dict) and market.get('status')=='needs_input' and not rows:
            parts.append(f'{region_kk} сәйкес сақталған баға табылмады, сондықтан сату құны анықталмаған.')
        elif isinstance(market,dict) and market.get('status')=='error':
            parts.append('Нарық бағасын тексеру қатемен аяқталды, сондықтан бағаны растау мүмкін болмады.')
        elif market is None:parts.append('Бұл жауапта дигестаттың нарықтық бағасы тексерілмеді.')
        parts.append('Жарамдылығын бағалау үшін құрғақ зат пен N/P/K зертханалық талдауы қажет.')
        if include_question:parts.append('Зертханалық талдауда құрғақ зат пен N/P/K қандай болды?')
        return ' '.join(parts)
    parts=['Digestate volume alone does not establish its mass or nutrient content. A mineral NPK price cannot be assigned directly: comparison requires measured composition, nutrient availability, and evidence that this product is suitable for the intended use.']
    if isinstance(market,dict) and market.get('status')=='needs_input' and not rows:
        parts.append(f'No applicable stored digestate quote was returned {region_en}, so sale value is not established.')
    elif isinstance(market,dict) and market.get('status')=='error':
        parts.append('The market lookup failed, so the existence and value of a current price could not be confirmed.')
    elif market is None:parts.append('A digestate market lookup was not performed in this response.')
    sources=results.get('search_scientific_sources')
    if isinstance(sources,dict) and sources.get('status')=='ok' and not sources.get('sources') and not sources.get('claims'):
        parts.append('The local scientific search returned no applicable source on this batch composition or product suitability.')
    parts.append('A laboratory analysis of dry matter and N/P/K is needed to assess suitability; valuation also needs batch mass and a regional digestate quote.')
    if include_question:parts.append('What dry-matter and N/P/K values did the lab report, if measured?')
    return ' '.join(parts)


def digestate_answer_covers(answer, results, state):
    """Check whether synthesis retained the minimal evidence needed for digestate valuation."""
    if state.value('market_commodity') != 'digestate' and 'digestate_management' not in state.intents:
        return True
    if not answer:return False
    quantity=state.value('quantity');unit=state.value('unit')
    if quantity is not None and unit in {'L','l'}:
        number=f'{quantity:g}'.replace('.',r'[.,]')
        if not re.search(number+r'\s*(?:л|l)(?![\w])',answer,re.I):return False
    if not re.search(r'\bNPK\b',answer,re.I):return False
    if not re.search(r'(?:нельзя|не\s+(?:присва|приравня|подмен)|cannot|not\s+(?:assign|equate|substitute)).{0,70}\bNPK\b|\bNPK\b.{0,70}(?:нельзя|не\s+(?:присва|приравня|подмен)|cannot|not\s+(?:assign|equate|substitute))',answer,re.I):return False
    market=results.get('get_market_prices',{})
    if market.get('status')=='needs_input' and not re.search(r'(?:нет|не\s+(?:вернул|найд)|отсутств|not\s+(?:returned|available|found)|no\s+applicable).{0,80}(?:цен|прайс|quote|price)|(?:цен|прайс|quote|price).{0,80}(?:нет|не\s+(?:вернул|найд)|отсутств|not\s+(?:returned|available|found))',answer,re.I):return False
    region_fact=state.assumptions.get('market_region')
    region=state.value('market_region') or (region_fact.value if region_fact else None)
    if market.get('status')=='needs_input' and region_fact and region_fact.provenance=='ASSUMED_FOR_SCENARIO':
        if not region or region.casefold() not in answer.casefold() or not re.search(r'по\s+умолчанию|not\s+confirmed|default',answer,re.I):return False
    return True
