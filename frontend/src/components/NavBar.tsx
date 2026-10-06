import React, { useContext, useEffect, useState } from 'react';
import { Activity, Headset, Home, Inbox, LogOut, Menu, Moon, Sun, Users, X } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';

const NavBar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useContext(AuthContext);
  const [menuOpen, setMenuOpen] = useState(false);
  const [logoutError, setLogoutError] = useState('');
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const savedTheme = window.localStorage.getItem('helpdesk-theme');
    if (savedTheme === 'light' || savedTheme === 'dark') return savedTheme;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.classList.toggle('dark', theme === 'dark');
    window.localStorage.setItem('helpdesk-theme', theme);
  }, [theme]);

  if (!auth || auth.loading || !auth.user) return null;

  const { user, logout } = auth;
  const homeActive = location.pathname === '/';
  const ticketsActive = location.pathname === '/tickets' || location.pathname.startsWith('/tickets/');
  const analyticsActive = location.pathname === '/dashboard';
  const agentsActive = location.pathname.startsWith('/admin/');
  const initials = user.username.slice(0, 2).toUpperCase();

  const handleLogout = async () => {
    setLogoutError('');
    try {
      await logout();
      navigate('/login');
    } catch {
      setLogoutError('Unable to sign out. Please try again.');
    }
  };

  const navLinkClass = (active: boolean) =>
    `group flex h-9 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
      active
        ? 'bg-blue-50 text-blue-700'
        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
    }`;

  const navigation = (
    <>
      <div className="flex h-16 items-center gap-3 border-b border-slate-200 px-5">
        <span className="flex size-8 items-center justify-center rounded-md bg-blue-600 text-white">
          <Headset className="size-[18px]" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold tracking-tight text-slate-900">Helpdesk</p>
          <p className="text-[11px] text-slate-500">Support workspace</p>
        </div>
        <button
          type="button"
          onClick={() => setMenuOpen(false)}
          className="ml-auto inline-flex size-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 lg:hidden"
          aria-label="Close navigation menu"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>

      <nav aria-label="Main navigation" className="flex-1 space-y-6 px-3 py-6">
        <section>
          <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">
            Workspace
          </p>
          <div className="space-y-1">
            <Link
              to="/"
              className={navLinkClass(homeActive)}
              aria-current={homeActive ? 'page' : undefined}
            >
              <Home className="size-[17px] shrink-0" aria-hidden="true" />
              <span>Home</span>
            </Link>
            <Link
              to="/tickets"
              className={navLinkClass(ticketsActive)}
              aria-current={ticketsActive ? 'page' : undefined}
            >
              <Inbox className="size-[17px] shrink-0" aria-hidden="true" />
              <span>Tickets</span>
            </Link>
            <Link
              to="/dashboard"
              className={navLinkClass(analyticsActive)}
              aria-current={analyticsActive ? 'page' : undefined}
            >
              <Activity className="size-[17px] shrink-0" aria-hidden="true" />
              <span>Analytics</span>
            </Link>
          </div>
        </section>

        {user.role === 'ADMIN' && (
          <section>
            <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">
              Management
            </p>
            <Link
              to="/admin/agents"
              className={navLinkClass(agentsActive)}
              aria-current={agentsActive ? 'page' : undefined}
            >
              <Users className="size-[17px] shrink-0" aria-hidden="true" />
              <span>Manage agents</span>
            </Link>
          </section>
        )}
      </nav>

      <div className="border-t border-slate-200 p-3">
        {logoutError && <p role="alert" className="px-2 pb-2 text-xs text-red-600">{logoutError}</p>}
        <button
          type="button"
          onClick={() => setTheme((current) => current === 'light' ? 'dark' : 'light')}
          className="mb-2 flex h-9 w-full items-center gap-3 rounded-md px-3 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
          title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
        >
          {theme === 'light' ? <Moon className="size-4" aria-hidden="true" /> : <Sun className="size-4" aria-hidden="true" />}
          <span>{theme === 'light' ? 'Dark theme' : 'Light theme'}</span>
        </button>
        <div className="flex items-center gap-3 rounded-md px-2 py-2">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700">
            {initials}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-800" title={user.username}>{user.username}</p>
            <p className="text-xs capitalize text-slate-500">{user.role?.toLowerCase() || 'Agent'}</p>
          </div>
          <button
            type="button"
            onClick={() => void handleLogout()}
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="size-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </>
  );

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col border-r border-slate-200 bg-white lg:flex">
        {navigation}
      </aside>

      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4 lg:hidden">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-md bg-blue-600 text-white">
            <Headset className="size-[18px]" aria-hidden="true" />
          </span>
          <span className="text-sm font-semibold text-slate-900">Helpdesk</span>
        </Link>
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="Open navigation menu"
          aria-expanded={menuOpen}
          className="inline-flex size-9 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100"
        >
          <Menu className="size-5" aria-hidden="true" />
        </button>
      </header>

      <button
        type="button"
        onClick={() => setTheme((current) => current === 'light' ? 'dark' : 'light')}
        className="fixed right-16 top-2.5 z-30 inline-flex size-9 items-center justify-center rounded-md text-slate-600 transition hover:bg-slate-100 lg:hidden"
        aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
        title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
      >
        {theme === 'light' ? <Moon className="size-4" aria-hidden="true" /> : <Sun className="size-4" aria-hidden="true" />}
      </button>

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/30"
            onClick={() => setMenuOpen(false)}
            aria-label="Close navigation menu"
          />
          <aside className="absolute inset-y-0 left-0 flex w-[min(84vw,280px)] flex-col border-r border-slate-200 bg-white shadow-xl">
            {navigation}
          </aside>
        </div>
      )}
    </>
  );
};

export default NavBar;
