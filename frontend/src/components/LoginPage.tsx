import { useState } from "react";

import { login } from "../api";
import type { User } from "../types";

interface Props {
  onLogin: (token: string, user: User) => void;
  notice?: string;
}

export function LoginPage({ onLogin, notice = "" }: Props) {
  const [username, setUsername] = useState("employee");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await login(username, password);
      onLogin(result.access_token, result.user);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-thesis" aria-label="Product introduction">
        <div className="brand-lockup inverse">
          <span className="brand-mark" aria-hidden="true">N</span>
          <div><strong>Northstar</strong><span>Knowledge Desk</span></div>
        </div>
        <div className="login-copy">
          <p className="eyebrow">Foreign-trade intelligence, governed</p>
          <h1>Every company answer carries its evidence.</h1>
          <p>Ask across product listings, operating standards, historical quotations, and dated market evidence—without turning uncertainty into fiction.</p>
          <div className="login-rail" aria-label="Trust states">
            <span>Current</span><span>Historical</span><span>Missing</span><span>Conflict</span>
          </div>
        </div>
        <p className="login-footnote">Public demo data is fictional. Private company sources never enter frontend assets.</p>
      </section>
      <section className="login-form-panel">
        <form className="login-form" onSubmit={submit}>
          <p className="eyebrow">Controlled access</p>
          <h2>Open your workspace</h2>
          <p className="form-intro">Use the Employee access details supplied with this demo, or generate local credentials. Reviewer/Admin access is reserved for the demo operator.</p>
          {notice && <div className="session-notice" role="status">{notice}</div>}
          <label htmlFor="username">Username<input id="username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label>
          <label htmlFor="password">Password<input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>
          {error && <div className="inline-error" role="alert">{error}</div>}
          <button className="primary-button" type="submit" disabled={loading}>{loading ? "Verifying…" : "Sign in"}</button>
          <div className="role-hint"><span>Employee</span><span>Reviewer</span><span>Admin</span></div>
        </form>
      </section>
    </main>
  );
}
