"""Stage 8.1 regression coverage. No synthetic measurements are used here."""
from pathlib import Path
import tempfile

import pytest
from fastapi.testclient import TestClient

from src.advisor.catalog import get_catalog
from src.advisor.schemas import AdvisorRequest
from src.market.api import create_app
from src.market.store import Store
from src.agent.conversation import ConversationAgent
from src.agent.providers import HybridLLM
from src.agent.tools import ToolRegistry


def request_component(material, state, quantity=10, unit="kg", **axes):
    return {"id": "sample", "material": material, "material_state": state,
            "quantity": quantity, "unit": unit, **axes}


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory(prefix="stage81-", dir=Path(__file__).parent) as directory:
        store = Store(Path(directory) / "isolated.sqlite3")
        with TestClient(create_app(store, scheduler_enabled=False)) as test_client:
            yield test_client


def test_catalog_exposes_species_states_profiles_and_ui_vocabulary():
    catalog = get_catalog()
    assert {"swine_manure", "poultry_manure", "sheep_goat_manure"} <= {
        material["id"] for material in catalog["materials"]
    }
    poultry = next(x for x in catalog["materials"] if x["id"] == "poultry_manure")
    assert {"slurry", "fresh_solid", "dry", "bedded"} <= {
        option["value"] for option in poultry["form_states"]
    }
    assert {"broiler", "layer", "turkey"} <= {
        option["value"] for option in catalog["ui"]["poultry_types"]
    }
    assert {"straw", "sawdust", "shavings"} <= {
        option["value"] for option in catalog["ui"]["beddings"]
    }


def test_subtype_selects_only_compatible_poultry_study_profile(client):
    base = request_component("poultry_manure", "fresh_solid", animal="poultry")
    layer = {**base, "poultry_type": "layer", "reference_profile_id": "ramos2019-layers-HD-sample1"}
    result = client.post("/api/advisor/analyze", json={"components": [layer]}).json()
    assert result["mixture"]["components"][0]["profile_id"] == "ramos2019-layers-HD-sample1"

    incompatible = {**layer, "poultry_type": "broiler"}
    response = client.post("/api/advisor/analyze", json={"components": [incompatible]})
    assert response.status_code == 422


def test_unmatched_broiler_is_not_given_layer_or_unspecified_profile(client):
    row = request_component("poultry_manure", "fresh_solid", poultry_type="broiler")
    result = client.post("/api/advisor/analyze", json={"components": [row]}).json()
    component = result["mixture"]["components"][0]
    assert component["profile_id"] is None
    assert component["methane_reference_m3"] is None


def test_poultry_dry_transfer_is_visible_and_retains_source_limits(client):
    row = request_component("poultry_manure", "dry", poultry_type="chicken")
    result = client.post("/api/advisor/analyze", json={"components": [row]}).json()
    component = result["mixture"]["components"][0]
    assert component["profile_id"] == "eftaxias2024-poultry"
    assert component["properties_used"]["ts_fraction"]["range"] == {
        "low": 0.6925, "high": 0.6925
    }
    assert any("не образец после специальной сушки" in text for text in component["assumptions"])
    assert result["sources"][0]["id"] == "eftaxias2024"


def test_mass_volume_conversion_requires_density_and_preserves_inventory(client):
    rows = [request_component("swine_manure", "slurry", 100, "kg", animal="pig"),
            request_component("food_waste", "fresh_solid", 5, "kg", id="food")]
    response = client.post("/api/advisor/convert", json={
        "request": {"components": rows}, "target_unit": "L"
    })
    assert response.status_code == 200
    conversions = response.json()["conversions"]
    assert conversions[0]["status"] == "ok"
    assert conversions[0]["value"] == {"low": 100, "high": 100}
    assert conversions[1]["status"] == "needs_input"
    assert conversions[1]["value"] is None


def test_save_load_edit_and_revision_history_are_lossless(client):
    request = {"components": [
        request_component("poultry_manure", "fresh_solid", 12, animal="poultry",
                          poultry_type="layer", reference_profile_id="ramos2019-layers-HD-sample1")
    ]}
    first = client.post("/api/advisor/mixtures", json={"name": "Test only", "request": request,
                                                         "display_units": {"sample": "kg"}})
    assert first.status_code == 201
    saved = first.json()
    changed = {"components": [{**request["components"][0], "quantity": 15}]}
    second = client.post("/api/advisor/mixtures", json={"mixture_id": saved["mixture_id"],
                                                          "name": "Test only", "request": changed,
                                                          "display_units": {"sample": "kg"}})
    assert second.json()["revision"] == 2
    restored = client.get(f"/api/advisor/mixtures/{saved['mixture_id']}?revision=1").json()
    assert restored["request"]["components"][0]["reference_profile_id"] == "ramos2019-layers-HD-sample1"
    assert restored["request"]["components"][0]["quantity"] == 12


def test_handoff_keeps_species_state_profile_and_units(client):
    row = request_component("swine_manure", "slurry", 100, "L", animal="pig")
    handed = client.post("/api/advisor/handoff", json={"request": {"components": [row]},
                                                        "mode": "no_llm"})
    assert handed.status_code == 201
    session = client.get(f"/api/dashboard/chat/sessions/{handed.json()['session_id']}").json()
    inventory = session["memory"]["advanced"]["inventory"]
    assert [(x["material"], x["material_state"], x["quantity"], x["unit"]) for x in inventory] == [
        ("swine_manure", "slurry", 100, "L")
    ]


def test_species_and_state_axes_reject_contradictory_material():
    with pytest.raises(ValueError):
        AdvisorRequest(components=[request_component("swine_manure", "slurry", animal="cattle")])


def test_agent_asks_for_manure_form_before_selecting_a_reference_profile():
    # Use an isolated workspace-local test database; no production state is read.
    with tempfile.TemporaryDirectory(prefix="stage81-dialogue-", dir=Path(__file__).parent) as directory:
        store = Store(Path(directory) / "isolated.sqlite3")
        agent = ConversationAgent(llm=HybridLLM(providers=[]), registry=ToolRegistry(store), research_enabled=True)
        first = agent.ask("У меня 20 кг коровьего навоза. Сколько газа?")
        assert first["pending_question"]["id"] == "advanced-material-state"
        assert first["missing"] == ["physical_state"]
        assert not any(item["tool"] == "estimate_advanced_gas" for item in first["tools"])
        next_turn = agent.ask("Жидкая жижа")
        assert next_turn["pending_question"] is None
        assert next_turn["memory"]["advanced"]["inventory"][0]["material_state"] == "slurry"
