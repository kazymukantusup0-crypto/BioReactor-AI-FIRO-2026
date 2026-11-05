"""v6 conversational tests use temporary SQLite; all numerical scenarios are hypothetical."""
import json
from pathlib import Path
import tempfile
import unittest
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.market.store import Store


class ProcessConversationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Store(Path(temporary.name) / 'TEST.sqlite3')
        self.agent = ConversationAgent(llm=HybridLLM(providers=[]), registry=ToolRegistry(self.store))

    def first(self):
        return self.agent.ask('У меня 800 литров коровьего навоза и реактор 90 литров. Как лучше его переработать?')

    def result(self, reply):
        return next(t['result'] for t in reply['tools'] if t['tool'] in {'optimize_process', 'compare_process_scenarios'})

    def test_mandatory_sequential_demo_preserves_roles_and_does_not_invent_a_winner(self):
        reply = self.first()
        self.assertEqual(self.agent.state.value('material_volume_l'), 800)
        self.assertEqual(self.agent.state.value('reactor_total_volume_l'), 90)
        self.assertIsNone(self.agent.state.value('reactor_working_volume_l'))
        self.assertEqual(reply['pending_question']['fields'], ['reactor_working_volume_l'])
        self.assertIn('optimize_process', reply['policy_tool_plan'])
        reply = self.agent.ask('Рабочий объём 65 литров')
        self.assertEqual(self.agent.state.value('reactor_working_volume_l'), 65)
        self.assertEqual(self.agent.state.value('material_volume_l'), 800)
        self.assertEqual(reply['pending_question']['id'], 'operating_mode')
        reply = self.agent.ask('Сравни 35 и 38 градусов')
        result = self.result(reply)
        self.assertEqual(len(result['scenarios']), 2)
        self.assertIsNone(self.agent.state.value('temperature_c'))
        self.assertIn('Зависимость BMP от температуры не установлена', reply['answer'])
        self.assertFalse(any(s['predicted_outputs']['methane'].get('potential_methane_m3') is not None for s in result['scenarios']))
        reply = self.agent.ask('А что выгоднее — продать или переработать?')
        self.assertIn('get_market_prices', reply['policy_tool_plan'])
        self.assertEqual(self.agent.state.value('material_volume_l'), 800)
        self.assertEqual(self.agent.state.value('reactor_working_volume_l'), 65)
        self.assertIn('нельзя честно назвать', reply['answer'])
        with self.store.connect() as con:
            self.assertGreaterEqual(con.execute('SELECT COUNT(*) FROM process_optimizer_runs').fetchone()[0], 4)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 0)

    def test_temperature_guidance_alone_retains_existing_three_tools(self):
        reply = self.agent.ask('Какая температура нужна для коровьего навоза?')
        self.assertEqual(reply['policy_tool_plan'], ['analyze_substrate', 'search_scientific_sources', 'recommend_conditions'])

    def test_comparison_targets_are_assumptions_not_current_reactor_measurements(self):
        self.first()
        self.agent.ask('Температура 37 градусов')
        self.agent.ask('Сравни 35 и 38 градусов')
        self.assertEqual(self.agent.state.value('temperature_c'), 37)
        selected = self.agent.state.assumptions['process_candidates']
        self.assertEqual(selected.provenance, 'ASSUMED_FOR_SCENARIO')
        self.assertEqual(selected.value['temperatures_c'], [35, 38])

    def test_followup_temperature_replaces_prior_candidates_and_recalculates(self):
        self.first()
        self.agent.ask('Сравни 35 и 38 градусов')
        reply = self.agent.ask('А если температура 37 градусов?')
        self.assertEqual(self.agent.state.value('material_volume_l'), 800)
        self.assertEqual(self.agent.state.assumptions['process_candidates'].value['temperatures_c'], [37])
        self.assertEqual(len(self.result(reply)['scenarios']), 1)

    def test_initial_temperature_is_not_target_temperature(self):
        self.first()
        self.agent.ask('Начальная температура 20 градусов')
        self.assertEqual(self.agent.state.value('initial_temperature_c'), 20)
        self.assertIsNone(self.agent.state.value('temperature_c'))

    def test_structured_energy_inputs_remain_explicit_and_compute_real_units(self):
        reply = self.agent.ask(json.dumps({'material': 'cattle_manure', 'process_parameters': {
            'heated_mass_kg': 10, 'initial_temperature_c': 20, 'temperature_c': 35,
            'heat_capacity_kj_kg_k': 4, 'heater_efficiency': .8,
            'heat_loss_coefficient_w_k': 0, 'auxiliary_energy_kwh': 0,
            'duration_days': 1, 'ambient_temperature_c': 20,
            'energy_scope': 'TEST hypothetical whole study', 'operating_mode': 'batch'}}))
        self.assertNotEqual(reply['mode'], 'input_rejected')
        energy = next(t['result']['energy'] for t in reply['tools'] if t['tool']=='estimate_process_energy')
        self.assertAlmostEqual(energy['initial_heating_kwh'], 10 * 4 * 15 / 3600 / .8)
        self.assertIsNone(self.agent.state.value('mass_kg'))

    def test_species_change_discards_old_material_thermal_data(self):
        self.first()
        self.agent.ask('heat_capacity_kj_kg_k=4 heated_mass_kg=10')
        self.agent.ask('Нет, это свиной навоз')
        self.assertIsNone(self.agent.state.value('heat_capacity_kj_kg_k'))
        self.assertIsNone(self.agent.state.value('heated_mass_kg'))

    def test_unrelated_model_question_does_not_run_optimizer(self):
        self.first()
        reply = self.agent.ask('Какова точность модели?')
        self.assertNotIn('optimize_process', reply['policy_tool_plan'])

    def test_boolean_or_blank_thermal_parameter_does_not_mutate_memory(self):
        self.first()
        for message in ['heated_mass_kg=true',json.dumps({'process_parameters':{'energy_scope':' '}})]:
            reply=self.agent.ask(message)
            self.assertFalse(reply['context_updated'])
            self.assertIsNone(self.agent.state.value('heated_mass_kg'))

    def test_energy_only_does_not_call_market_or_literature_recommendation_tools(self):
        self.first()
        reply=self.agent.ask('Сравнивать не надо, рассчитай энергозатраты нагрева')
        # Explicit comparison language is ambiguous, so use a direct energy question.
        reply=self.agent.ask('Какие энергозатраты нагрева?')
        self.assertEqual(reply['policy_tool_plan'],['estimate_process_energy'])


if __name__ == '__main__':
    unittest.main()
