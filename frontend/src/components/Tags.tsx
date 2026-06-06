import { useState } from "react";
import { useAuth } from "react-oidc-context";
import { Tags as TagsIcon, PlusCircle, MinusCircle, Trash2, AlertTriangle, CheckCircle, XCircle, Share2, Unlock, Lock } from "lucide-react";
import { CONFIG } from "../config";

const Tags = () => {
  const auth = useAuth();
  
  const [tagUrls, setTagUrls] = useState('');
  const [tagNames, setTagNames] = useState('');
  const [tagMsg, setTagMsg] = useState<{type: 'success' | 'error', text: string} | null>(null);
  const [isTagging, setIsTagging] = useState(false);

  const [deleteUrls, setDeleteUrls] = useState('');
  const [deleteMsg, setDeleteMsg] = useState<{type: 'success' | 'error', text: string} | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const [shareUrls, setShareUrls] = useState('');
  const [shareMsg, setShareMsg] = useState<{type: 'success' | 'error', text: string} | null>(null);
  const [isSharing, setIsSharing] = useState(false);

  const getHeaders = () => {
    const token = auth.user?.id_token || auth.user?.access_token;
    return {
      'Authorization': token || '',
      'Content-Type': 'application/json'
    };
  };

  const manageTags = async (operation: number) => {
    setTagMsg(null);
    if (!tagUrls.trim() || !tagNames.trim()) {
      setTagMsg({ type: 'error', text: 'Please enter both URLs and tags.' });
      return;
    }

    const urls = tagUrls.split('\n').map(u => u.trim()).filter(Boolean);
    const tags = tagNames.split(',').map(t => t.trim().toLowerCase()).filter(Boolean);

    setIsTagging(true);
    try {
      const response = await fetch(`${CONFIG.API_URL}/tags/manage`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ urls, tags, operation })
      });
      const result = await response.json();
      if (response.ok) {
        setTagMsg({ type: 'success', text: operation === 1 ? 'Tags successfully added!' : 'Tags successfully removed!' });
        if (operation === 1) {
           setTagUrls(''); setTagNames('');
        }
      } else {
        setTagMsg({ type: 'error', text: `${result.error || 'Failed to update tags'}` });
      }
    } catch (err: any) {
      setTagMsg({ type: 'error', text: `Error: ${err.message}` });
    } finally {
      setIsTagging(false);
    }
  };

  const deleteFiles = async () => {
    setDeleteMsg(null);
    if (!deleteUrls.trim()) {
      setDeleteMsg({ type: 'error', text: 'Please enter URLs to delete.' });
      return;
    }

    if (!window.confirm('Are you absolutely sure you want to permanently delete these files? This action cannot be undone.')) {
      return;
    }

    const urls = deleteUrls.split('\n').map(u => u.trim()).filter(Boolean);

    setIsDeleting(true);
    try {
      const response = await fetch(`${CONFIG.API_URL}/files`, {
        method: 'DELETE',
        headers: getHeaders(),
        body: JSON.stringify({ urls })
      });
      const result = await response.json();
      
      if (response.ok) {
        setDeleteMsg({ type: 'success', text: 'Files deleted successfully!' });
        setDeleteUrls('');
      } else {
        setDeleteMsg({ type: 'error', text: `${result.error || 'Failed to delete files'}` });
      }
    } catch (err: any) {
      setDeleteMsg({ type: 'error', text: `Error: ${err.message}` });
    } finally {
      setIsDeleting(false);
    }
  };

  const setTagSharing = async (allow: boolean) => {
    setShareMsg(null);
    if (!shareUrls.trim()) {
      setShareMsg({ type: 'error', text: 'Please enter URLs.' });
      return;
    }

    const urls = shareUrls.split('\n').map(u => u.trim()).filter(Boolean);

    setIsSharing(true);
    try {
      const response = await fetch(`${CONFIG.API_URL}/tags/sharing`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ urls, allow })
      });
      const result = await response.json();
      
      if (response.ok) {
        const failed = result.data?.results?.filter((r: any) => r.status !== 'success');
        if (failed && failed.length > 0) {
          const reason = failed[0].status === 'not_found' ? 'File not found in database.' : 'Unauthorized.';
          setShareMsg({ type: 'error', text: `Failed to update some files: ${reason}` });
        } else {
          setShareMsg({ type: 'success', text: allow ? 'Editing allowed successfully!' : 'Editing disabled successfully!' });
          setShareUrls('');
        }
      } else {
        setShareMsg({ type: 'error', text: `${result.error || 'Failed to update sharing settings'}` });
      }
    } catch (err: any) {
      setShareMsg({ type: 'error', text: `Error: ${err.message}` });
    } finally {
      setIsSharing(false);
    }
  };

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto' }}>
      <div className="flex items-center gap-2 mb-6">
        <TagsIcon size={28} color="var(--color-primary)" />
        <h2 style={{ margin: 0 }}>Data Management</h2>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '2rem' }}>
        
        {/* Manage Tags Card */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <TagsIcon size={20} color="var(--color-primary)" />
            <h3 style={{ margin: 0, fontSize: '1.25rem' }}>Bulk Tagging</h3>
          </div>
          <p className="text-sm text-muted mb-6">Manually add or remove tags from multiple files at once.</p>

          <div className="form-group">
            <label className="form-label">File URLs (One per line)</label>
            <textarea 
              className="form-textarea" 
              placeholder="https://aussie-ecolens...s3.amazonaws.com/uploads/...&#10;https://aussie-ecolens...s3.amazonaws.com/uploads/..."
              value={tagUrls}
              onChange={(e) => setTagUrls(e.target.value)}
            ></textarea>
          </div>

          <div className="form-group">
            <label className="form-label">Tags (Comma separated)</label>
            <input 
              type="text" 
              className="form-input" 
              placeholder="koala, wombat, dingo"
              value={tagNames}
              onChange={(e) => setTagNames(e.target.value)}
            />
          </div>

          <div className="flex gap-4 mt-6">
            <button 
              className="btn btn-primary w-full" 
              onClick={() => manageTags(1)} 
              disabled={isTagging}
            >
              <PlusCircle size={18} /> Add Tags
            </button>
            <button 
              className="btn btn-outline w-full" 
              onClick={() => manageTags(0)} 
              disabled={isTagging}
              style={{ color: 'var(--color-danger)', borderColor: 'var(--color-danger)' }}
            >
              <MinusCircle size={18} /> Remove Tags
            </button>
          </div>

          {tagMsg && (
            <div className={`alert alert-${tagMsg.type} mt-4`}>
              {tagMsg.type === 'error' ? <XCircle size={18} /> : <CheckCircle size={18} />}
              {tagMsg.text}
            </div>
          )}
        </div>

        {/* Share Tags Card */}
        <div className="card" style={{ borderTop: '4px solid var(--color-success)' }}>
          <div className="flex items-center gap-2 mb-4">
            <Share2 size={20} color="var(--color-success)" />
            <h3 style={{ margin: 0, fontSize: '1.25rem' }}>Tag Sharing</h3>
          </div>
          <p className="text-sm text-muted mb-6">Allow or revoke permission for others to edit tags on your files.</p>

          <div className="form-group">
            <label className="form-label">File URLs (One per line)</label>
            <textarea 
              className="form-textarea" 
              placeholder="https://aussie-ecolens...s3.amazonaws.com/uploads/..."
              value={shareUrls}
              onChange={(e) => setShareUrls(e.target.value)}
              style={{ minHeight: '180px' }}
            ></textarea>
          </div>

          <div className="flex gap-4 mt-6">
            <button 
              className="btn btn-outline w-full" 
              onClick={() => setTagSharing(true)} 
              disabled={isSharing}
              style={{ color: 'var(--color-success)', borderColor: 'var(--color-success)' }}
            >
              <Unlock size={18} /> Allow Editing
            </button>
            <button 
              className="btn btn-outline w-full" 
              onClick={() => setTagSharing(false)} 
              disabled={isSharing}
              style={{ color: 'var(--color-warning)', borderColor: 'var(--color-warning)' }}
            >
              <Lock size={18} /> Revoke Editing
            </button>
          </div>

          {shareMsg && (
            <div className={`alert alert-${shareMsg.type} mt-4`}>
              {shareMsg.type === 'error' ? <XCircle size={18} /> : <CheckCircle size={18} />}
              {shareMsg.text}
            </div>
          )}
        </div>

        {/* Delete Files Card */}
        <div className="card" style={{ borderTop: '4px solid var(--color-danger)' }}>
          <div className="flex items-center gap-2 mb-4">
            <Trash2 size={20} color="var(--color-danger)" />
            <h3 style={{ margin: 0, fontSize: '1.25rem', color: 'var(--color-danger)' }}>Delete Files</h3>
          </div>
          <p className="text-sm text-muted mb-6">Permanently remove files and their thumbnails from storage and the database.</p>

          <div className="form-group">
            <label className="form-label">File URLs to delete (One per line)</label>
            <textarea 
              className="form-textarea" 
              placeholder="https://aussie-ecolens...s3.amazonaws.com/uploads/..."
              value={deleteUrls}
              onChange={(e) => setDeleteUrls(e.target.value)}
              style={{ minHeight: '180px' }}
            ></textarea>
          </div>

          <div className="flex gap-4 mt-6">
            <button 
              className="btn btn-danger w-full" 
              onClick={deleteFiles} 
              disabled={isDeleting}
            >
              <AlertTriangle size={18} /> 
              {isDeleting ? 'Deleting...' : 'Permanently Delete Files'}
            </button>
          </div>

          {deleteMsg && (
            <div className={`alert alert-${deleteMsg.type} mt-4`}>
              {deleteMsg.type === 'error' ? <XCircle size={18} /> : <CheckCircle size={18} />}
              {deleteMsg.text}
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

export default Tags;
