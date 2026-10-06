import React, { createContext, useState, useEffect, ReactNode } from 'react';
import { MeResponse } from '../types';
import {
  apiFetch,
  AUTH_INVALID_EVENT,
  clearAuthToken,
  getAuthToken,
} from '../api';

interface AuthContextProps {
  user: MeResponse | null;
  setUser: (u: MeResponse | null) => void;
  logout: () => Promise<void>;
  loading: boolean;
}

export const AuthContext = createContext<AuthContextProps | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // Resolve the identity bound to this tab's sessionStorage credential.
  useEffect(() => {
    const handleInvalidAuth = () => setUser(null);
    window.addEventListener(AUTH_INVALID_EVENT, handleInvalidAuth);

    apiFetch('/api/auth/me/')
      .then(res => (res.ok ? res.json() : null))
      .then((data) => setUser(data))
      .catch(() => {
        clearAuthToken();
        setUser(null);
      })
      .finally(() => setLoading(false));

    return () => window.removeEventListener(AUTH_INVALID_EVENT, handleInvalidAuth);
  }, []);

  const logout = async () => {
    const response = await apiFetch('/api/auth/logout/', {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error('Unable to sign out.');
    }
    clearAuthToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, setUser, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};
