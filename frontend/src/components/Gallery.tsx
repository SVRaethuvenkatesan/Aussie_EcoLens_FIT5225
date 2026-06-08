import { useState, useEffect } from "react";
import { useAuth } from "react-oidc-context";
import { Image as ImageIcon, Video, Calendar, AlertCircle } from "lucide-react";
import { CONFIG } from "../config";

interface UploadedFile {
  file_url: string;
  thumbnail_url: string;
  file_type: string;
  tags: Record<string, number>;
  is_video: boolean;
  original_name: string;
  uploaded_at: string;
}

const Gallery = () => {
  const auth = useAuth();
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!auth.isLoading && auth.isAuthenticated) {
      fetchMyUploads();
    }
  }, [auth.isLoading, auth.isAuthenticated]);

  const fetchMyUploads = async () => {
    setLoading(true);
    setError("");
    try {
      const token = auth.user?.id_token || auth.user?.access_token;
      if (!token) {
        throw new Error("Authentication token not available yet.");
      }
      
      const response = await fetch(`${CONFIG.API_URL}/query/tags`, {
        method: "POST",
        headers: {
          Authorization: token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ action: "my_uploads" }),
      });

      const result = await response.json();
      if (response.ok && result.success) {
        setFiles(result.data.results || []);
      } else {
        setError(result.error || "Failed to load uploads");
      }
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (isoString: string) => {
    if (!isoString) return "Unknown Date";
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString() + " " + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return "Invalid Date";
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2">
          <ImageIcon className="text-primary" /> My Uploads
        </h2>
        <button className="btn btn-outline" onClick={fetchMyUploads} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="alert alert-error">
          <AlertCircle size={20} />
          {error}
        </div>
      )}

      {loading && files.length === 0 ? (
        <div className="text-center py-12">
          <div className="inline-block animate-pulse">
            <ImageIcon size={48} className="text-muted opacity-50" />
          </div>
          <p className="text-muted mt-4">Loading your uploads...</p>
        </div>
      ) : files.length === 0 ? (
        <div className="card text-center py-12 bg-white">
          <ImageIcon size={48} className="text-muted mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium mb-2">No Uploads Yet</h3>
          <p className="text-muted">You haven't uploaded any media yet.</p>
        </div>
      ) : (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "1.5rem" }}>
          {files.map((file, idx) => (
            <div key={idx} className="card p-0 overflow-hidden flex flex-col" style={{ background: "white", transition: "transform 0.2s ease" }}>
              <div style={{ height: "200px", position: "relative", background: "#f8f9fa", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
                {file.thumbnail_url ? (
                  <img src={file.thumbnail_url} alt={file.original_name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                ) : (
                  <div className="text-muted flex flex-col items-center">
                    {file.is_video ? <Video size={32} /> : <ImageIcon size={32} />}
                    <span className="text-xs mt-2">No Thumbnail</span>
                  </div>
                )}
                <div style={{ position: "absolute", top: "0.5rem", right: "0.5rem", background: "rgba(0,0,0,0.6)", color: "white", padding: "0.2rem 0.5rem", borderRadius: "var(--radius-sm)", fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                  {file.is_video ? <Video size={14} /> : <ImageIcon size={14} />}
                  {file.file_type.toUpperCase()}
                </div>
              </div>
              <div className="p-4 flex flex-col gap-3 flex-1">
                <h4 style={{ fontSize: "1rem", margin: 0, wordBreak: "break-all" }}>{file.original_name || "Unnamed File"}</h4>
                
                <div className="flex items-center gap-2 text-muted text-xs">
                  <Calendar size={14} />
                  <span>{formatDate(file.uploaded_at)}</span>
                </div>

                <div className="mt-auto pt-3 border-t">
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(file.tags || {}).length > 0 ? (
                      Object.entries(file.tags).map(([tag, count]) => (
                        <span key={tag} className="badge bg-green-50 text-green-700 border border-green-200 px-2 py-0.5 rounded-full text-xs font-medium" style={{ background: "var(--color-bg)", padding: "2px 8px", borderRadius: "12px", border: "1px solid var(--color-border)" }}>
                          {tag} <span className="opacity-70 ml-1">({count})</span>
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-muted italic">Processing or no tags...</span>
                    )}
                  </div>
                </div>
                <div className="mt-2 flex gap-2">
                   <a href={file.file_url} target="_blank" rel="noreferrer" className="btn btn-outline w-full text-center" style={{ padding: "0.4rem", fontSize: "0.875rem" }}>View Original</a>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Gallery;
