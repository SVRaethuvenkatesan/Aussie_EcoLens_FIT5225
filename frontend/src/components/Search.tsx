import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { Search as SearchIcon, Image as ImageIcon, Video, X, Tag, Link as LinkIcon, UploadCloud, Plus, Minus } from "lucide-react";
import { CONFIG } from "../config";

interface QueryResult {
  file_url: string;
  thumbnail_url?: string;
  file_type: 'image' | 'video';
}

const Search = () => {
  const auth = useAuth();
  
  // States for Tag Search
  const [tagInputs, setTagInputs] = useState([{ species: '', count: 1 }]);
  
  // State for Species Search
  const [speciesQuery, setSpeciesQuery] = useState('');
  
  // State for Thumbnail Search
  const [thumbnailUrl, setThumbnailUrl] = useState('');
  const [thumbnailResult, setThumbnailResult] = useState<string | null>(null);

  // State for File Query
  const [queryFile, setQueryFile] = useState<File | null>(null);
  
  // General UI States
  const [results, setResults] = useState<QueryResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [modalImage, setModalImage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<1|2|3|4>(1);
  const [message, setMessage] = useState<{type: 'error' | 'info', text: string} | null>(null);

  const getHeaders = () => {
    const token = auth.user?.id_token || auth.user?.access_token;
    return {
      'Authorization': token || '',
      'Content-Type': 'application/json'
    };
  };

  const handleAPI = async (path: string, method: string, body?: any) => {
    setIsSearching(true);
    setMessage(null);
    setResults([]);
    setThumbnailResult(null);

    try {
      const options: RequestInit = { method, headers: getHeaders() };
      if (body) options.body = JSON.stringify(body);
      
      const response = await fetch(`${CONFIG.API_URL}${path}`, options);
      const data = await response.json();
      
      if (!response.ok) throw new Error(data.error || 'Request failed');
      
      if (path === '/query/thumbnail') {
         if (data && data.file_url) setThumbnailResult(data.file_url);
         else setMessage({ type: 'info', text: 'No matching full image found.' });
      } else {
         if (data.results && data.results.length > 0) {
           setResults(data.results);
         } else {
           setMessage({ type: 'info', text: 'No results found.' });
         }
      }
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setIsSearching(false);
    }
  };

  // 1. Tag Search
  const searchByTags = () => {
    const body: Record<string, number> = {};
    tagInputs.forEach(t => {
      if (t.species.trim()) body[t.species.trim().toLowerCase()] = t.count;
    });
    
    if (Object.keys(body).length === 0) {
      setMessage({ type: 'error', text: 'Enter at least one species' });
      return;
    }
    handleAPI('/query/tags', 'POST', body);
  };

  // 2. Species Search
  const searchBySpecies = () => {
    if (!speciesQuery.trim()) {
      setMessage({ type: 'error', text: 'Enter a species name' });
      return;
    }
    handleAPI('/query/species', 'POST', { species: speciesQuery.trim().toLowerCase() });
  };

  // 3. Thumbnail URL
  const searchByThumbnail = () => {
    if (!thumbnailUrl.trim()) {
      setMessage({ type: 'error', text: 'Enter thumbnail URL' });
      return;
    }
    handleAPI(`/query/thumbnail?thumbnail_url=${encodeURIComponent(thumbnailUrl.trim())}`, 'GET');
  };

  // 4. File Query
  const toBase64 = (f: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === 'string') resolve(reader.result.split(',')[1]);
      };
      reader.onerror = reject;
      reader.readAsDataURL(f);
    });
  };

  const searchByFile = async () => {
    if (!queryFile) {
      setMessage({ type: 'error', text: 'Select a file first' });
      return;
    }
    try {
      setIsSearching(true);
      const base64 = await toBase64(queryFile);
      await handleAPI('/query/file', 'POST', {
        file_content: base64,
        file_name: queryFile.name,
        file_type: queryFile.type
      });
    } catch(err) {
      console.error(err);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <SearchIcon size={28} color="var(--color-primary)" />
        <h2 style={{ margin: 0 }}>Search Wildlife</h2>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '2rem', alignItems: 'start' }}>
        
        {/* Left Column: Query Controls */}
        <div className="flex flex-col gap-4">
          
          {/* Query Type 1: Tags + Count */}
          <div className="card" style={{ padding: '1.5rem', border: activeTab === 1 ? '2px solid var(--color-primary)' : '' }} onClick={() => setActiveTab(1)}>
            <div className="flex items-center gap-2 mb-2">
              <Tag size={18} color="var(--color-primary)" />
              <h3 style={{ fontSize: '1.1rem', margin: 0 }}>Search by Tags & Counts</h3>
            </div>
            <p className="text-sm text-muted mb-4">Find media containing minimum counts of specific animals (AND logic).</p>
            
            {activeTab === 1 && (
              <div className="flex flex-col gap-3">
                {tagInputs.map((t, i) => (
                  <div key={i} className="flex gap-2">
                    <input 
                      type="text" 
                      className="form-input" 
                      placeholder="Species (e.g. koala)"
                      value={t.species}
                      onChange={(e) => { const newInputs = [...tagInputs]; newInputs[i].species = e.target.value; setTagInputs(newInputs); }}
                    />
                    <input 
                      type="number" 
                      className="form-input" 
                      placeholder="Min count" 
                      min="1" 
                      style={{ width: '100px' }}
                      value={t.count}
                      onChange={(e) => { const newInputs = [...tagInputs]; newInputs[i].count = parseInt(e.target.value)||1; setTagInputs(newInputs); }}
                    />
                    {i > 0 && (
                      <button className="btn btn-outline" style={{ padding: '0 0.5rem', border: 'none' }} onClick={() => setTagInputs(tagInputs.filter((_, idx) => idx !== i))}>
                        <Minus size={16} />
                      </button>
                    )}
                  </div>
                ))}
                <button className="btn btn-outline w-full mt-2 text-sm" onClick={() => setTagInputs([...tagInputs, {species: '', count: 1}])}>
                  <Plus size={16} /> Add Another Species
                </button>
                <button className="btn btn-primary w-full mt-2" onClick={searchByTags} disabled={isSearching}>
                  {isSearching ? 'Searching...' : 'Search Tags'}
                </button>
              </div>
            )}
          </div>

          {/* Query Type 2: Species */}
          <div className="card" style={{ padding: '1.5rem', border: activeTab === 2 ? '2px solid var(--color-primary)' : '' }} onClick={() => setActiveTab(2)}>
            <div className="flex items-center gap-2 mb-2">
              <SearchIcon size={18} color="var(--color-primary)" />
              <h3 style={{ fontSize: '1.1rem', margin: 0 }}>Search by Species</h3>
            </div>
            <p className="text-sm text-muted mb-4">Find all media containing a specific species.</p>
            
            {activeTab === 2 && (
              <div className="flex flex-col gap-3">
                <input 
                  type="text" 
                  className="form-input" 
                  placeholder="e.g. dingo"
                  value={speciesQuery}
                  onChange={(e) => setSpeciesQuery(e.target.value)}
                />
                <button className="btn btn-primary w-full" onClick={searchBySpecies} disabled={isSearching}>
                  {isSearching ? 'Searching...' : 'Search Species'}
                </button>
              </div>
            )}
          </div>

          {/* Query Type 3: Thumbnail URL */}
          <div className="card" style={{ padding: '1.5rem', border: activeTab === 3 ? '2px solid var(--color-primary)' : '' }} onClick={() => setActiveTab(3)}>
            <div className="flex items-center gap-2 mb-2">
              <LinkIcon size={18} color="var(--color-primary)" />
              <h3 style={{ fontSize: '1.1rem', margin: 0 }}>Find via Thumbnail URL</h3>
            </div>
            <p className="text-sm text-muted mb-4">Get the full resolution image URL from a thumbnail link.</p>
            
            {activeTab === 3 && (
              <div className="flex flex-col gap-3">
                <input 
                  type="text" 
                  className="form-input" 
                  placeholder="Paste thumbnail URL here"
                  value={thumbnailUrl}
                  onChange={(e) => setThumbnailUrl(e.target.value)}
                />
                <button className="btn btn-primary w-full" onClick={searchByThumbnail} disabled={isSearching}>
                  {isSearching ? 'Searching...' : 'Find Full Image'}
                </button>
              </div>
            )}
          </div>

          {/* Query Type 4: Upload File */}
          <div className="card" style={{ padding: '1.5rem', border: activeTab === 4 ? '2px solid var(--color-primary)' : '' }} onClick={() => setActiveTab(4)}>
            <div className="flex items-center gap-2 mb-2">
              <UploadCloud size={18} color="var(--color-primary)" />
              <h3 style={{ fontSize: '1.1rem', margin: 0 }}>Visual Search</h3>
            </div>
            <p className="text-sm text-muted mb-4">Upload an image to find similar wildlife in our database.</p>
            
            {activeTab === 4 && (
              <div className="flex flex-col gap-3">
                <input 
                  type="file" 
                  className="form-input" 
                  accept="image/*,video/*"
                  onChange={(e) => setQueryFile(e.target.files?.[0] || null)}
                />
                <button className="btn btn-primary w-full" onClick={searchByFile} disabled={isSearching || !queryFile}>
                  {isSearching ? 'Analyzing & Searching...' : 'Upload & Search'}
                </button>
              </div>
            )}
          </div>

        </div>

        {/* Right Column: Results */}
        <div className="card" style={{ minHeight: '500px' }}>
          <h3 className="mb-4">Results</h3>
          
          {message && (
             <div className={`alert alert-${message.type} mb-4`}>
               {message.text}
             </div>
          )}

          {isSearching && !message && (
            <div className="flex justify-center items-center" style={{ height: '200px' }}>
              <div style={{ display: 'inline-block', animation: 'pulse 1.5s infinite' }}>
                <SearchIcon size={40} color="var(--color-primary)" />
              </div>
            </div>
          )}

          {/* Thumbnail URL specific result */}
          {thumbnailResult && (
             <div style={{ background: '#f8fafc', padding: '1.5rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)' }}>
               <p className="mb-2 font-medium">Full Resolution Image Found:</p>
               <a href={thumbnailResult} target="_blank" rel="noreferrer" style={{ wordBreak: 'break-all', fontSize: '0.9rem' }}>
                 {thumbnailResult}
               </a>
             </div>
          )}

          {/* Grid Results (for Queries 1, 2, 4) */}
          {!isSearching && results.length > 0 && (
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', 
              gap: '1rem' 
            }}>
              {results.map((item, idx) => (
                <div key={idx} style={{ 
                  border: '1px solid var(--color-border)', 
                  borderRadius: 'var(--radius-md)', 
                  overflow: 'hidden',
                  background: 'white',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                  cursor: 'pointer'
                }}
                className="hover:shadow-md"
                >
                  {item.file_type === 'image' ? (
                    <div onClick={() => setModalImage(item.file_url)}>
                      <img 
                        src={item.thumbnail_url || item.file_url} 
                        alt="Wildlife" 
                        style={{ width: '100%', height: '140px', objectFit: 'cover', display: 'block' }}
                        onError={(e) => (e.currentTarget.src = 'https://via.placeholder.com/180x140?text=No+Thumbnail')}
                      />
                      <div className="p-2" style={{ padding: '0.75rem', fontSize: '0.75rem', color: 'var(--color-text-muted)', borderTop: '1px solid var(--color-border)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        <ImageIcon size={12} style={{ display: 'inline', marginRight: '4px' }} />
                        {item.file_url.split('/').pop()}
                      </div>
                    </div>
                  ) : (
                    <div>
                      <div style={{ width: '100%', height: '140px', background: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', color: 'var(--color-text-muted)' }}>
                        <Video size={32} />
                        <span className="text-sm mt-2">Video File</span>
                      </div>
                      <div className="p-2" style={{ padding: '0.75rem', fontSize: '0.75rem', color: 'var(--color-text-muted)', borderTop: '1px solid var(--color-border)' }}>
                        <a href={item.file_url} target="_blank" rel="noreferrer" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <LinkIcon size={12} /> Watch Video
                        </a>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {!isSearching && results.length === 0 && !thumbnailResult && !message && (
             <div className="flex flex-col justify-center items-center text-muted" style={{ height: '300px' }}>
                <SearchIcon size={48} style={{ opacity: 0.2, marginBottom: '1rem' }} />
                <p>Run a query to see results here.</p>
             </div>
          )}
        </div>
      </div>

      {/* Lightbox Modal */}
      {modalImage && (
        <div 
          onClick={() => setModalImage(null)}
          style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(15, 23, 42, 0.9)',
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backdropFilter: 'blur(5px)',
            padding: '2rem'
          }}
        >
          <button 
            style={{ position: 'absolute', top: '2rem', right: '2rem', background: 'transparent', border: 'none', color: 'white', cursor: 'pointer' }}
            onClick={() => setModalImage(null)}
          >
            <X size={32} />
          </button>
          <img 
            src={modalImage} 
            alt="Full Resolution" 
            style={{ 
              maxWidth: '100%', 
              maxHeight: '100%', 
              borderRadius: 'var(--radius-lg)',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)'
            }} 
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
};

export default Search;
