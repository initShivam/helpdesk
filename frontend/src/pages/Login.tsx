import React, { useContext, useState } from 'react';
import { AlertCircle, Headset, LoaderCircle } from 'lucide-react';
import { Navigate, useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { AuthContext } from '@/context/AuthContext';
import { MeResponse } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

const Login: React.FC = () => {
  const navigate = useNavigate();
  const auth = useContext(AuthContext);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!auth) {
    return null;
  }

  if (auth.loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-muted/30">
        <LoaderCircle className="size-6 animate-spin text-muted-foreground" aria-label="Loading" />
      </main>
    );
  }

  if (auth.user) {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const csrfResponse = await fetch(`${API_BASE_URL}/api/auth/csrf/`, {
        credentials: 'include',
      });
      if (!csrfResponse.ok) {
        throw new Error('Unable to initialize secure login. Please refresh and try again.');
      }
      const { csrfToken } = await csrfResponse.json();

      const res = await fetch(`${API_BASE_URL}/api/auth/login/`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ username: username.trim(), password }),
      });

      if (!res.ok) {
        let message = 'Invalid credentials';
        const responseText = await res.text();

        try {
          const data = JSON.parse(responseText);
          message =
            data.detail ||
            data.error ||
            data.non_field_errors?.[0] ||
            responseText ||
            message;
        } catch {
          if (responseText) {
            message = responseText;
          }
        }
        throw new Error(message);
      }

      const data: MeResponse = await res.json();
      auth.setUser(data);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-muted/30 px-4 py-10">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,oklch(0.97_0_0),transparent_55%)]" />

      <Card className="relative w-full max-w-md shadow-lg">
        <CardHeader className="space-y-4 text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <Headset className="size-6" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <CardTitle className="text-2xl">Welcome back</CardTitle>
            <CardDescription>Sign in to access your helpdesk workspace.</CardDescription>
          </div>
        </CardHeader>

        <CardContent>
          {error && (
            <div
              className="mb-5 flex items-start gap-2.5 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
              role="alert"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}

          <form className="space-y-5" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="username">Email or username</Label>
              <Input
                id="username"
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="you@example.com"
                autoComplete="username"
                required
                autoFocus
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
                required
              />
            </div>

            <Button className="w-full" type="submit" size="lg" disabled={isSubmitting}>
              {isSubmitting && <LoaderCircle className="animate-spin" aria-hidden="true" />}
              {isSubmitting ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
};

export default Login;
