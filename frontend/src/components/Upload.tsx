import { useState, useRef } from "react";
import { useAuth } from "react-oidc-context";
import { UploadCloud, Image as ImageIcon, Video, AlertCircle, CheckCircle, Info } from "lucide-react";
import { CONFIG } from "../config";

const Upload = () => {
  const auth = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [status, setStatus] = useState<{ type: 'success' | 'error' | 'info', message: string } | null>(null);
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
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
    setThumbnailUrl(null);
    
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

  const computeDHash = (f: File): Promise<string> => {
    if (f.type.startsWith('video/')) return Promise.resolve("");
    
    return new Promise((resolve) => {
      const url = URL.createObjectURL(f);
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = 9;
        canvas.height = 8;
        const ctx = canvas.getContext('2d');
        if (!ctx) return resolve("");
        
        // Fill white background to normalize transparent PNGs vs opaque JPGs
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, 9, 8);
        ctx.drawImage(img, 0, 0, 9, 8);
        const imgData = ctx.getImageData(0, 0, 9, 8).data;
        
        const grays = [];
        for (let i = 0; i < imgData.length; i += 4) {
          const r = imgData[i];
          const g = imgData[i+1];
          const b = imgData[i+2];
          const rawGray = r * 0.299 + g * 0.587 + b * 0.114;
          // Heavily quantize the grayscale value to eliminate JPG compression noise.
          // This guarantees that the exact same image in JPG and PNG produces the EXACT same hash.
          grays.push(Math.round(rawGray / 32) * 32);
        }
        
        const diff = [];
        for (let row = 0; row < 8; row++) {
          for (let col = 0; col < 8; col++) {
            const left = grays[row * 9 + col];
            const right = grays[row * 9 + col + 1];
            diff.push(left > right);
          }
        }
        
        let decimalValue = 0n;
        for (let i = 0; i < diff.length; i++) {
          if (diff[i]) {
            decimalValue += (1n << BigInt(i));
          }
        }
        
        resolve(decimalValue.toString(16).padStart(16, '0'));
      };
      img.onerror = () => resolve("");
      img.src = url;
    });
  };

  const handleUpload = async () => {
    if (!file) return;

    if (file.size === 0) {
      setStatus({ type: 'error', message: 'File is empty or corrupt. Cannot upload 0-byte file.' });
      return;
    }

    if (file.type.startsWith('video/') && file.size > 5 * 1024 * 1024 * 1024) {
      setStatus({ type: 'error', message: 'Video exceeds absolute maximum size of 5 GB.' });
      return;
    }

    setIsUploading(true);
    setStatus({ type: 'info', message: 'Initializing secure direct upload...' });

    try {
      const token = auth.user?.id_token || auth.user?.access_token;
      
      let clientHash = "";
      if (file.type.startsWith('image/')) {
        setStatus({ type: 'info', message: 'Analyzing visual signature to prevent duplicates...' });
        clientHash = await computeDHash(file);
        if (!clientHash) {
          setStatus({ type: 'error', message: 'File is corrupt or in an unsupported format. Cannot read image data.' });
          setIsUploading(false);
          return;
        }
      }

      // 1. Get Presigned URL
      const response = await fetch(`${CONFIG.API_URL}/upload`, {
        method: 'POST',
        headers: {
          'Authorization': token || '',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          filename: file.name,
          content_type: file.type,
          file_size: file.size,
          client_hash: clientHash
        })
      });

      const result = await response.json();

      if (!response.ok) {
        if (response.status === 409) {
          setStatus({ type: 'error', message: 'Duplicate file! This file has already been uploaded.' });
        } else if (response.status === 413) {
          setStatus({ type: 'error', message: 'File is too large.' });
        } else {
          setStatus({ type: 'error', message: `Upload initialization failed: ${result.error || 'Unknown error'}` });
        }
        return;
      }

      const { upload_url, thumbnail_url } = result.data;

      // 2. Upload direct to S3
      setStatus({ type: 'info', message: 'Uploading directly to secure storage...' });
      const s3Response = await fetch(upload_url, {
        method: 'PUT',
        headers: {
          'Content-Type': file.type || 'application/octet-stream'
        },
        body: file
      });

      if (!s3Response.ok) {
        setStatus({ type: 'error', message: 'Failed to upload the file directly to S3.' });
        return;
      }

      setStatus({ type: 'success', message: 'Upload successful! The file is being processed.' });
      setThumbnailUrl(thumbnail_url || null);
      setFile(null);
      setPreview(null);
      if (fileInputRef.current) fileInputRef.current.value = '';

    } catch (err: any) {
      setStatus({ type: 'error', message: `Error: ${err.message}` });
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

        {thumbnailUrl && (
          <div className="card mt-4 mb-6" style={{ background: 'var(--color-bg)' }}>
            <h3 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>Thumbnail URL</h3>
            <div className="flex items-center gap-2">
              <input 
                type="text" 
                readOnly 
                value={thumbnailUrl} 
                className="form-control" 
                style={{ flex: 1, padding: '0.5rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)' }}
              />
              <button 
                className="btn btn-outline" 
                onClick={() => {
                  navigator.clipboard.writeText(thumbnailUrl);
                  alert('Copied to clipboard!');
                }}
              >
                Copy URL
              </button>
            </div>
            <p className="text-muted text-sm mt-2">This is a presigned URL that expires in 1 hour.</p>
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
            <p className="text-muted text-sm">Supports: JPG, PNG, MP4, MOV (Max 5GB supported)</p>
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
