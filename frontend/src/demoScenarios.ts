// Demo scenarios for the jury. The list lives in demoScenarios.json, shared with
// docs/demo_script.md and scripts/run_demo_scenarios.py (one source of truth).
// Each button starts a NEW dialog and sends the messages one after another.
import data from './demoScenarios.json'

export interface DemoScenario { id: string; title: string; goal: string; messages: string[]; main?: boolean; noLlm?: boolean }

export const DEMO_SCENARIOS: DemoScenario[] = data.scenarios
