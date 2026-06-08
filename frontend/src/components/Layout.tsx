import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "react-oidc-context";
import { Leaf, UploadCloud, Search, Tags, Bell, LogOut, User, Image as ImageIcon } from "lucide-react";
import { CONFIG } from "../config";

const Layout = () => {
  const auth = useAuth();
  
  // Extract user info from token
  const userName = auth.user?.profile?.given_name || auth.user?.profile?.email?.split('@')[0] || "User";

  const navItems = [
    { to: "/upload", icon: <UploadCloud size={18} />, label: "Upload" },
    { to: "/gallery", icon: <ImageIcon size={18} />, label: "My Uploads" },
    { to: "/search", icon: <Search size={18} />, label: "Search" },
    { to: "/tags", icon: <Tags size={18} />, label: "Tags" },
    { to: "/alerts", icon: <Bell size={18} />, label: "Alerts" },
  ];

  const handleLogout = () => {
    // Clear local storage and tokens
    auth.removeUser();
    localStorage.clear();
    sessionStorage.clear();
    window.location.href = CONFIG.getLogoutUrl(window.location.origin);
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Top Navigation */}
      <nav style={{
        background: "rgba(27, 67, 50, 0.6)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderBottom: "1px solid rgba(255, 255, 255, 0.1)",
        color: "white",
        padding: "1rem 2rem",
        position: "sticky",
        top: 0,
        zIndex: 50
      }}>
        <div className="container flex justify-between items-center" style={{ padding: 0 }}>
          
          <div className="flex items-center gap-2" style={{ fontWeight: 600, fontSize: "1.25rem" }}>
            <Leaf size={24} color="var(--color-primary-light)" />
            <span>Aussie EcoLens</span>
          </div>

          <div className="flex items-center" style={{ gap: "2rem" }}>
            {/* Desktop Links */}
            <div className="flex items-center gap-4" style={{ display: "flex" }}>
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  style={({ isActive }) => ({
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    color: isActive ? "white" : "rgba(255,255,255,0.7)",
                    fontWeight: isActive ? 600 : 400,
                    padding: "0.5rem 0.75rem",
                    borderRadius: "var(--radius-md)",
                    background: isActive ? "rgba(255,255,255,0.1)" : "transparent",
                    transition: "all 0.2s"
                  })}
                >
                  {item.icon}
                  {item.label}
                </NavLink>
              ))}
            </div>

            {/* User Menu */}
            <div className="flex items-center gap-4" style={{ borderLeft: "1px solid rgba(255,255,255,0.2)", paddingLeft: "2rem" }}>
              <div className="flex items-center gap-2 text-sm">
                <div style={{ background: "rgba(255,255,255,0.1)", padding: "0.4rem", borderRadius: "50%" }}>
                  <User size={16} />
                </div>
                <span>{userName}</span>
              </div>
              
              <button 
                onClick={handleLogout}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "rgba(255,255,255,0.7)",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  cursor: "pointer",
                  fontSize: "0.875rem",
                  transition: "color 0.2s"
                }}
                onMouseOver={(e) => e.currentTarget.style.color = "white"}
                onMouseOut={(e) => e.currentTarget.style.color = "rgba(255,255,255,0.7)"}
              >
                <LogOut size={16} />
                Logout
              </button>
            </div>
          </div>

        </div>
      </nav>

      {/* Main Content Area */}
      <main className="container page-wrapper" style={{ flex: 1 }}>
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;
