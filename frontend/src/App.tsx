import { useAuth } from "react-oidc-context";
import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Upload from "./components/Upload";
import Search from "./components/Search";
import Tags from "./components/Tags";
import Alerts from "./components/Alerts";
import Gallery from "./components/Gallery";
import { Leaf, LogIn } from "lucide-react";
import { CONFIG } from "./config";
function App() {
  const auth = useAuth();

  const handleSignUp = async () => {
    try {
      // Create a proper OIDC request to generate state and PKCE verifier
      const request = await auth.userManager.createSigninRequest();
      // AWS Cognito Hosted UI uses /signup for the registration page
      const signupUrl = request.url.replace('/oauth2/authorize', '/signup');
      window.location.href = signupUrl;
    } catch (err) {
      console.error("Failed to generate signup URL", err);
      window.location.href = CONFIG.getSignupUrl(window.location.origin);
    }
  };

  if (auth.isLoading) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="card text-center" style={{ width: '300px' }}>
          <div style={{ display: 'inline-block', animation: 'pulse 2s infinite' }}>
            <Leaf size={40} color="var(--color-primary)" />
          </div>
          <h2 className="mt-4">Loading...</h2>
        </div>
      </div>
    );
  }

  if (auth.error) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="card text-center" style={{ width: '400px' }}>
          <h2 className="text-danger mb-4">Authentication Error</h2>
          <p className="mb-6">{auth.error.message}</p>
          <button className="btn btn-outline w-full" onClick={() => auth.signinRedirect()}>Try Again</button>
        </div>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    return (
      <div style={{ 
        minHeight: '100vh', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        background: 'linear-gradient(135deg, var(--color-primary-dark), var(--color-primary))'
      }}>
        <div className="card text-center" style={{ width: '100%', maxWidth: '420px', margin: '1rem', padding: '3rem 2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.5rem' }}>
            <div style={{ background: 'var(--color-bg)', padding: '1rem', borderRadius: '50%' }}>
              <Leaf size={48} color="var(--color-primary)" />
            </div>
          </div>
          
          <h1 style={{ marginBottom: '0.5rem', color: 'var(--color-primary-dark)' }}>Aussie EcoLens</h1>
          <p className="text-muted" style={{ marginBottom: '2.5rem' }}>Wildlife Observation Platform</p>
          
          <div className="flex flex-col gap-4">
            <button 
              className="btn btn-primary w-full justify-center"
              onClick={() => void auth.signinRedirect()}
              style={{ padding: '1rem' }}
            >
              <LogIn size={20} />
              Sign In
            </button>
            <button 
              className="btn btn-outline w-full justify-center"
              onClick={() => void handleSignUp()}
              style={{ padding: '1rem' }}
            >
              Create Account
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Authenticated State
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/upload" replace />} />
        <Route path="upload" element={<Upload />} />
        <Route path="gallery" element={<Gallery />} />
        <Route path="search" element={<Search />} />
        <Route path="tags" element={<Tags />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="*" element={<Navigate to="/upload" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
