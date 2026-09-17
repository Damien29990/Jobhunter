import React from 'react'
import ReactDOM from 'react-dom/client'
import './lib/i18n' // initialize i18n (zh-HK + en) before App
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
