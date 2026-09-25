// src/components/PrivateRoute.tsx
import React, { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';

interface PrivateRouteProps {
  children: ReactNode;
}

const PrivateRoute: React.FC<PrivateRouteProps> = ({ children }) => {
  const auth = React.useContext(AuthContext);
  if (!auth) {
    // Context not available – render nothing.
    return null;
  }
  const { user, loading } = auth;
  if (loading) {
    // Show a loading spinner while checking auth status
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <svg className="animate-spin h-8 w-8 text-blue-600" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
          </svg>
          <span className="text-sm text-slate-500">Loading...</span>
        </div>
      </div>
    );
  }
  return user ? <>{children}</> : <Navigate to="/login" replace />;
};

export default PrivateRoute;
