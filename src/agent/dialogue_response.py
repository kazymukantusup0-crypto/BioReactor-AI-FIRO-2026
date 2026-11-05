"""Readable RU/KK/EN answers assembled only from confirmed facts and tool results."""
from src.agent.tools import get_model_info
from src.recommendations.knowledge import source_records

NAMES={
 'manure':('навоз','manure','көң'),'cattle_manure':('коровий навоз','cattle manure','сиыр көңі'),
 'swine_manure':('свиной навоз','pig manure','шошқа көңі'),'poultry_manure':('птичий помёт','poultry manure','құс көңі'),
 'food_waste':('пищевые отходы','food waste','тағам қалдықтары'),'chernozem':('чернозём','chernozem','қара топырақ'),
 'Wheat straw':('пшеничная солома','wheat straw','бидай сабаны'),'Whey':('молочная сыворотка','whey','сарысу')}


def choose(lang,ru,en,kk):return {'ru':ru,'en':en,'kk':kk}[lang]


def fmt(value,lang='ru'):
    text=f'{float(value):,.6g}'.replace(',',' ')
    return text.replace('.',',') if lang in {'ru','kk'} else text


def answer(state,results,extraction,question,has_llm):
    lang=state.language;intents=set(state.intents);material=state.value('material')
    name=NAMES.get(material,(str(material or ''),)*3)[['ru','en','kk'].index(lang)]
    paragraphs=[];sources={};modes=[];assumptions=[]
    followup=not extraction.intents and bool(extraction.entities)
    def add_source(source):
        if isinstance(source,dict) and source.get('url'):sources[source['url']]=source
    def add(text):
        if text and text not in paragraphs:paragraphs.append(text)
    if 'greeting' in intents and not material:
        add(choose(lang,'Здравствуйте! Помогу разобраться с сырьём, научными режимами и экономикой.','Hello! I can help with feedstocks, scientific guidance and economics.','Сәлем! Шикізат, ғылыми режимдер және экономика бойынша көмектесемін.'))
    if state.invalidated:
        add(choose(lang,f'Обновил данные: теперь обсуждаем {name}. Зависевшие от прежнего материала или количества оценки и предложения больше не использую.',f'Updated: we are discussing {name}. Estimates and offers tied to the previous material or quantity are no longer used.',f'Деректер жаңартылды: енді {name} туралы сөйлесеміз. Алдыңғы шикізатқа немесе мөлшерге тәуелді бағалар мен ұсыныстар қолданылмайды.'))
    if state.value('quantity') is not None:
        unit={'L':'л','m3':'м³','kg':'кг','t':'т','g':'г'} if lang!='en' else {'L':'L','m3':'m³','kg':'kg','t':'t','g':'g'}
        add(choose(lang,f'В партии: {fmt(state.value("quantity"),lang)} {unit.get(state.value("unit"),state.value("unit"))}, сырьё — {name or "пока не уточнено"}.',f'Batch: {fmt(state.value("quantity"),lang)} {unit.get(state.value("unit"),state.value("unit"))}; material: {name or "not yet identified"}.',f'Партия: {fmt(state.value("quantity"),lang)} {unit.get(state.value("unit"),state.value("unit"))}; шикізат — {name or "әзірге анықталмаған"}.'))
    if material=='chernozem':
        add(choose(lang,'Чернозём — почва, а не подтверждённое биогазовое сырьё в нашей базе. Органическое вещество почвы не означает измеренный выход метана; численный BMP для неё я не назначаю.','Chernozem is soil, not a validated biogas feedstock in this system. Soil organic matter does not establish a measured methane yield; I will not assign it a numerical BMP.','Қара топырақ — біздің қорда расталған биогаз шикізаты емес. Топырақтағы органикалық зат өлшенген метан шығымын білдірмейді; оған сандық BMP тағайындамаймын.'))
        for source in results.get('analyze_substrate',{}).get('sources',[]):add_source(source)
    economic=results.get('compare_market_scenarios') or results.get('calculate_profitability')
    if 'economic_comparison' in intents and material!='chernozem':
        if economic and (economic.get('status')=='ok' or any(row['status']=='ok' for row in economic.get('scenarios',[]))):
            for row in economic.get('scenarios',[]):
                if row['status']=='ok':add(choose(lang,f'Вариант {row["scenario"]}: результат после указанных затрат {fmt(row["net_profit"],lang)} {economic["currency"]}.',f'Option {row["scenario"]}: result after the specified costs {fmt(row["net_profit"],lang)} {economic["currency"]}.',f'{row["scenario"]} нұсқасы: көрсетілген шығындардан кейінгі нәтиже {fmt(row["net_profit"],lang)} {economic["currency"]}.'))
            if 'processing_net_profit' in economic:
                add(choose(lang,f'Переработка после указанных затрат: {fmt(economic["processing_net_profit"],lang)} {economic["currency"]}; выручка продажи сырья: {fmt(economic["sale_revenue"],lang)} {economic["currency"]}.',f'Processing after the specified costs: {fmt(economic["processing_net_profit"],lang)} {economic["currency"]}; raw-feedstock sale revenue: {fmt(economic["sale_revenue"],lang)} {economic["currency"]}.',f'Көрсетілген шығындардан кейінгі өңдеу нәтижесі: {fmt(economic["processing_net_profit"],lang)} {economic["currency"]}; шикізатты сату түсімі: {fmt(economic["sale_revenue"],lang)} {economic["currency"]}.'))
            modes.append('conditional_economic_scenario')
            add(choose(lang,'Это расчёт при заданных условиях, а не подтверждение фактической прибыли.','This is a calculation under specified conditions, not confirmation of actual profit.','Бұл берілген шарттардағы есеп, нақты пайданы растау емес.'))
        elif state.value('sale_offer_amount') is not None:
            add(choose(lang,'Предложение продажи уже есть. Для сравнения с переработкой остаётся оценить выход полезного продукта и затраты; итоговую прибыль пока не назначаю.','We now have a sale offer. Comparing it with processing still requires product yield and costs; I will not assign a final profit yet.','Сату ұсынысы бар. Өңдеумен салыстыру үшін өнім шығымы мен шығындар қажет; түпкі пайданы әзірге тағайындамаймын.'))
        elif followup:
            add(choose(lang,'Вид сырья уточнён. Следующий полезный шаг — узнать реальную цену продажи этой партии, затем сопоставить её с выходом продукта и затратами переработки.','The feedstock type is now clear. The next useful step is an actual sale offer for this batch, followed by product yield and processing costs.','Шикізат түрі нақтыланды. Келесі қадам — осы партияға нақты сату ұсынысын білу, кейін өнім шығымы және өңдеу шығындарымен салыстыру.'))
        else:
            add(choose(lang,'Переработку можно рассмотреть, но сейчас нельзя честно назвать её выгоднее продажи: нужны выход полезного продукта, применимая цена и затраты. Можно сравнить условный сценарий, если вы явно зададите эти предположения.','Processing is worth considering, but I cannot yet establish that it beats selling: product yield, applicable prices and costs are needed. We can compare a hypothetical scenario if you explicitly supply its assumptions.','Өңдеуді қарастыруға болады, бірақ оның сатудан тиімді екенін әзірге растай алмаймын: өнім шығымы, сәйкес баға және шығындар қажет. Болжамдарды нақты берсеңіз, шартты сценарийді салыстырамыз.'))
        offer=state.value('sale_offer_amount');scope=state.value('sale_offer_scope');currency=state.value('sale_offer_currency','KZT')
        if offer is not None:
            if scope=='batch':add(choose(lang,f'По вашему предложению продажа всей партии даёт {fmt(offer,lang)} {currency} выручки до хранения и перевозки. Это пока не чистая прибыль.',f'Your offer gives {fmt(offer,lang)} {currency} revenue for the whole batch before storage and transport. This is not yet net profit.',f'Сіздің ұсынысыңыз бойынша бүкіл партияның түсімі сақтау және тасымалға дейін {fmt(offer,lang)} {currency}. Бұл әзірге таза пайда емес.'))
            else:add(choose(lang,f'Предложение {fmt(offer,lang)} {currency} сохранил; его основание пока нужно уточнить.',f'I recorded the {fmt(offer,lang)} {currency} offer; its price basis still needs clarification.',f'{fmt(offer,lang)} {currency} ұсынысы сақталды; оның баға негізін нақтылау қажет.'))
        prices=results.get('get_market_prices',{}).get('prices',[])
        if prices:
            add(choose(lang,'Сохранённые бытовые тарифы и статистика — ориентиры, а не цена покупки вашего сырья или продажи сырого биогаза.','Saved household tariffs and statistics are references, not bids for your feedstock or raw-biogas sales prices.','Сақталған тұрмыстық тарифтер мен статистика — бағдар; олар шикізатыңызды сатып алу немесе шикі биогазды сату бағасы емес.'))
            for price in prices[:2]:add_source({'title':price['source_name'],'url':price['source_url']})
    recommendation=results.get('recommend_conditions',{})
    claims=recommendation.get('claims',[])
    for claim in ([] if followup else claims[:2]):
        add(claim['text'][lang]);modes.append('literature_guidance')
        for source in recommendation.get('sources',[]):
            if source.get('id')==claim['source_id']:add_source(source)
    if state.value('temperature_c') is not None and 'temperature_recommendation' in intents:
        add(choose(lang,f'{fmt(state.value("temperature_c"),lang)} °C сохраняю как указанный вами вариант. Одна температура не доказывает оптимальность или безопасность режима; нужны конструкция, стабильность процесса и измерения.',f'I recorded {fmt(state.value("temperature_c"),lang)} °C as your proposed condition. Temperature alone does not establish an optimal or safe regime; design, process stability and measurements matter.',f'{fmt(state.value("temperature_c"),lang)} °C сіз ұсынған шарт ретінде сақталды. Бір температура режимнің оңтайлы не қауіпсіз екенін дәлелдемейді; құрылым, тұрақтылық және өлшемдер керек.'))
    if claims and followup:
        add(choose(lang,'Уточнение вида навоза не превращает ранее приведённый литературный режим в доказанный оптимум вашей установки.','Identifying the manure type does not turn the earlier literature guidance into a verified optimum for your reactor.','Көң түрін нақтылау алдыңғы әдеби режимді реакторыңыздың дәлелденген оңтайлы режиміне айналдырмайды.'))
        for source in recommendation.get('sources',[]):
            if source.get('id')==claims[0]['source_id']:add_source(source)
        modes.append('literature_guidance')
    if claims and not followup and 'temperature_recommendation' in intents:
        add(choose(lang,'Это литературная справка, не ML-прогноз и не команда нагревателю. Без датчиков я не могу подтвердить состояние установки.','This is literature guidance, not an ML prediction or heater command. Without sensors I cannot confirm the reactor state.','Бұл әдеби нұсқаулық, ML болжамы немесе қыздырғышқа команда емес. Датчиктерсіз қондырғының күйін растай алмаймын.'))
    prediction=results.get('predict_bmp',{})
    if prediction.get('status')=='ok':
        modes.append('experimental_ml_prediction')
        add(choose(lang,f'Сохранённая модель оценивает лабораторный BMP в {fmt(prediction["bmp"],lang)} мл CH₄/г VS. Это потенциал субстрата; подтверждённого 90% интервала и проверки вашей установки нет.',f'The saved model estimates laboratory BMP at {fmt(prediction["bmp"],lang)} mL CH₄/g VS. This is substrate potential; no validated 90% interval or validation on your reactor is available.',f'Сақталған модель зертханалық BMP мәнін {fmt(prediction["bmp"],lang)} мл CH₄/г VS деп бағалайды. Бұл субстрат әлеуеті; расталған 90% интервал және сіздің реакторыңыздағы тексеру жоқ.'))
        add_source(source_records(['hafner'])[0])
    elif 'methane_yield' in intents and material!='chernozem' and results.get('calculate_methane',{}).get('status')!='ok':
        if prediction.get('status')=='unsupported':add(choose(lang,'Hafner-модель не обучена на этом сырье; литературную справку я не выдаю за ML-прогноз.','The Hafner model was not trained on this feedstock; literature guidance is not an ML prediction.','Hafner моделі бұл шикізатқа үйретілмеген; әдеби нұсқаулық ML болжамы емес.'))
        add(choose(lang,'Точный объём метана по одной влажной массе или литрам не определяется. Для этого сырья нужны применимый удельный выход и измеренная органическая часть; значения за вашу партию я не подставляю.',f'Wet mass or litres alone cannot determine methane volume. We need an applicable specific yield and measured volatile solids; I will not invent them for your batch.',f'Тек ылғалды масса немесе литр арқылы метан көлемін анықтау мүмкін емес. Сәйкес меншікті шығым мен өлшенген ұшпа заттар қажет; партияңызға ойдан мән қоспаймын.'))
        for source in results.get('search_scientific_sources',{}).get('sources',[]):add_source(source)
    methane=results.get('calculate_methane',{})
    if methane.get('status')=='ok':add(choose(lang,f'По указанной органической массе потенциальный CH₄: {fmt(methane["potential_methane_m3"],lang)} м³ при заданных условиях приведения; фактическая выработка не подтверждена.',f'Potential CH₄ from the stated volatile-solids mass: {fmt(methane["potential_methane_m3"],lang)} m³ at the stated reference conditions; actual production remains unverified.',f'Көрсетілген ұшпа зат массасынан ықтимал CH₄: берілген келтіру шарттарында {fmt(methane["potential_methane_m3"],lang)} м³; нақты өндіріс расталмаған.'))
    volume=state.value('material_volume_l');total=state.value('reactor_total_volume_l')
    if volume is not None and total is not None and volume>total:
        add(choose(lang,f'{fmt(volume,lang)} л сырья больше полного объёма реактора {fmt(total,lang)} л: загрузить всё одновременно нельзя. Рабочий объём отличается от полного; число партий без рабочего объёма и режима подачи я не рассчитываю.',f'{fmt(volume,lang)} L of feedstock exceeds the reactor total volume of {fmt(total,lang)} L: it cannot all be loaded at once. Working volume differs from total volume; no batch count is calculated without working volume and feeding mode.',f'{fmt(volume,lang)} л шикізат реактордың {fmt(total,lang)} л толық көлемінен көп: бәрін бірден тиеуге болмайды. Жұмыс көлемі толық көлемнен бөлек; жұмыс көлемі мен беру режимінсіз партия санын есептемеймін.'))
    if 'model_info' in results or 'get_model_info' in results:
        model=results.get('get_model_info',{});accuracy=model.get('accuracy',{})
        score=accuracy.get('macro_lab_MAE',accuracy.get('MAE'))
        if score is not None:add(choose(lang,f'Для {model["algorithm"]} сохранена MAE {fmt(score,lang)} мл CH₄/г VS. Схема оценки: {model["evaluation"]}. Это не проверка на независимых исследованиях.',f'{model["algorithm"]} has stored MAE {fmt(score,lang)} mL CH₄/g VS. Evaluation: {model["evaluation"]}. This is not independent-study validation.',f'{model["algorithm"]} үшін сақталған MAE: {fmt(score,lang)} мл CH₄/г VS. Бағалау: {model["evaluation"]}. Бұл тәуелсіз зерттеулермен тексеру емес.'));add_source(source_records(['hafner'])[0])
    if 'market_prices' in intents or 'price_history' in intents:
        prices=results.get('get_market_prices',{}).get('prices',[]) or results.get('get_price_history',{}).get('prices',[])
        if not prices:add(choose(lang,'Подходящих сохранённых цен этого региона нет.','No matching saved prices are available for this region.','Бұл өңірге сәйкес сақталған бағалар жоқ.'))
        for price in prices[:3]:
            label=choose(lang,'статистический ориентир, не предложение сделки','statistical reference, not a trade offer','статистикалық бағдар, сауда ұсынысы емес') if price['price_type']=='reference' else choose(lang,'тариф; проверьте профиль и свежесть','tariff; check customer profile and freshness','тариф; тұтынушы санаты мен мерзімін тексеріңіз')
            add(f'{fmt(price["normalized_value"],lang)} {price["currency"]}/{price["normalized_unit"]} · {price["region"]} · {price["effective_from"]} — {label}.')
            add_source({'title':price['source_name'],'url':price['source_url']})
    if 'get_reactor_status' in results:add(choose(lang,'Датчики не подключены. Реальных показаний нет, управление оборудованием отключено.','Sensors are not connected. No live readings are available and hardware control is disabled.','Датчиктер қосылмаған. Нақты өлшемдер жоқ, жабдықты басқару өшірілген.'))
    if not paragraphs:add(choose(lang,'Помогу разобраться. Уточните, что хотите оценить: сырьё, условия сбраживания, метан или экономику.','I can help. What would you like to assess: feedstock, digestion conditions, methane or economics?','Көмектесемін. Нені бағалаймыз: шикізат, ашыту шарттары, метан әлде экономика?'))
    from src.agent.process_bridge import response as process_response
    process_lines,process_sources=process_response(state,results)
    for line in process_lines:add(line)
    for source in process_sources:add_source(source)
    if state.assumptions:
        for key,entry in state.assumptions.items():
            if key=='market_region':
                region={'KZ-Karaganda':choose(lang,'Караганда','Karaganda','Қарағанды'),'KZ-Almaty':choose(lang,'Алматы','Almaty','Алматы')}.get(entry.value,entry.value)
                if 'get_market_prices' in results:assumptions.append(choose(lang,f'Рыночный регион профиля — {region}; вы его ещё не подтвердили.',f'The profile market region is {region}; you have not confirmed it.',f'Профильдегі нарық өңірі — {region}; сіз оны әлі растаған жоқсыз.'))
            elif key=='process_candidates':
                values=' / '.join(fmt(v,lang) for v in entry.value.get('temperatures_c',[]))
                assumptions.append(choose(lang,'Выбранные варианты температуры: ','Selected temperature alternatives: ','Таңдалған температура нұсқалары: ')+values+' °C')
            else:assumptions.append(f'{key}: {entry.value}')
    if assumptions:
        # Human answer discloses default region; scenario field details live in metadata.
        if 'get_market_prices' in results and 'market_region' in state.assumptions:add(assumptions[0])
        if any(k!='market_region' for k in state.assumptions):add(choose(lang,'Отдельные параметры указаны как предположения для сценария и не сохранены как измеренные факты.','Some parameters are scenario assumptions and have not been saved as measured facts.','Кейбір параметрлер сценарий болжамдары ретінде берілген, өлшенген дерек ретінде сақталмады.'))
    facing={'paragraphs':paragraphs,'question':question.model_dump() if question else None,'sources':list(sources.values()),
        'modes':list(dict.fromkeys(modes)) or ['consultation'],'assumptions':assumptions}
    lines=list(paragraphs)
    if question:lines.append(question.text)
    if sources:lines.append(choose(lang,'Источники:','Sources:','Дереккөздер:')+'\n'+'\n'.join(f'- {s["title"]}: {s["url"]}' for s in sources.values()))
    return '\n\n'.join(lines),facing
