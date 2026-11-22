// design-v3: two concepts while the user chooses. ?concept=a|b in the address (kept in localStorage), default A.
// The value goes to <html data-concept>, which switches the whole palette (design.css :root[data-concept]).
export type Concept = 'a' | 'b'
const KEY = 'bioreactor.concept'

export function concept(): Concept {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('concept')
    if (fromUrl === 'a' || fromUrl === 'b') { localStorage.setItem(KEY, fromUrl); return fromUrl }
    const stored = localStorage.getItem(KEY)
    return stored === 'b' ? 'b' : 'a'
  } catch {
    return 'a'
  }
}

export function applyConcept(): void {
  if (typeof document !== 'undefined') document.documentElement.dataset.concept = concept()
}
