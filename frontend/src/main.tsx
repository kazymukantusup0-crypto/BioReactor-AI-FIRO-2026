import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles.css'
import './design.css'  // last: the design system tokens and components win over older page styles

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
