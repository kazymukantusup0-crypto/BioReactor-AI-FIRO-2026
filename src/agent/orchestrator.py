"""LLM planning -> allowlisted tools -> JSON validation -> verified response cards."""
import json
import re
from src.agent.context import extract_explicit,merge_context,validate_context
from src.agent.providers import HybridLLM
from src.agent.tools import TOOL_NAMES,ToolRegistry


def fallback_plan(text,context):
    """Restricted deterministic routing, explicitly NOT a language model."""
    lower=text.casefold()
    names=[]
    if context.get('material') or re.search('сырь|материал|черноз|почв|отход',lower): names+=['analyze_substrate']
    if re.search('выгод|прода|прибыл|эконом|profit',lower) or any(k in context for k in ['sale_price_per_kg','methane_price_per_m3']) or ('market_scenario' in context and text.strip().startswith('{')):
        names+=['analyze_substrate','predict_bmp','calculate_methane','get_market_prices','compare_market_scenarios','explain_market_recommendation']
    elif re.search('bmp|бмп|метан|выход|прогноз',lower) or all(k in context for k in ['c_vs_sub_m','c_vs_sub_f','c_vs_inoc','ISR']):
        names+=['analyze_substrate','predict_bmp']
        if re.search(r'метан|выход|объ[её]м\s+газа',lower): names+=['calculate_methane']
    if re.search(r'режим|температур|влажност|удерж|\bph\b|услови',lower): names+=['recommend_conditions']
    if re.search('модел|точност|mae|rmse|r²',lower): names+=['get_model_info']
    if re.search('состояни|датчик|статус|sensor|status',lower): names+=['get_reactor_status']
    if re.search('источник|стать|публикац|научн|source',lower): names+=['search_scientific_sources']
    if re.search('цен|тариф|рынок|рыноч|price|market',lower):names+=['get_market_prices']
    if re.search(r'истори\w*\s+цен|измен\w*\s+цен|динамик',lower):names+=['get_price_history']
    return list(dict.fromkeys(names or ['analyze_substrate']))


def ordered_dependencies(names,context):
    names=list(names)
    if 'compare_market_scenarios' in names and 'calculate_profitability' in names:
        from src.economics.calculator import ECONOMIC_FIELDS
        if not all(context.get(k) is not None for k in ECONOMIC_FIELDS):names=[n for n in names if n!='calculate_profitability']
    if 'explain_market_recommendation' in names:names+=['compare_market_scenarios']
    if 'compare_market_scenarios' in names:names+=['get_market_prices']
    if 'calculate_profitability' in names and 'potential_methane_m3' not in context:
        names+=['calculate_methane']
    if 'calculate_methane' in names and 'bmp_ml_ch4_g_vs' not in context:
        names+=['predict_bmp']
    if 'predict_bmp' in names: names+=['analyze_substrate']
    return [name for name in TOOL_NAMES if name in names]


class Agent:
    def __init__(self,mode='auto',context=None,llm=None,registry=None):
        self.context=validate_context(context or {})
        self.llm=llm or HybridLLM(mode)
        self.registry=registry or ToolRegistry()
        self.history=[]
        self.last_pending=[]

    def reset(self):
        self.context={'model':self.context['model']} if 'model' in self.context else {}
        self.history=[]
        self.last_pending=[]

    def ask(self,text):
        try:
            additions=extract_explicit(text)
            new_context,reset=merge_context(self.context,additions)
        except (ValueError,TypeError) as exc:
            return {'mode':'input_rejected','answer':'Некорректный ввод: '+str(exc),'tools':[], 'context_updated':False}
        self.context=new_context
        proposed=self.llm.plan(text,self.context,self.history)
        raw_proposed=list(proposed) if proposed else []
        # Deterministic checks may add required scientific tools; LLM cannot bypass them.
        essential=fallback_plan(text,self.context)
        # A structured reply completes the preceding request, not unrelated tools
        # a small LLM might select merely because it sees a large JSON object.
        if text.strip().startswith('{') and self.last_pending and not reset:
            essential=list(self.last_pending)
            proposed=[n for n in (proposed or []) if n in ordered_dependencies(essential,self.context)] or (essential if proposed else None)
        if self.last_pending and additions and not reset:
            essential+=self.last_pending
        names=ordered_dependencies((proposed or [])+essential,self.context)
        trace=[]
        results={}
        for name in names:
            result=self.registry.execute(name,self.context,results,text)
            # Fail closed if a custom tool violates result protocol.
            try:
                json.dumps(result,allow_nan=False)
                if not isinstance(result,dict) or 'status' not in result or not isinstance(result.get('message'),str):
                    raise ValueError('Invalid result')
            except (ValueError,TypeError):
                result={'status':'error','message':'Инструмент вернул непроверяемый результат; он отклонён.'}
            results[name]=result
            trace.append({'tool':name,'input_origin':'explicit_user_context_and_verified_prior_tool_results',
                'status':result['status'],'result':result})
        order=self.llm.order_results(text,results)
        mode='llm_tools' if proposed else 'deterministic_tools_no_llm'
        missing=list(dict.fromkeys(key for result in results.values() for key in result.get('missing',[]) if result['status']=='needs_input'))
        self.last_pending=[name for name,result in results.items() if result['status']=='needs_input']
        lines=[]
        if not proposed:
            lines.append('В этом ответе LLM не используется. Работает ограниченный расчётный режим, не языковая модель.')
        if reset: lines.append('Сырьё изменилось: предыдущие характеристики и цены партии сброшены.')
        seen_messages=set()
        for name in order:
            if name not in results: continue
            if name=='compare_market_scenarios' and results.get('explain_market_recommendation',{}).get('status') in {'ok','needs_input'}:continue
            result=results[name]
            if result['message'] not in seen_messages:
                lines.append(result['message'])
                seen_messages.add(result['message'])
            if result.get('domain',{}).get('limited_support'):
                lines.append('Ограничение: у этой категории мало независимых обучающих лабораторий; нужны дополнительные измерения.')
        if missing:
            if 'calculate_profitability' in self.last_pending:
                lines.append('Для сравнения нужны: масса партии, обоснованный потенциал метана и условия приведения, доля извлечения, цены сырья и метана, затраты на подготовку/нагрев/эксплуатацию, валюта и дата цен. Полный список полей доступен с --json.')
            else:
                lines.append('Нужны данные: '+', '.join(missing)+'. Ответьте JSON-объектом или полями имя=значение; строки с пробелами — в кавычках.')
        if 'mass_kg' in missing and 'material_volume_l' in self.context:
            lines.append('Литры сырья не равны килограммам: измерьте массу или задайте density_kg_l. Номинальный объём реактора не задаёт безопасный рабочий объём.')
        sources={s['url']:s for r in results.values() for s in r.get('sources',[]) if isinstance(s,dict) and 'url' in s}
        if sources: lines.append('Источники:\n'+'\n'.join(f"- {s['title']}: {url}" for url,s in sources.items()))
        self.history.append(text)
        self.history=self.history[-8:]
        return {'mode':mode,'provider_status':list(self.llm.status),'llm_proposed_tools':raw_proposed,'policy_tool_plan':names,'response_order':order,'answer':'\n\n'.join(lines),
            'tools':trace,'missing':missing,'context':dict(self.context),'actuator_access':False}
