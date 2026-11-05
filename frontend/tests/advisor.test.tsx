// TEST ONLY UI fixtures, not measured materials or market data.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DisplayModeProvider, DisplayModeToggle } from '../src/DisplayMode'
import SubstrateAdvisor from '../src/pages/SubstrateAdvisorV81'
import ConversationReply from '../src/ConversationReply'
import { CHAT_ADVISOR_KEY } from '../src/api'
import { advisorApi, type AdvisorCatalog, type AdvisorResult } from '../src/advisorApi'
import type { AgentReply } from '../src/types'

const catalog: AdvisorCatalog = {
 recognized_categories:15,approved_profile_count:3,materials_with_approved_profiles:['cattle_manure','food_waste'],complete_density_solids_bmp_profile_count:1,
 ui:{
  units:[{value:'g',label:'г'},{value:'kg',label:'кг'},{value:'t',label:'т'},{value:'mL',label:'мл'},{value:'L',label:'л'},{value:'m3',label:'м³'}],
  animals:[{value:'unknown',label:'Не уточнён',material:'manure'},{value:'cattle',label:'КРС',material:'cattle_manure'},{value:'pig',label:'Свиньи',material:'swine_manure'},{value:'poultry',label:'Птица',material:'poultry_manure'}],
  decay_states:[{value:'unknown',label:'Не уточнена'},{value:'fresh',label:'Свежий'},{value:'stored',label:'Хранившийся'},{value:'rotted',label:'Перепревший'},{value:'composted',label:'Компостированный'}],
  beddings:[{value:'unknown',label:'Не уточнена'},{value:'none',label:'Без подстилки'},{value:'straw',label:'Солома'}],
  poultry_types:[{value:'unknown',label:'Тип не уточнён'},{value:'chicken',label:'Куриный'},{value:'broiler',label:'Бройлеры'},{value:'layer',label:'Несушки'}],
  data_modes:[{value:'LITERATURE_ESTIMATE',label:'Приблизительные · по источникам'},{value:'MEASURED',label:'Только измеренные'},{value:'ILLUSTRATIVE_ASSUMPTION',label:'Условный сценарий'}],
 },
 materials:[
  {id:'cattle_manure',name:{ru:'TEST навоз',en:'TEST manure',kk:'TEST көң'},physical_states:['slurry','bedded'],form_states:[{value:'unknown',physical_state:'unknown',label:'Не уточнено'},{value:'slurry',physical_state:'liquid',label:'Жидкий'},{value:'bedded',physical_state:'bedded',label:'С подстилкой'}],available_reference_states:['slurry','bedded'],has_numerical_profile:true,support_level:'NUMERICAL_REFERENCE_SCOPED',support_notice:'TEST scoped reference',potential_inhibitors:[],profiles:[]},
  {id:'food_waste',name:{ru:'TEST пищевые отходы',en:'TEST food',kk:'TEST тамақ'},physical_states:['prepared_pulp'],form_states:[{value:'unknown',physical_state:'unknown',label:'Не уточнено'},{value:'prepared_pulp',physical_state:'unknown',label:'Подготовленная пульпа'}],available_reference_states:['prepared_pulp'],has_numerical_profile:true,support_level:'NUMERICAL_REFERENCE_SCOPED',support_notice:'TEST scoped reference',potential_inhibitors:[],profiles:[]},
 ]
}
const result = {status:'needs_input',mixture:{components:[],total_wet_mass_kg:{low:70,high:70},total_ts_kg:null,total_vs_kg:null,sum_separate_volumes_l:null,additive_methane_reference_m3:null,known_component_additive_subtotal_m3:{low:2,high:3},olr_kg_vs_m3_day:null},temperature:{candidate:null,studies:[],missing:[]},duration:{studies:[]},stability:{risks:[]},decision_analysis:{energy:{outputs:{}},feasibility:{status:'UNKNOWN',working_volume_l:null}},sources:[]} as AdvisorResult
function builder(){return render(<DisplayModeProvider><DisplayModeToggle/><SubstrateAdvisor mixture/></DisplayModeProvider>)}
function modeButton(name: string){return within(screen.getByRole('group',{name:'Режим калькулятора'})).getByRole('button',{name})}
function displayButton(name: string){return within(screen.getByRole('group',{name:'Режим отображения'})).getByRole('button',{name})}

describe('Advisor scientific boundaries in the UI',()=>{
 beforeEach(()=>{vi.restoreAllMocks();localStorage.clear();vi.spyOn(advisorApi,'catalog').mockResolvedValue(catalog);vi.spyOn(advisorApi,'mixtures').mockResolvedValue({mixtures:[]})})
 it('has one unified form for one or several materials',async()=>{
  const {container}=builder();await screen.findByText('15',{selector:'strong'})
  expect(screen.getByRole('heading',{name:'Сырьё и смеси'})).toBeVisible();expect(container.querySelectorAll('form')).toHaveLength(1)
  expect(screen.queryByRole('heading',{name:'Substrate Advisor'})).toBeNull();expect(modeButton('Простой')).toHaveAttribute('aria-pressed','true')
  fireEvent.click(modeButton('Научный'));expect(screen.getAllByRole('button',{name:'Добавить материал'})).toHaveLength(1)
 })
 it('keeps inventory and units when leaving and returning to the page',async()=>{
  vi.spyOn(advisorApi,'convert').mockResolvedValue({conversions:[{id:'c1',status:'ok',value:{low:142,high:142},message:'TEST',target_unit:'L'}]})
  const first=builder();await screen.findByText('15',{selector:'strong'});fireEvent.change(screen.getByLabelText('Количество 1'),{target:{value:'142'}});fireEvent.change(screen.getByLabelText('Единицы 1'),{target:{value:'L'}});await waitFor(()=>expect(screen.getByLabelText('Единицы 1')).toHaveValue('L'));first.unmount()
  builder();await screen.findByText('15',{selector:'strong'});expect(screen.getByLabelText('Количество 1')).toHaveValue(142);expect(screen.getByLabelText('Единицы 1')).toHaveValue('L')
 })
 it('uses simple display by default and persists the scientific preference',()=>{
  localStorage.clear();render(<DisplayModeProvider><DisplayModeToggle/></DisplayModeProvider>)
  expect(displayButton('Простой')).toHaveAttribute('aria-pressed','true')
  fireEvent.click(displayButton('Научный'));expect(localStorage.getItem('bioreactor-display-mode')).toBe('scientific')
 })
 it('sends component quantities separately and never supplies density or working volume by default',async()=>{
  const analyze=vi.spyOn(advisorApi,'analyze').mockResolvedValue(result);builder()
  await screen.findByText('15',{selector:'strong'});fireEvent.click(modeButton('Научный'));fireEvent.click(screen.getByRole('button',{name:'Добавить материал'}))
  fireEvent.change(screen.getByLabelText('Количество 2'),{target:{value:'25'}})
  fireEvent.click(screen.getByRole('button',{name:'Получить оценку'}))
  await waitFor(()=>expect(analyze).toHaveBeenCalledOnce());const input=analyze.mock.calls[0][0]
  expect((input.components as {quantity:number}[]).map(x=>x.quantity)).toEqual([50,25]);expect(input.assume_common_dry_gas_basis).toBe(true)
  expect(input.allow_conditional_profiles).toBe(true)
  expect(screen.getByLabelText('Показать условный ориентир смеси, предполагая сопоставимые условия объёма газа')).toBeChecked()
  expect(input.decision).toEqual({reactor:{}});expect(input.components).not.toHaveProperty('density_kg_l')
 })
 it('keeps missing total distinct from a known-parts subtotal',async()=>{
  vi.spyOn(advisorApi,'analyze').mockResolvedValue(result);builder();await screen.findByText('15',{selector:'strong'})
  fireEvent.click(screen.getByRole('button',{name:'Получить оценку'}));await screen.findByTestId('advisor-results')
  expect(screen.getByTestId('advisor-methane')).toHaveTextContent('Нужны данные');expect(screen.getByText(/не его нижняя граница/)).toBeVisible()
 })
 it('changes display without issuing another calculation or changing numbers',async()=>{
  const analyze=vi.spyOn(advisorApi,'analyze').mockResolvedValue(result);builder();await screen.findByText('15',{selector:'strong'})
  fireEvent.click(screen.getByRole('button',{name:'Получить оценку'}));await screen.findByTestId('advisor-results');const before=screen.getByTestId('advisor-methane').textContent
  fireEvent.click(displayButton('Научный'));expect(screen.getByTestId('advisor-methane').textContent).toBe(before);expect(analyze).toHaveBeenCalledOnce()
  expect(screen.getByText('Расчёт и научные подробности').closest('details')).toHaveAttribute('open')
 })
 it('requires recalculation after an inventory edit and keeps the previous saved result labeled',async()=>{
  const analyze=vi.spyOn(advisorApi,'analyze').mockResolvedValue(result);builder();await screen.findByText('15',{selector:'strong'})
  fireEvent.click(screen.getByRole('button',{name:'Получить оценку'}));await screen.findByTestId('advisor-results');fireEvent.change(screen.getByLabelText('Количество 1'),{target:{value:'100'}})
  expect(screen.getByText(/предыдущий расчёт/)).toBeVisible();expect(analyze).toHaveBeenCalledOnce()
 })
 it('hides status codes in the ordinary answer while retaining structured diagnostics',()=>{
  const reply:AgentReply={mode:'deterministic_tools_no_llm',answer:'TEST answer',tools:[],missing:[],provider_status:[],technical_metadata:{TEST:'HYPOTHETICAL_SCENARIO'},user_facing_answer:{paragraphs:['TEST answer'],sections:[{title:'Краткий ответ',body:'TEST answer'}],sources:[],modes:['HYPOTHETICAL_SCENARIO'],assumptions:[],question:null}}
  localStorage.clear();const {container}=render(<DisplayModeProvider><ConversationReply reply={reply}/></DisplayModeProvider>)
  expect(screen.getByText('Условный пример')).toBeVisible();expect(container.querySelector('.conversation-prose')).not.toHaveTextContent('HYPOTHETICAL_SCENARIO');expect(container.querySelector('.conversation-technical')).not.toHaveAttribute('open')
 })
 it('does not collapse a density interval when switching between mass and volume',async()=>{
  const convert=vi.spyOn(advisorApi,'convert').mockResolvedValue({conversions:[{id:'c1',status:'ok',value:{low:12.5,high:13},message:'TEST density range',target_unit:'L'}]})
  builder();await screen.findByText('15',{selector:'strong'});fireEvent.change(screen.getByLabelText('Единицы 1'),{target:{value:'L'}})
  await waitFor(()=>expect(screen.getByText(/Плотность даёт диапазон 12.5–13/)).toBeVisible())
  expect(screen.getByLabelText('Единицы 1')).toHaveValue('kg');expect(screen.getByLabelText('Количество 1')).toHaveValue(50);expect(convert).toHaveBeenCalledOnce()
 })
 it('saves and restores a backend mixture with all component rows',async()=>{
  const request={components:[{id:'c1',material:'cattle_manure',material_state:'slurry',physical_state:'liquid',quantity:40,unit:'kg' as const}],allow_literature_transfer:true}
  const saved={mixture_id:'saved-1',revision:1,name:'TEST blend',created_at:'2026-01-01',request,display_units:{c1:'kg' as const}}
  vi.spyOn(advisorApi,'mixtures').mockResolvedValue({mixtures:[saved]})
  const load=vi.spyOn(advisorApi,'loadMixture').mockResolvedValue(saved)
  vi.spyOn(advisorApi,'saveMixture').mockResolvedValue(saved)
  builder();await screen.findByText('15',{selector:'strong'})
  fireEvent.change(screen.getByLabelText('Название смеси для сохранения'),{target:{value:'TEST blend'}})
  fireEvent.click(screen.getByRole('button',{name:'Сохранить смесь'}));await waitFor(()=>expect(advisorApi.saveMixture).toHaveBeenCalledOnce())
  fireEvent.change(screen.getByLabelText('Сохранённые смеси'),{target:{value:'saved-1'}})
  fireEvent.click(screen.getByRole('button',{name:'Загрузить смесь'}));await waitFor(()=>expect(load).toHaveBeenCalledWith('saved-1'))
  await waitFor(()=>expect(screen.getByLabelText('Количество 1')).toHaveValue(40))
 })
 it('offers only registry profiles compatible with the selected poultry state and subtype',async()=>{
  const poultry={id:'poultry_manure',name:{ru:'TEST poultry',en:'TEST poultry',kk:'TEST poultry'},physical_states:['solid','dry'],form_states:[{value:'unknown',physical_state:'unknown',label:'unknown'},{value:'fresh_solid',physical_state:'solid',label:'solid'},{value:'dry',physical_state:'dry',label:'dry'}],available_reference_states:['fresh_solid','dry'],has_numerical_profile:true,support_level:'NUMERICAL_REFERENCE_SCOPED',support_notice:'TEST scoped profile',potential_inhibitors:[],profiles:[{id:'eftaxias2024-poultry',source_id:'eftaxias2024',material_state:'fresh_solid',matching_states:['fresh_solid','dry'],animals:['poultry'],poultry_types:['unknown','chicken'],beddings:['unknown','none'],approved_scope:'TEST only'},{id:'ramos2019-layers-HD-sample1',source_id:'ramos2019',material_state:'fresh_solid',matching_states:['fresh_solid'],animals:['poultry'],poultry_types:['layer'],beddings:['unknown','none'],approved_scope:'TEST only'}]}
  const expanded={...catalog,materials:[...catalog.materials,poultry]};vi.spyOn(advisorApi,'catalog').mockResolvedValue(expanded)
  const analyze=vi.spyOn(advisorApi,'analyze').mockResolvedValue(result);builder();await screen.findByText('15',{selector:'strong'})
  fireEvent.click(modeButton('Научный'))
  fireEvent.change(screen.getByLabelText('Сырьё 1'),{target:{value:'poultry_manure'}})
  fireEvent.change(screen.getByLabelText('Состояние 1'),{target:{value:'fresh_solid'}})
  fireEvent.change(screen.getByLabelText('Тип птичьего помёта 1'),{target:{value:'layer'}})
  fireEvent.change(screen.getByLabelText('Научный профиль 1'),{target:{value:'ramos2019-layers-HD-sample1'}})
  fireEvent.click(screen.getByRole('button',{name:'Получить оценку'}));await waitFor(()=>expect(analyze).toHaveBeenCalledOnce())
  expect(analyze.mock.calls[0][0].components[0]).toMatchObject({material:'poultry_manure',material_state:'fresh_solid',poultry_type:'layer',reference_profile_id:'ramos2019-layers-HD-sample1'})
 })
 it('provides simple and scientific modes without losing entered batch values',async()=>{
  builder();await screen.findByText('15',{selector:'strong'})
  expect(modeButton('Простой')).toHaveAttribute('aria-pressed','true')
  fireEvent.change(screen.getByLabelText('Количество 1'),{target:{value:'5'}})
  fireEvent.click(modeButton('Научный'))
  expect(screen.getByLabelText('Количество 1')).toHaveValue(5)
  expect(screen.getByText('Измеренные свойства компонента · необязательно')).toBeVisible()
  fireEvent.click(modeButton('Простой'))
  expect(screen.getByLabelText('Количество 1')).toHaveValue(5)
  expect(modeButton('Простой')).toHaveAttribute('aria-pressed','true')
 })
 it('imports chat materials, quantity, volume and confirmed region into the scientific calculator',async()=>{
  const analyze=vi.spyOn(advisorApi,'analyze').mockResolvedValue(result)
  sessionStorage.setItem(CHAT_ADVISOR_KEY,JSON.stringify({language:'ru',facts:{material:{value:'food_waste'},quantity:{value:5},unit:{value:'kg'},reactor_total_volume_l:{value:90},market_region:{value:'KZ-Karaganda-oblast',provenance:'USER_CONFIRMED'}},derived:{},assumptions:{},mixture_components:[]}))
  builder();await screen.findByText('15',{selector:'strong'})
  await waitFor(()=>expect(analyze).toHaveBeenCalled())
  const request=analyze.mock.calls.at(-1)?.[0]
  expect(request?.components[0]).toMatchObject({material:'food_waste',quantity:5,unit:'kg'})
  expect(request?.reactor_total_volume_l).toBe(90)
  expect(request?.region).toBe('KZ-Karaganda-oblast')
  expect(request?.region_confirmed).toBe(true)
  expect(modeButton('Научный')).toHaveAttribute('aria-pressed','true')
  expect(sessionStorage.getItem(CHAT_ADVISOR_KEY)).toBeNull()
 })
 it('keeps hypothetical dilution separate when importing a chat scenario',async()=>{
  const analyze=vi.spyOn(advisorApi,'analyze').mockResolvedValue(result)
  sessionStorage.setItem(CHAT_ADVISOR_KEY,JSON.stringify({language:'ru',facts:{material:{value:'food_waste'},quantity:{value:5},unit:{value:'kg'},dilution_water_l:{value:0}},derived:{},
   assumptions:{dilution_water_l:{value:10,provenance:'ASSUMED_FOR_SCENARIO'}},decision_settings:{reactor:{dilution_water_l:0}},mixture_components:[]}))
  builder();await screen.findByText('15',{selector:'strong'})
  await waitFor(()=>expect(analyze).toHaveBeenCalled())
  const request=analyze.mock.calls.at(-1)?.[0]
  expect(request?.decision?.reactor).toMatchObject({dilution_water_l:10,provenance:'HYPOTHETICAL_SCENARIO'})
 })
 it('hands the exact mixture session to chat without emitting technical JSON',async()=>{
  vi.spyOn(advisorApi,'handoff').mockResolvedValue({session_id:'chat-1',component_count:1,suggested_question:'Оцени экономику этой смеси'})
  builder();await screen.findByText('15',{selector:'strong'});fireEvent.click(screen.getByRole('button',{name:'Передать смесь в чат'}))
  await waitFor(()=>expect(advisorApi.handoff).toHaveBeenCalledOnce())
  expect(localStorage.getItem('bioreactor_chat_session_v4')).toBe('chat-1')
  expect(sessionStorage.getItem('bioreactor_demo_question')).toBe('Оцени экономику этой смеси')
 })
})
