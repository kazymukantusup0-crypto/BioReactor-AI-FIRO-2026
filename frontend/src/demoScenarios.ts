// Demo scenarios for the jury. The list lives in demoScenarios.json, shared with
// docs/demo_script.md and scripts/run_demo_scenarios.py (one source of truth, Russian).
// The visible texts in the other languages are in src/i18n/*.json: scenario.<id>.title / .goal / .message.<n>.
// Each button starts a NEW dialog and sends the messages one after another.
import data from './demoScenarios.json'
import { localized, tr } from './i18n'

export interface DemoScenario { id: string; title: string; goal: string; messages: string[]; main?: boolean; noLlm?: boolean }

export const DEMO_SCENARIOS: DemoScenario[] = localized(() => data.scenarios.map(scenario => ({
  ...scenario,
  title: tr(`scenario.${scenario.id}.title`),
  goal: tr(`scenario.${scenario.id}.goal`),
  messages: scenario.messages.map((_, index) => tr(`scenario.${scenario.id}.message.${index + 1}`)),
})))
