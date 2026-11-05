// TEST ONLY data; no market price or scientific measurement fixtures.
import { fireEvent,render,screen,waitFor } from '@testing-library/react'
import { describe,it,expect,vi,beforeEach } from 'vitest'
import MaterialPropertiesFields from '../src/MaterialPropertiesFields'
import ConversationReply from '../src/ConversationReply'
import { DisplayModeProvider } from '../src/DisplayMode'
import type { AgentReply } from '../src/types'
import AdvancedInventoryFacts from '../src/AdvancedInventoryFacts'
import type { AdvisorCatalog } from '../src/advisorApi'
const fieldCatalog: AdvisorCatalog = {
 recognized_categories:1,approved_profile_count:0,materials_with_approved_profiles:[],complete_density_solids_bmp_profile_count:0,
 ui:{
  units:[],animals:[{value:'unknown',label:'Не уточнён',material:'manure'},{value:'cattle',label:'КРС',material:'cattle_manure'},{value:'pig',label:'Свиньи',material:'swine_manure'},{value:'poultry',label:'Птица',material:'poultry_manure'},{value:'horse',label:'Лошади',material:'horse_manure'},{value:'sheep',label:'Овцы',material:'sheep_goat_manure'},{value:'goat',label:'Козы',material:'sheep_goat_manure'}],
  decay_states:[{value:'unknown',label:'Не уточнена'},{value:'fresh',label:'Свежий'},{value:'stored',label:'Хранившийся'},{value:'rotted',label:'Перепревший'},{value:'composted',label:'Компостированный'}],
  beddings:[{value:'unknown',label:'Не уточнена'},{value:'none',label:'Без подстилки'},{value:'straw',label:'Солома'},{value:'sawdust',label:'Опилки'},{value:'shavings',label:'Стружка'},{value:'other',label:'Другая'}],
  poultry_types:[{value:'unknown',label:'Тип не уточнён'},{value:'chicken',label:'Куриный'},{value:'broiler',label:'Бройлеры'},{value:'layer',label:'Несушки'},{value:'turkey',label:'Индейки'}],
  data_modes:[{value:'LITERATURE_ESTIMATE',label:'Приблизительные'},{value:'MEASURED',label:'Измеренные'},{value:'ILLUSTRATIVE_ASSUMPTION',label:'Условные'}],
 },
 materials:[],
}
describe('Independent substrate axes and v8 answers',()=>{
 beforeEach(()=>localStorage.clear())
 it('shows confirmed stock separately from the hypothetical branch',()=>{
  const row={id:'c1',material:'cattle_manure',material_state:'bedded',physical_state:'bedded',quantity:156,unit:'L' as const}
  render(<AdvancedInventoryFacts memory={{inventory:[row],scenario:[{...row,quantity:200}],active_scenario:true}}/>);expect(screen.getByText('156 л')).toBeVisible();expect(screen.getByText('200 л')).toBeVisible();expect(screen.queryByText(/Пока нет подтверждённых/)).toBeNull()
 })
 it('keeps dry and fresh in independent controls',()=>{
  const change=vi.fn();render(<MaterialPropertiesFields row={{id:'c1',material:'cattle_manure',material_state:'dry',physical_state:'dry',quantity:50,unit:'kg'}} index={1} onChange={change} catalog={fieldCatalog}/>);
  fireEvent.change(screen.getByLabelText('Степень разложения 1'),{target:{value:'fresh'}});expect(change).toHaveBeenLastCalledWith({decay_state:'fresh',reference_profile_id:null})
  fireEvent.change(screen.getByLabelText('Подстилка 1'),{target:{value:'straw'}});expect(change).toHaveBeenLastCalledWith({bedding:'straw',reference_profile_id:null})
 })
 it('keeps sheep and goat distinct and changes the species material',()=>{
  const change=vi.fn();render(<MaterialPropertiesFields row={{id:'c1',material:'manure',material_state:'unknown',quantity:1,unit:'kg'}} index={1} onChange={change} catalog={fieldCatalog}/>);
  fireEvent.change(screen.getByLabelText('Вид животного 1'),{target:{value:'goat'}});expect(change).toHaveBeenLastCalledWith({animal:'goat',material:'sheep_goat_manure',poultry_type:'unknown',reference_profile_id:null,properties:{}})
 })
 it('offers measured-only and explicitly illustrative modes',()=>{
  const change=vi.fn();render(<MaterialPropertiesFields row={{id:'c1',material:'cattle_manure',material_state:'bedded',quantity:1,unit:'L'}} index={1} onChange={change} catalog={fieldCatalog}/>);
  fireEvent.change(screen.getByLabelText('Данные 1'),{target:{value:'MEASURED'}});expect(change).toHaveBeenLastCalledWith({data_mode:'MEASURED',reference_profile_id:null})
 })
 it('renders a real v8 clarification contract without diagnostic noise',()=>{
  const answer=vi.fn();const reply={mode:'deterministic_tools_no_llm',answer:'Сохранил все задачи.',tools:[],provider_status:[],technical_metadata:{smart_version:'8.0'},user_facing_answer:{paragraphs:['Сохранил все задачи.'],question:{id:'advanced-species',text:'Это коровий или другой навоз?',options:['Коровий'],fields:['animal']},sources:[],modes:[],assumptions:[]}} as unknown as AgentReply
  render(<DisplayModeProvider><ConversationReply reply={reply} onAnswer={answer}/></DisplayModeProvider>);fireEvent.click(screen.getByRole('button',{name:'Коровий'}));expect(answer).toHaveBeenCalledWith('Коровий');expect(screen.queryByText(/LLM недоступна/)).toBeNull()
 })
})
