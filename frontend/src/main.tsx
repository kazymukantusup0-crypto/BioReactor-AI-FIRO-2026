import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { applyConcept } from './concept'
import './styles.css'
import './design.css'  // last: the design system tokens and components win over older page styles

applyConcept()  // design-v3: <html data-concept> picks the palette before the first paint
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
