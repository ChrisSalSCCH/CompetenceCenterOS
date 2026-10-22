import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import './app.css'

const root = document.getElementById('root')!
const app = (
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

// SSG: if the root already has pre-rendered HTML, hydrate instead of full render.
// This avoids a flash of empty content and lets React attach to existing DOM.
if (root.innerHTML.trim()) {
  ReactDOM.hydrateRoot(root, app)
} else {
  ReactDOM.createRoot(root).render(app)
}
