import type { ReactNode } from "react";

import type { Role, User } from "../types";

export type Page = "assistant" | "products" | "review" | "sources";

const pageLabels: Record<Page, string> = {
  assistant: "Ask knowledge",
  products: "Product master",
  review: "Review queue",
  sources: "Knowledge sources",
};

function allowedPages(role: Role): Page[] {
  if (role === "admin") return ["assistant", "products", "review", "sources"];
  if (role === "reviewer") return ["assistant", "products", "review"];
  return ["assistant", "products"];
}

interface Props {
  user: User;
  page: Page;
  onPage: (page: Page) => void;
  onLogout: () => void;
  children: ReactNode;
}

export function Shell({ user, page, onPage, onLogout, children }: Props) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">N</span>
          <div><strong>Northstar</strong><span>Knowledge Desk</span></div>
        </div>
        <nav aria-label="Main navigation">
          {allowedPages(user.role).map((item) => (
            <button aria-current={page === item ? "page" : undefined} className={page === item ? "nav-item active" : "nav-item"} key={item} onClick={() => onPage(item)} type="button">
              <span className="nav-glyph" aria-hidden="true">{item === "assistant" ? "✦" : item === "products" ? "▦" : item === "review" ? "✓" : "◫"}</span>
              {pageLabels[item]}
            </button>
          ))}
        </nav>
        <div className="sidebar-note"><span className="signal-dot" />Governed index online</div>
        <div className="user-card">
          <span className="avatar">{user.display_name.slice(0, 1)}</span>
          <div><strong>{user.display_name}</strong><span>{user.role}</span></div>
          <button type="button" onClick={onLogout}>Sign out</button>
        </div>
      </aside>
      <main className="workspace">{children}</main>
    </div>
  );
}
