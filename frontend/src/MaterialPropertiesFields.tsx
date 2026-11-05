import type { ComponentInput } from './advisorApi'
import type { AdvisorCatalog } from './advisorApi'
export default function MaterialPropertiesFields({row,index,onChange,catalog}:{row:ComponentInput;index:number;onChange:(patch:Partial<ComponentInput>)=>void;catalog:AdvisorCatalog}){
 const manure=row.material==='manure'||row.material.endsWith('_manure')
 const inferred=catalog.ui.animals.find(option=>option.material===row.material)?.value??'unknown'
 const isPoultry=row.animal==='poultry'||inferred==='poultry'
 return <div className="advisor-input-grid material-axes" data-testid="material-axes">
 {manure&&<label>Вид животного {index}<select aria-label={`Вид животного ${index}`} value={row.animal??inferred} onChange={e=>{const option=catalog.ui.animals.find(item=>item.value===e.target.value);if(option)onChange({animal:option.value,material:option.material??row.material,poultry_type:'unknown',reference_profile_id:null,properties:{}})}}>{catalog.ui.animals.filter(option=>option.value==='unknown'||option.material===row.material||row.material==='manure').map(option=><option value={option.value} key={option.value}>{option.label}</option>)}</select></label>}
 {isPoultry&&<label>Тип птичьего помёта {index}<select aria-label={`Тип птичьего помёта ${index}`} value={row.poultry_type??'unknown'} onChange={e=>onChange({poultry_type:e.target.value,reference_profile_id:null})}>{catalog.ui.poultry_types.map(option=><option value={option.value} key={option.value}>{option.label}</option>)}</select></label>}
 <label>Степень разложения {index}<select aria-label={`Степень разложения ${index}`} value={row.decay_state??(row.material_state==='compost'?'composted':'unknown')} onChange={e=>onChange({decay_state:e.target.value,reference_profile_id:null})}>{catalog.ui.decay_states.map(option=><option value={option.value} key={option.value}>{option.label}</option>)}</select></label>
 {manure&&<label>Подстилка {index}<select aria-label={`Подстилка ${index}`} value={row.bedding??'unknown'} onChange={e=>onChange({bedding:e.target.value,reference_profile_id:null,...(e.target.value!=='unknown'&&e.target.value!=='none'&&row.physical_state!=='dry'?{physical_state:'bedded',material_state:'bedded'}:{})})}>{catalog.ui.beddings.map(option=><option value={option.value} key={option.value}>{option.label}</option>)}</select></label>}
 <label>Данные {index}<select aria-label={`Данные ${index}`} value={row.data_mode??'LITERATURE_ESTIMATE'} onChange={e=>onChange({data_mode:e.target.value,reference_profile_id:null})}>{catalog.ui.data_modes.map(option=><option value={option.value} key={option.value}>{option.label}</option>)}</select></label>
 {row.data_mode==='ILLUSTRATIVE_ASSUMPTION'&&<p>Условные свойства и перенос между исследованиями будут показаны отдельно. Неизвестная плотность сухого навоза не подставляется.</p>}
 </div>
}
