import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Login from './pages/Login';
import App from './App';
import PrivateRoute from './components/PrivateRoute';
import TicketDetail from './pages/TicketDetail';
import AdminAgents from './pages/AdminAgents';
import Dashboard from './pages/Dashboard';

const AppRouter: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <App />
            </PrivateRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <PrivateRoute>
              <Dashboard />
            </PrivateRoute>
          }
        />
        <Route
          path="/tickets/:id"
          element={
            <PrivateRoute>
              <TicketDetail />
            </PrivateRoute>
          }
        />
        <Route
          path="/admin/agents"
          element={
            <PrivateRoute>
              <AdminAgents />
            </PrivateRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  );
};

export default AppRouter;