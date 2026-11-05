const aliases:Record<string,string>={advisor:'substrates',mixtures:'substrates',prediction:'substrates',economics:'substrates',optimizer:'substrates',experiments:'substrates'}
export function canonicalRoute(hash:string){const value=hash.replace(/^#\/?/,'');return aliases[value]??(['overview','substrates','chat','reactor','market','science','system','demo'].includes(value)?value:'overview')}
