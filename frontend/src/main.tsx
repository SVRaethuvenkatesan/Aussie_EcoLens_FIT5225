import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from 'react-oidc-context'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import './index.css'
import { CONFIG } from './config.ts'

const oidcConfig = {
  authority: `https://cognito-idp.${CONFIG.REGION}.amazonaws.com/${CONFIG.USER_POOL_ID}`,
  client_id: CONFIG.CLIENT_ID,
  redirect_uri: window.location.origin,
  response_type: 'code',
  scope: 'email openid profile',
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider {...oidcConfig}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>,
)
