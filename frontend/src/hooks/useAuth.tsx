import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { authApi } from "../lib/api";

interface User {
  id: number;
  name: string;
  email: string;
  role: string;
  company?: string;
  phone?: string;
  address?: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: any) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("talentiq_token");
    if (token) {
      authApi.me()
        .then(setUser)
        .catch(() => localStorage.removeItem("talentiq_token"))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email: string, password: string) => {
    const data = await authApi.login({ email, password });
    localStorage.setItem("talentiq_token", data.access_token);
    setUser(data.user);
  };

  const register = async (formData: any) => {
    const data = await authApi.register(formData);
    localStorage.setItem("talentiq_token", data.access_token);
    setUser(data.user);
  };

  const logout = () => {
    localStorage.removeItem("talentiq_token");
    setUser(null);
    window.location.href = "/login";
  };

  const refreshUser = async () => {
    const u = await authApi.me();
    setUser(u);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
