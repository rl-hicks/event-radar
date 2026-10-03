import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth";
import { fetchMe, type MeResponse } from "./lib/api";
import { supabase } from "./lib/supabase";

function HomePage() {
  return (
    <main>
      <h1>Event Radar</h1>
      <p>Your weekend, researched for you.</p>
      <p>This is the E0 product foundation, not the finished subscription product.</p>
      <nav>
        <Link to="/login">Sign in</Link>{" "}
        <Link to="/signup">Create account</Link>
      </nav>
    </main>
  );
}

function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) {
      setMessage("Supabase is not configured for this environment.");
      return;
    }

    const result =
      mode === "login"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });

    setMessage(result.error ? result.error.message : mode === "login" ? "Signed in." : "Account created.");
  }

  return (
    <main>
      <h1>{mode === "login" ? "Sign in" : "Create account"}</h1>
      <form onSubmit={submit}>
        <label>
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button type="submit">{mode === "login" ? "Sign in" : "Sign up"}</button>
      </form>
      {message && <p role="status">{message}</p>}
      <Link to="/">Back to Event Radar</Link>
    </main>
  );
}

function ProtectedAppPage() {
  const { session, loading } = useAuth();
  const [identity, setIdentity] = useState<MeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) {
      return;
    }
    void fetchMe(session.access_token)
      .then((value) => {
        setIdentity(value);
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Backend identity check failed.");
      });
  }, [session]);

  if (loading) {
    return <p>Loading authentication…</p>;
  }
  if (!session) {
    return <Navigate to="/login" replace />;
  }

  return (
    <main>
      <h1>Event Radar foundation</h1>
      <p>Authenticated as {session.user.email ?? session.user.id}</p>
      {identity ? (
        <p role="status">API and database roundtrip confirmed for {identity.id}.</p>
      ) : error ? (
        <p role="alert">{error}</p>
      ) : (
        <p>Checking backend connectivity…</p>
      )}
      <button type="button" onClick={() => void supabase?.auth.signOut()}>
        Sign out
      </button>
    </main>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<AuthForm mode="login" />} />
      <Route path="/signup" element={<AuthForm mode="signup" />} />
      <Route path="/app" element={<ProtectedAppPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
