import React, { useContext } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';

const NavBar: React.FC = () => {
  const navigate = useNavigate();
  const auth = useContext(AuthContext);

  if (!auth) {
    return null;
  }

  const { user, logout, loading } = auth;

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  if (loading) {
    return null;
  }

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16 items-center">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold shadow-sm">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            </div>
            <div>
              <span className="text-lg font-bold text-slate-900 tracking-tight">Helpdesk</span>
              <span className="ml-2 text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                Workspace
              </span>
            </div>
          </div>

          {user && (
            <div className="flex items-center gap-4">
              <div className="text-right hidden sm:block">
                <p className="text-sm font-medium text-slate-900 leading-none">{user.username}</p>
                <p className="text-xs text-slate-500 mt-1 capitalize font-medium">{user.role || 'Member'}</p>
              </div>

              <div className="h-8 w-px bg-slate-200 hidden sm:block" />

              <button
                onClick={handleLogout}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-xs font-medium rounded-lg text-slate-700 bg-white hover:bg-slate-50 hover:text-slate-900 transition focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
                Sign Out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default NavBar;
