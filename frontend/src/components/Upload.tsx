import { useState, useRef } from "react";
import { useAuth } from "react-oidc-context";
import { UploadCloud, Image as ImageIcon, Video, AlertCircle, CheckCircle, Info } from "lucide-react";
import { CONFIG } from "../config";

const Upload = () => {
  const auth = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [status, setStatus] = useState<{ type: 'success' | 'error' | 'info', message: string } | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const processFile = (selectedFile: File) => {
    setFile(selectedFile);
    setStatus(null);
    
    // Create preview
    const url = URL.createObjectURL(selectedFile);
    setPreview(url);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      if (droppedFile.type.startsWith('image/') || droppedFile.type.startsWith('video/')) {
        processFile(droppedFile);
      } else {
        setStatus({ type: 'error', message: 'Please upload an image or video file.' });
      }
    }
  };

  const toBase64 = (f: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === 'string') {
          // Extract just the base64 part, dropping the data URL prefix
          resolve(reader.result.split(',')[1]);
        }
      };
      reader.onerror = reject;
      reader.readAsDataURL(f);
    });
  };

  const handleUpload = async () => {
    if (!file) return;

    setIsUploading(true);
    setStatus({ type: 'info', message: 'Uploading file to cloud storage...' });

    try {
      const base64 = await toBase64(file);
      const token = auth.user?.id_token || auth.user?.access_token;

      const response = await fetch(`${CONFIG.API_URL}/upload`, {
        method: 'POST',
        headers: {
          'Authorization': token || '',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          file_content: base64,
          file_name: file.name,
          file_type: file.type,
          file_size: file.size
        })
      });

      const result = await response.json();

      if (response.status === 409) {
        setStatus({ type: 'error', message: '⚠️ Duplicate file! This file has already been uploaded.' });
      } else if (response.ok) {
        setStatus({ type: 'success', message: '✅ Upload successful! The file is being processed.' });
        setFile(null);
        setPreview(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
      } else {
        setStatus({ type: 'error', message: `❌ Upload failed: ${result.error || 'Unknown error'}` });
      }
    } catch (err: any) {
      setStatus({ type: 'error', message: `❌ Error: ${err.message}` });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <div className="card">
        <div className="flex items-center gap-2 mb-6">
          <UploadCloud size={28} color="var(--color-primary)" />
          <h2>Upload Wildlife Media</h2>
        </div>
        
        <p className="text-muted mb-6">
          Upload an image or video. Our machine learning model will automatically analyze it to detect species and tag it in the database.
        </p>

        {/* Status Message */}
        {status && (
          <div className={`alert alert-${status.type}`}>
            {status.type === 'error' && <AlertCircle size={20} />}
            {status.type === 'success' && <CheckCircle size={20} />}
            {status.type === 'info' && <Info size={20} />}
            <span>{status.message}</span>
          </div>
        )}

        {/* Drag & Drop Zone */}
        {!file && (
          <div 
            onClick={() => fileInputRef.current?.click()}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            style={{
              border: `2px dashed ${isDragging ? 'var(--color-primary)' : 'var(--color-border)'}`,
              borderRadius: 'var(--radius-lg)',
              padding: '4rem 2rem',
              textAlign: 'center',
              cursor: 'pointer',
              backgroundColor: isDragging ? 'rgba(64, 145, 108, 0.05)' : 'transparent',
              transition: 'all 0.2s ease',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1rem', color: 'var(--color-text-muted)' }}>
              <UploadCloud size={48} />
            </div>
            <h3 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>Click or drag file to this area to upload</h3>
            <p className="text-muted text-sm">Supports: JPG, PNG, MP4, MOV (Max 10MB recommended)</p>
          </div>
        )}

        <input 
          type="file" 
          ref={fileInputRef} 
          style={{ display: 'none' }} 
          accept="image/*,video/*"
          onChange={handleFileChange}
        />

        {/* Preview Area */}
        {file && preview && (
          <div style={{ 
            background: 'var(--color-bg)', 
            padding: '1.5rem', 
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--color-border)',
            textAlign: 'center'
          }}>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.5rem' }}>
              {file.type.startsWith('image/') ? (
                <img src={preview} alt="Preview" style={{ maxHeight: '350px', maxWidth: '100%', borderRadius: 'var(--radius-md)', objectFit: 'contain' }} />
              ) : (
                <video src={preview} controls style={{ maxHeight: '350px', maxWidth: '100%', borderRadius: 'var(--radius-md)' }} />
              )}
            </div>
            
            <div className="flex items-center justify-between" style={{ background: 'white', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)' }}>
              <div className="flex items-center gap-3">
                {file.type.startsWith('image/') ? <ImageIcon size={20} className="text-muted" /> : <Video size={20} className="text-muted" />}
                <div style={{ textAlign: 'left' }}>
                  <p style={{ margin: 0, fontWeight: 500, fontSize: '0.875rem' }}>{file.name}</p>
                  <p style={{ margin: 0, fontSize: '0.75rem' }} className="text-muted">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
                </div>
              </div>
              <button 
                onClick={() => { setFile(null); setPreview(null); setStatus(null); if(fileInputRef.current) fileInputRef.current.value = ''; }}
                className="btn btn-outline"
                style={{ padding: '0.4rem 0.8rem', fontSize: '0.875rem' }}
                disabled={isUploading}
              >
                Change File
              </button>
            </div>

            <button 
              className="btn btn-primary w-full mt-4" 
              onClick={handleUpload}
              disabled={isUploading}
              style={{ padding: '1rem', fontSize: '1.1rem' }}
            >
              {isUploading ? 'Uploading & Analyzing...' : 'Upload File to Cloud'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default Upload;
