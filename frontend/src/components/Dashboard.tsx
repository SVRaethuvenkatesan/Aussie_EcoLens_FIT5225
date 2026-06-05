import { useState } from 'react';
import { useAuth } from 'react-oidc-context';
import Upload from './Upload';
import Search from './Search';

export default function Dashboard() {
  const auth = useAuth();
  const [activeTab, setActiveTab] = useState<'upload' | 'search'>('search');

  const signOutRedirect = () => {
    const clientId = "3d4m3g86gj50c2erc4vts7aig4";
    const logoutUri = "http://localhost:3000";
    const cognitoDomain = "https://us-east-1yig3u62sm.auth.us-east-1.amazoncognito.com";
    window.location.href = `${cognitoDomain}/logout?client_id=${clientId}&logout_uri=${encodeURIComponent(logoutUri)}`;
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Navigation Bar */}
      <nav style={{ background: 'rgba(15, 23, 42, 0.9)', padding: '1rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>
          <span style={{ color: '#4ade80' }}>Aussie</span> EcoLens
        </h1>
        
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <button 
            onClick={() => setActiveTab('search')} 
            style={{ background: 'transparent', border: 'none', color: activeTab === 'search' ? '#4ade80' : 'white', cursor: 'pointer', fontSize: '1rem', fontWeight: activeTab === 'search' ? 'bold' : 'normal' }}
          >
            Search
          </button>
          <button 
            onClick={() => setActiveTab('upload')} 
            style={{ background: 'transparent', border: 'none', color: activeTab === 'upload' ? '#4ade80' : 'white', cursor: 'pointer', fontSize: '1rem', fontWeight: activeTab === 'upload' ? 'bold' : 'normal' }}
          >
            Upload
          </button>
          
          <div style={{ width: '1px', height: '24px', background: 'rgba(255,255,255,0.2)', margin: '0 0.5rem' }}></div>
          
          <span style={{ color: '#94a3b8', fontSize: '0.9rem' }}>{auth.user?.profile.email}</span>
          <button onClick={signOutRedirect} className="btn-secondary" style={{ marginTop: 0, padding: '0.4rem 1rem', fontSize: '0.8rem', borderColor: '#ef4444', color: '#ef4444' }}>
            Logout
          </button>
        </div>
      </nav>

      {/* Main Content Area */}
      <main style={{ flex: 1, padding: '2rem' }}>
        {activeTab === 'search' ? <Search /> : <Upload />}
      </main>
    </div>
  );
}
