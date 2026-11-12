import {request} from './api'
export interface DemoScenario {id:string;title:string;question:string;inputs:{label:string;value:string|number;unit:string}[]}
export interface DemoRun {id:string;case:string;title:string;question:string;created_at:string;input_notice:string;inputs:DemoScenario['inputs'];
  answer:string;results:{label:string;value:string|number|null;unit:string;provenance:string;formula?:string}[];missing:string[];questions:string[];
  sources:{title:string;url:string;year?:number}[];tools:unknown[];estimate?:{estimation_mode:string;target_days:number|null;scenarios:{id:string;estimation_mode:string;potential_methane_l:{low:number;high:number}|null;assumptions:string[]}[]}|null;verification:{label:string;arithmetic:unknown;scientific:unknown;capacity:unknown};
  explanation:{status:string;text:string|null;message:string;telemetry?:unknown}}
const root='/api/dashboard/firo-demo'
export const firoApi={
  scenarios:(signal?:AbortSignal)=>request<{enabled:boolean;model:string;scenarios:DemoScenario[]}>(root+'/scenarios',{signal}),
  run:(scenario:string)=>request<DemoRun>(root+'/runs',{method:'POST',body:{case:scenario}}),
  get:(id:string,signal?:AbortSignal)=>request<DemoRun>(root+'/runs/'+id,{signal}),
  explain:(id:string)=>request<DemoRun>(root+'/runs/'+id+'/explain',{method:'POST',timeout:75000}),
  cancel:(id:string)=>request<DemoRun>(root+'/runs/'+id+'/cancel',{method:'POST'}),
}
