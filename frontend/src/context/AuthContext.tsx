import React, { createContext, useState, useEffect, ReactNode } from 'react';
import { MeResponse } from '../types';

interface AuthContextProps {
  user: MeResponse | null;
  setUser: (u: MeResponse | null) => void;
  logout: () => Promise<void>;
  loading: boolean;
}

export const AuthContext = createContext<AuthContextProps | undefined>(undefined);

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const getCsrfToken = async () => {
    const response = await fetch(`${API_BASE_URL}/api/auth/csrf/`, {
      credentials: 'include',
    });
    if (!response.ok) {
      throw new Error('Unable to initialize secure logout.');
    }
    const data = await response.json();
    return data.csrfToken as string;
  };

  // On mount, fetch current user (session) – this also sets CSRF cookie
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/auth/me/`, { credentials: 'include' })
      .then(res => (res.ok ? res.json() : null))
      .then((data) => setUser(data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const logout = async () => {
    const csrf = await getCsrfToken();
    await fetch(`${API_BASE_URL}/api/auth/logout/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRFToken': csrf },
    });
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, setUser, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};
