import { useEffect, useState } from "react";

import { api } from "./api";
import { EvidenceDrawer } from "./components/EvidenceDrawer";
import { LoginPage } from "./components/LoginPage";
import { type Page, Shell } from "./components/Shell";
import { ChatPage } from "./pages/ChatPage";
import { ProductsPage } from "./pages/ProductsPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SourcesPage } from "./pages/SourcesPage";
import type { Citation, User } from "./types";

interface Session { token: string; user: User }

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [page, setPage] = useState<Page>("assistant");
  const [citation, setCitation] = useState<Citation | null>(null);
  const [sessionNotice, setSessionNotice] = useState("");

  useEffect(() => {
    function expireSession() {
      setSession(null);
      setPage("assistant");
      setCitation(null);
      setSessionNotice("Your session expired. Sign in again to continue.");
    }
    window.addEventListener("rag:session-expired", expireSession);
    return () => window.removeEventListener("rag:session-expired", expireSession);
  }, []);

  if (!session) {
    return <LoginPage notice={sessionNotice} onLogin={(token, user) => { setSessionNotice(""); setSession({ token, user }); }} />;
  }

  async function logout() {
    if (!session) return;
    try { await api.logout(session.token); } finally { setSessionNotice(""); setSession(null); setPage("assistant"); setCitation(null); }
  }

  return (
    <Shell user={session.user} page={page} onPage={(next) => { setPage(next); setCitation(null); }} onLogout={() => void logout()}>
      {page === "assistant" && <ChatPage token={session.token} role={session.user.role} onEvidence={setCitation} />}
      {page === "products" && <ProductsPage token={session.token} />}
      {page === "review" && session.user.role !== "employee" && <ReviewPage token={session.token} />}
      {page === "sources" && session.user.role === "admin" && <SourcesPage token={session.token} />}
      <EvidenceDrawer citation={citation} token={session.token} onClose={() => setCitation(null)} />
    </Shell>
  );
}
