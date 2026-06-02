import { useState, useEffect } from "react";
import { useAuth } from "react-oidc-context";
import { Bell, Mail, Target, CheckCircle, XCircle } from "lucide-react";
import { CONFIG } from "../config";

const Alerts = () => {
  const auth = useAuth();
  
  const [email, setEmail] = useState('');
  const [species, setSpecies] = useState('koala');
  const [isSubscribing, setIsSubscribing] = useState(false);
  const [message, setMessage] = useState<{type: 'success' | 'error', text: string} | null>(null);

  // Pre-fill email from auth context
  useEffect(() => {
    if (auth.user?.profile?.email) {
      setEmail(auth.user.profile.email as string);
    }
  }, [auth.user]);

  const getHeaders = () => {
    const token = auth.user?.id_token || auth.user?.access_token;
    return {
      'Authorization': token || '',
      'Content-Type': 'application/json'
    };
  };

  const handleSubscribe = async () => {
    setMessage(null);
    
    if (!email) {
      setMessage({ type: 'error', text: 'Please enter an email address.' });
      return;
    }

    setIsSubscribing(true);
    try {
      const response = await fetch(`${CONFIG.API_URL}/subscribe`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ email, species })
      });
      
      const result = await response.json();
      
      if (response.ok) {
        setMessage({ type: 'success', text: '✅ Successfully subscribed! Please check your email to confirm the subscription.' });
      } else {
        setMessage({ type: 'error', text: `❌ ${result.error || 'Failed to subscribe'}` });
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: `❌ Error: ${err.message}` });
    } finally {
      setIsSubscribing(false);
    }
  };

  const SPECIES_OPTIONS = [
    { value: 'koala', label: 'Koala' },
    { value: 'wombat', label: 'Wombat' },
    { value: 'dingo', label: 'Dingo' },
    { value: 'kangaroo', label: 'Kangaroo' },
    { value: 'possum', label: 'Possum' },
    { value: 'echidna', label: 'Echidna' },
    { value: 'platypus', label: 'Platypus' }
  ];

  return (
    <div style={{ maxWidth: '600px', margin: '0 auto' }}>
      <div className="card">
        <div className="flex items-center gap-2 mb-2">
          <Bell size={28} color="var(--color-primary)" />
          <h2 style={{ margin: 0 }}>Wildlife Alerts</h2>
        </div>
        
        <p className="text-muted mb-8">
          Subscribe to receive email notifications whenever new media containing your favorite species is uploaded to the platform.
        </p>

        <div className="form-group mb-6">
          <label className="form-label flex items-center gap-2">
            <Mail size={16} className="text-muted" />
            Your Email Address
          </label>
          <input 
            type="email" 
            className="form-input" 
            placeholder="your@email.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="form-group mb-8">
          <label className="form-label flex items-center gap-2">
            <Target size={16} className="text-muted" />
            Select Species to Watch
          </label>
          <select 
            className="form-select"
            value={species}
            onChange={(e) => setSpecies(e.target.value)}
          >
            {SPECIES_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        <button 
          className="btn btn-primary w-full justify-center"
          style={{ padding: '1rem', fontSize: '1.1rem' }}
          onClick={handleSubscribe}
          disabled={isSubscribing}
        >
          {isSubscribing ? 'Setting up subscription...' : 'Subscribe to Alerts'}
        </button>

        {message && (
          <div className={`alert alert-${message.type} mt-6`}>
            {message.type === 'error' ? <XCircle size={20} /> : <CheckCircle size={20} />}
            {message.text}
          </div>
        )}
      </div>
    </div>
  );
};

export default Alerts;
