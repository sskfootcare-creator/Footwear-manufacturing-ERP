import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { http, friendlyAxiosError } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = loading, false = anon, object = logged in
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const { data } = await http.get("/auth/me");
      setUser(data);
    } catch {
      setUser(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = async (email, password) => {
    setError("");
    try {
      const { data } = await http.post("/auth/login", { email, password });
      if (data.access_token) {
        localStorage.setItem("token", data.access_token);
      }
      if (data.refresh_token) {
        localStorage.setItem("refresh_token", data.refresh_token);
      }
      setUser(data);
      return true;
    } catch (e) {
      setError(friendlyAxiosError(e));
      return false;
    }
  };

  const logout = async () => {
    try { await http.post("/auth/logout"); } catch {}
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, refresh, error, setError }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
