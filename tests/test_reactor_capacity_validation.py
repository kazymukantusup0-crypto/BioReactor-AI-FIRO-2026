"""Deterministic tests for nominal versus working reactor volume."""

from pathlib import Path
import tempfile
import unittest

from src.agent.conversation import ConversationAgent, _attach_capacity_notice
from src.agent.dialogue_memory import fact
from src.agent.dialogue_types import DialogueState
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry
from src.market.store import Store
from src.optimizer.capacity import assess_reactor_capacity, render_capacity_notice
from src.optimizer.constraints import analyze_constraints
from src.optimizer.schemas import ProcessParameters
from src.agent.batch_intent import confirmation


class ReactorCapacityValidationTests(unittest.TestCase):
    def test_batch_confirmation_preserves_volume_and_mass_units(self):
        state=DialogueState(language='ru')
        state.facts.update({'quantity':fact(470,'L'), 'unit':fact('L')})
        volume_confirmation=confirmation(state)
        self.assertIn('объём сырья 470 л',volume_confirmation)
        self.assertNotIn('масса 470 л',volume_confirmation)

        state.facts.update({'quantity':fact(470,'kg'), 'unit':fact('kg')})
        mass_confirmation=confirmation(state)
        self.assertIn('масса 470 кг',mass_confirmation)
        self.assertNotIn('объём сырья 470 кг',mass_confirmation)

    def test_final_postprocessor_corrects_volume_as_mass_and_updates_rendered_sections(self):
        state=DialogueState(language='ru')
        state.facts.update({
            'quantity':fact(470,'L'), 'unit':fact('L'),
            'material_volume_l':fact(470,'L'), 'reactor_total_volume_l':fact(114,'L'),
        })
        assessment=assess_reactor_capacity(feedstock_volume_l=470,reactor_total_volume_l=114)
        reply={
            'answer':'\u0412\u043b\u0430\u0436\u043d\u0430\u044f \u043c\u0430\u0441\u0441\u0430 \u0441\u044b\u0440\u044c\u044f 470 \u043b.',
            'user_facing_answer':{
                'paragraphs':['\u041c\u0430\u0441\u0441\u0430 470 \u043b.'],
                'sections':[{'title':'\u041a\u0440\u0430\u0442\u043a\u0438\u0439 \u043e\u0442\u0432\u0435\u0442','body':'\u041c\u0430\u0441\u0441\u0430 470 \u043b. \u0412\u044b\u0445\u043e\u0434 \u043d\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0451\u043d.'}],
            },
        }
        _attach_capacity_notice(reply,assessment,'ru',state)
        expected='470 литров сырья невозможно одновременно загрузить в реактор номинальной вместимостью 114 литров.'
        corrected='\u043e\u0431\u044a\u0451\u043c \u0441\u044b\u0440\u044c\u044f 470 \u043b'
        self.assertTrue(reply['answer'].startswith(expected))
        self.assertIn(corrected,reply['answer'])
        self.assertNotIn('\u043c\u0430\u0441\u0441\u0430 470 \u043b',reply['answer'].casefold())
        self.assertIn(corrected,reply['user_facing_answer']['paragraphs'][1])
        self.assertNotIn('\u043c\u0430\u0441\u0441\u0430 470 \u043b',reply['user_facing_answer']['paragraphs'][1].casefold())
        self.assertTrue(reply['user_facing_answer']['sections'][0]['body'].startswith(expected))
        self.assertIn(corrected,reply['user_facing_answer']['sections'][0]['body'])

    def test_requested_470_lot_cannot_fit_114_l_nominal_reactor(self):
        result = assess_reactor_capacity(feedstock_volume_l=470, reactor_total_volume_l=114)
        self.assertEqual(result["status"], "EXCEEDS_NOMINAL")
        self.assertIs(result["simultaneous_load_possible"], False)
        self.assertIsNone(result["exact_batch_count"])
        notice = render_capacity_notice(result, "en")
        self.assertIn("cannot be loaded all at once", notice)
        self.assertIn("sequential batches", notice)
        self.assertIn("not a one-cycle yield", notice)
        self.assertNotIn("470 kg", notice)

    def test_equal_nominal_volume_does_not_imply_safe_working_volume(self):
        result = assess_reactor_capacity(feedstock_volume_l=114, reactor_total_volume_l=114)
        self.assertEqual(result["status"], "WORKING_VOLUME_UNKNOWN")
        self.assertIsNone(result["simultaneous_load_possible"])
        self.assertIsNone(result["exact_batch_count"])
        notice = render_capacity_notice(result, "en")
        self.assertIn("working volume is unknown", notice)
        self.assertIn("do not fill to the brim", notice)
        self.assertIn("no room for inoculum or gas headspace", notice)

    def test_float_rounding_near_nominal_is_not_rendered_as_below_nominal(self):
        result = assess_reactor_capacity(feedstock_volume_l=200 - 1e-10, reactor_total_volume_l=200)
        notice = render_capacity_notice(result, "ru")
        self.assertIn("равна номинальной полной вместимости", notice)
        self.assertIn("места нет для инокулята и газового пространства", notice)

    def test_smaller_lots_remain_unconfirmed_when_working_volume_is_unknown(self):
        for volume in (100, 47):
            with self.subTest(volume=volume):
                result = assess_reactor_capacity(feedstock_volume_l=volume, reactor_total_volume_l=114)
                self.assertEqual(result["status"], "WORKING_VOLUME_UNKNOWN")
                self.assertIsNone(result["simultaneous_load_possible"])
                self.assertIsNone(result["exact_batch_count"])

    def test_water_and_inoculum_count_against_working_volume(self):
        exceeds = assess_reactor_capacity(feedstock_volume_l=100, reactor_total_volume_l=114,
                                          reactor_working_volume_l=105, dilution_water_l=4,
                                          inoculum_volume_l=2, resident_liquid_volume_l=0)
        self.assertEqual(exceeds["status"], "EXCEEDS_WORKING_VOLUME")
        self.assertIs(exceeds["simultaneous_load_possible"], False)
        fits = assess_reactor_capacity(feedstock_volume_l=100, reactor_total_volume_l=114,
                                       reactor_working_volume_l=110, dilution_water_l=4,
                                       inoculum_volume_l=2, resident_liquid_volume_l=0)
        self.assertEqual(fits["status"], "WITHIN_DECLARED_WORKING_VOLUME")
        self.assertIn("not process or safety approval", fits["note"])
        unknown = assess_reactor_capacity(feedstock_volume_l=100, reactor_total_volume_l=114,
                                          dilution_water_l=10, inoculum_volume_l=5)
        self.assertEqual(unknown["status"], "WORKING_VOLUME_UNKNOWN")
        self.assertIsNone(unknown["exact_batch_count"])

    def test_sequential_batch_count_is_not_inferred_without_full_charge_inputs(self):
        result = assess_reactor_capacity(feedstock_volume_l=470, reactor_total_volume_l=114,
                                         dilution_water_l=10, inoculum_volume_l=5)
        self.assertEqual(result["status"], "EXCEEDS_NOMINAL")
        self.assertIsNone(result["exact_batch_count"])
        self.assertIn("exact batch count", render_capacity_notice(result, "en"))

    def test_optimizer_exposes_capacity_assessment_for_equal_and_oversize_lots(self):
        for volume, status in ((470, "EXCEEDS_NOMINAL"), (114, "WORKING_VOLUME_UNKNOWN"),
                               (100, "WORKING_VOLUME_UNKNOWN"), (47, "WORKING_VOLUME_UNKNOWN")):
            with self.subTest(volume=volume):
                p = ProcessParameters(material="cattle_manure", feedstock_volume_l=volume,
                                      reactor_total_volume_l=114)
                self.assertEqual(analyze_constraints(p)["capacity_assessment"]["status"], status)

    def test_agent_preflights_and_preserves_lot_and_reactor_volumes(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "TEST.sqlite3")
            agent = ConversationAgent(llm=HybridLLM(providers=[]), registry=ToolRegistry(store))
            prompt = ("\u0423 \u043c\u0435\u043d\u044f 470 \u043b \u0436\u0438\u0434\u043a\u043e\u0433\u043e "
                      "\u043a\u043e\u0440\u043e\u0432\u044c\u0435\u0433\u043e \u043d\u0430\u0432\u043e\u0437\u0430 "
                      "\u0438 \u0440\u0435\u0430\u043a\u0442\u043e\u0440 \u0432\u043c\u0435\u0441\u0442\u0438\u043c\u043e\u0441\u0442\u044c\u044e "
                      "114 \u043b. \u0427\u0442\u043e \u0432\u044b\u0433\u043e\u0434\u043d\u0435\u0435 \u0438 "
                      "\u043a\u0430\u043a\u0443\u044e \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0443 \u0437\u0430\u0434\u0430\u0442\u044c?")
            reply = agent.ask(prompt)
            self.assertEqual(agent.state.value("material_volume_l"), 470)
            self.assertEqual(agent.state.value("reactor_total_volume_l"), 114)
            self.assertIsNone(agent.state.value("mass_kg"))
            self.assertEqual(reply["technical_metadata"]["reactor_capacity_assessment"]["status"], "EXCEEDS_NOMINAL")
            self.assertTrue(reply["answer"].startswith("470 литров сырья невозможно одновременно загрузить в реактор номинальной вместимостью 114 литров."))
            events = reply["technical_metadata"]["diagnostic_events"]
            capacity_index = next(i for i, e in enumerate(events) if e["type"] == "ReactorCapacityChecked")
            understanding_index = next(i for i, e in enumerate(events) if e["type"] == "ModelUnderstandingStarted")
            tool_indices = [i for i, e in enumerate(events) if e["type"] == "ToolExecuted"]
            self.assertLess(capacity_index, understanding_index)
            self.assertTrue(all(capacity_index < i for i in tool_indices))

            followup = agent.ask("\u0410 \u043a\u0430\u043a\u0443\u044e \u0442\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0443 \u043f\u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c?")
            self.assertEqual(agent.state.value("material_volume_l"), 470)
            self.assertEqual(agent.state.value("reactor_total_volume_l"), 114)
            self.assertTrue(followup["answer"].startswith("470 литров сырья невозможно одновременно загрузить в реактор номинальной вместимостью 114 литров."))


if __name__ == "__main__":
    unittest.main()
