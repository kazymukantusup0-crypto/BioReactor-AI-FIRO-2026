import {describe,it,expect} from 'vitest'
import {canonicalRoute} from '../src/routes'
describe('Retained dashboard links',()=>{
 it.each(['advisor','mixtures','prediction','economics','optimizer','experiments'])('redirects %s to the unified page',route=>expect(canonicalRoute('#/'+route)).toBe('substrates'))
 it('keeps reactor, market, sources and chat routes',()=>{for(const id of ['reactor','market','science','chat','system'])expect(canonicalRoute('#/'+id)).toBe(id)})
 it('handles an unknown hash without exposing a removed page',()=>expect(canonicalRoute('#/unknown')).toBe('overview'))
})
