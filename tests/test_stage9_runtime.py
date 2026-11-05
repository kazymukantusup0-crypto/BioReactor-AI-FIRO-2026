"""Protocol/fault fixtures; these are not real-Qwen acceptance measurements."""
import json
from src.agent.conversation import ConversationAgent
from src.agent.dialogue_types import NLUProposal
from src.agent.providers import HybridLLM,JSONProvider
from src.agent.tools import ToolRegistry

def agent_with(decide,registry=None):
    provider=JSONProvider('offline',model='qwen3:8b')
    provider.extract_dialogue=lambda *args:NLUProposal(language='ru',intents=['methane_yield'],material=None,material_evidence=None,entities=[])
    provider.generate=decide
    agent=ConversationAgent(research_enabled=True,llm=HybridLLM('offline',providers=[provider]),registry=registry or ToolRegistry())
    agent.runtime_version='9'
    return agent

def action(tool=None):return {'action':'tool' if tool else 'answer','tool':tool or '','arguments':{},'purpose':'TEST protocol action'}
def synthesis(payload):
    return {'conclusion':'Получен условный потенциал метана.','explanation':'Это расчёт по опубликованному образцу, а не измеренная выработка установки.',
            'limitations':['Условия переноса на вашу партию не подтверждены.'],'next_question':None,
            'evidence_ids':[k for k in payload['evidence'] if k.endswith('.methane')][:2],'decision':'not_applicable'}

def test_v9_uses_model_selected_tools_then_independently_verified_synthesis():
    decisions=iter([action('assess_substrate_potential'),action()])
    def decide(messages,schema):
        return next(decisions) if 'action' in schema['properties'] else synthesis(json.loads(messages[-1]['content']))
    reply=agent_with(decide).ask('У меня 5 кг пищевых отходов. Сколько метана?')
    assert reply['technical_metadata']['final_author']=='qwen_verified'
    assert reply['technical_metadata']['verification']['status']=='ok'
    assert [t['tool'] for t in reply['tools']]==['assess_substrate_potential']
    assert 'м³ CH₄' in reply['answer'] and reply['actuator_access'] is False

def test_model_cannot_bypass_primary_evidence_gate():
    schemas=[]
    def decide(messages,schema):schemas.append(schema);return action()
    reply=agent_with(decide).ask('У меня 5 кг пищевых отходов. Сколько метана?')
    assert reply['technical_metadata']['final_author']=='verified_engine_partial'
    assert reply['technical_metadata']['primary_evidence_unchecked']==['assess_substrate_potential']
    assert all(s['properties']['action']['enum']==['tool'] for s in schemas)

def test_failed_scientific_tool_can_replan_to_alternative_path():
    class FaultRegistry(ToolRegistry):
        def _execute(self,name,*args):
            if name=='assess_substrate_potential':return {'status':'error','message':'TEST controlled scientific adapter failure'}
            return super()._execute(name,*args)
    decisions=iter([action('assess_substrate_potential'),action('recover_local_scientific_analysis'),action()])
    def decide(messages,schema):
        return next(decisions) if 'action' in schema['properties'] else synthesis(json.loads(messages[-1]['content']))
    reply=agent_with(decide,FaultRegistry()).ask('Есть 5 кг пищевых отходов. Сколько метана?')
    assert [t['status'] for t in reply['tools']]==['error','ok']
    assert reply['technical_metadata']['final_author']=='qwen_verified' and 'м³ CH₄' in reply['answer']
