"""One most useful question; scientific machine fields stay in technical metadata."""
from src.agent.dialogue_types import Question
from src.agent.tools import get_model_info

TEXT={
 'material':('Что это за сырьё?','What material is it?','Бұл қандай шикізат?'),
 'manure_subtype':('Какой именно навоз: коровий, свиной или птичий? От этого зависят применимые данные и условия сбраживания.','What type of manure is it: cattle, pig or poultry? Applicable evidence and processing conditions differ.','Бұл сиыр, шошқа немесе құс көңі ме? Қолданылатын деректер мен ашыту шарттары осыған тәуелді.'),
 'sale_scope':('Эти деньги предлагают за всю партию или за единицу массы/объёма?','Is that offer for the whole batch, or per unit of mass or volume?','Бұл ұсыныс бүкіл партияға ма, әлде масса немесе көлем бірлігіне ме?'),
 'working_volume':('Какой у реактора подтверждённый рабочий объём и как подаётся сырьё: порциями или непрерывно?','What is the confirmed working volume, and is feeding batchwise or continuous?','Реактордың расталған жұмыс көлемі қандай және шикізат мерзімді ме, үздіксіз бе беріледі?'),
 'vs_basis':('Процент VS указан от сухого вещества или от влажной массы?','Is VS expressed as a percentage of dry solids or wet mass?','VS пайызы құрғақ затқа ма, әлде ылғалды массаға ма қатысты?'),
 'sale_offer':('Есть ли реальное предложение купить эту партию и сколько предлагают за неё целиком?','Do you have an actual offer to buy this batch, and what is the total offer?','Осы партияны сатып алу туралы нақты ұсыныс бар ма, бүкіл партияға қанша ұсынады?'),
 'mass_or_density':('Можно взвесить партию или указать измеренную плотность? Литры без плотности не дают массу.','Can you weigh the batch or provide a measured density? Litres alone do not give its mass.','Партияны өлшеуге немесе өлшенген тығыздықты беруге бола ма? Литрден массаны тығыздықсыз анықтай алмаймыз.'),
 'laboratory_data':('Есть ли лабораторные данные о сухом и органическом веществе и удельном выходе метана для этой партии?','Do you have laboratory measurements of dry/volatile solids and specific methane yield for this batch?','Осы партияның құрғақ/ұшпа заттары мен меншікті метан шығымы бойынша зертханалық деректер бар ма?'),
 'vs_mass':('Известна ли измеренная масса органического сухого вещества в партии?','Do you know the measured mass of volatile solids in the batch?','Партиядағы ұшпа қатты заттардың өлшенген массасы белгілі ме?'),
 'laboratory_features':('Можете предоставить измеренные VS субстрата, лабораторного эталона и инокулята, а также отношение их органических масс?','Can you provide measured substrate/reference/inoculum VS and the inoculum-to-substrate VS ratio?','Субстрат, зертханалық эталон және инокуляттың өлшенген VS мәндерін және олардың VS қатынасын бере аласыз ба?'),
 'processing_costs':('Какие затраты на переработку известны — в первую очередь нагрев, обслуживание и перевозка?','What processing costs are known, especially heating, operation and transport?','Өңдеу шығындары, әсіресе жылыту, қызмет көрсету және тасымал, белгілі ме?'),
 'operating_mode':('Это периодический реактор или установка с регулярной/непрерывной подачей?','Is the digester batch-operated or regularly/continuously fed?','Реактор мерзімді жұмыс істей ме, әлде шикізат тұрақты/үздіксіз беріле ме?'),
}
FIELDS={'material':['material'],'manure_subtype':['material'],'sale_scope':['sale_offer_scope'],'working_volume':['reactor_working_volume_l','operating_mode'],
 'vs_basis':['vs_basis'],'sale_offer':['sale_offer_amount'],'mass_or_density':['mass_kg','density_kg_l'],'laboratory_data':['bmp_ml_ch4_g_vs','vs_mass_kg'],
 'vs_mass':['vs_mass_kg'],'laboratory_features':['c_vs_sub_m','c_vs_sub_f','c_vs_inoc','ISR'],'processing_costs':['preparation_cost','heating_cost','operating_cost'],'operating_mode':['operating_mode']}


def question(state,context,results):
    material=state.value('material');intents=set(state.intents)
    if results.get('calculate_profitability',{}).get('status')=='ok':return None
    def unknown(name):return name in state.facts and state.facts[name].provenance=='UNKNOWN'
    def make(key):
        if all(unknown(name) for name in FIELDS[key]):return None
        options={'manure_subtype':[['Коровий','Свиной','Птичий'],['Cattle manure','Pig manure','Poultry manure'],['Сиырдікі','Шошқаның көңі','Құс көңі']],
            'sale_scope':[['За всю партию','За килограмм','За литр'],['For the whole batch','Per kilogram','Per litre'],['Бүкіл партияға','Килограмм үшін','Литр үшін']],
            'operating_mode':[['Периодический (batch)','Непрерывный'],['Batch','Continuous'],['Мерзімді (batch)','Үздіксіз']]}.get(key)
        lang=['ru','en','kk'].index(state.language)
        return Question(id=key,text=TEXT[key][lang],fields=FIELDS[key],options=options[lang] if options else [],reason=key)
    if not material and intents & {'economic_comparison','methane_yield','process_guidance','temperature_recommendation'}:return make('material')
    if material=='manure':return make('manure_subtype')
    if state.value('sale_offer_amount') is not None and state.value('sale_offer_scope') is None:return make('sale_scope')
    volume=state.value('material_volume_l');total=state.value('reactor_total_volume_l')
    if volume is not None and total is not None and volume>total and (state.value('reactor_working_volume_l') is None or state.value('operating_mode') is None):return make('working_volume')
    if state.value('vs_percent') is not None and state.value('vs_basis') is None:return make('vs_basis')
    if material=='chernozem':return None
    if 'economic_comparison' in intents:
        if state.value('sale_offer_amount') is None and not unknown('sale_offer_amount'):return make('sale_offer')
        if volume is not None and state.value('mass_kg') is None and not unknown('density_kg_l'):return make('mass_or_density')
    if 'methane_yield' in intents:
        if material not in get_model_info(context.get('model','stage1_5'))['supported_substrates'] and state.value('bmp_ml_ch4_g_vs') is None and not unknown('bmp_ml_ch4_g_vs'):return make('laboratory_data')
        predicted=results.get('predict_bmp',{}).get('status')=='ok'
        if predicted or state.value('bmp_ml_ch4_g_vs') is not None:
            if state.value('vs_mass_kg') is None:return make('vs_mass')
        elif material in get_model_info(context.get('model','stage1_5'))['supported_substrates']:return make('laboratory_features')
    if 'economic_comparison' in intents and not any(r.get('is_final_recommendation') for r in results.values()):return make('processing_costs')
    if intents & {'temperature_recommendation','process_guidance'} and material and state.value('operating_mode') is None:return make('operating_mode')
    return None
