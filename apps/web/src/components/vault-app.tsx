"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CertificateDetail } from "./certificate-detail";
import { ProfileEditor } from "./profile-editor";
import { CollectionManager } from "./collection-manager";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Award,
  Bell,
  Check,
  CheckCheck,
  ChevronRight,
  CloudUpload,
  FileCheck2,
  FolderLock,
  Globe,
  Grid2X2,
  Inbox,
  LayoutDashboard,
  List,
  LoaderCircle,
  LockKeyhole,
  Mail,
  Menu,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Star,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  api,
  type Audit,
  type Certificate,
  type Connection,
  type Draft,
  type ImportItem,
  type Notice,
  type Profile,
  type Settings,
  type Share,
} from "@/lib/api";
import { formatBytes } from "@/lib/utils";

type View =
  | "Overview"
  | "My vault"
  | "Collections"
  | "Approval inbox"
  | "Connected mailboxes"
  | "Activity"
  | "Post studio"
  | "Public profile"
  | "Sharing"
  | "Settings"
  | "Trash";
const nav = [
  { label: "Overview", icon: LayoutDashboard },
  { label: "My vault", icon: FolderLock },
  { label: "Collections", icon: FolderLock },
  { label: "Approval inbox", icon: Inbox },
  { label: "Connected mailboxes", icon: Mail },
  { label: "Activity", icon: Activity },
] as const;
const grow = [
  { label: "Post studio", icon: Sparkles },
  { label: "Public profile", icon: Globe },
  { label: "Sharing", icon: ArrowRight },
] as const;
const emptySettings: Settings = {
  threshold_mib: 50,
  name: "Demo learner",
  hard_cap_mib: 100,
};

export function VaultApp() {
  const [session, setSession] = useState(false),
    [checking, setChecking] = useState(true);
  const [view, setView] = useState<View>("Overview"),
    [mobile, setMobile] = useState(false);
  const [certs, setCerts] = useState<Certificate[]>([]),
    [trash, setTrash] = useState<Certificate[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]),
    [imports, setImports] = useState<ImportItem[]>([]);
  const [notices, setNotices] = useState<Notice[]>([]),
    [history, setHistory] = useState<Audit[]>([]),
    [shares, setShares] = useState<Share[]>([]),
    [drafts, setDrafts] = useState<Draft[]>([]);
  const [settings, setSettings] = useState<Settings>(emptySettings),
    [profile, setProfile] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [toast, setToast] = useState("");
  const [query, setQuery] = useState(""),
    [category, setCategory] = useState("All certificates"),
    [favorites, setFavorites] = useState(false),
    [list, setList] = useState(false);
  const [selected, setSelected] = useState<Certificate | null>(null),
    [modal, setModal] = useState<"connect" | "upload" | "notifications" | null>(
      null,
    );
  const [provider, setProvider] = useState<"gmail" | "outlook">("gmail"),
    [consent, setConsent] = useState(false);
  const [sharePath, setSharePath] = useState(""),
    [draftContent, setDraftContent] = useState(""),
    [draftId, setDraftId] = useState(""),
    [draftCert, setDraftCert] = useState(""),
    [tone, setTone] = useState("professional");
  const [dark, setDark] = useState(false);
  const [selecting, setSelecting] = useState(false),
    [selectedIds, setSelectedIds] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const modalOpener = useRef<HTMLElement | null>(null);
  const approvals = imports.filter((i) => i.status === "awaiting_approval");
  const unread = notices.filter((n) => !n.read).length;
  const [searchResult, setSearchResult] = useState<{
    query: string;
    trashed: boolean;
    items: Certificate[];
  } | null>(null);
  const searchQuery = query.trim();
  const inTrash = view === "Trash";
  const searching =
    !!searchQuery &&
    (searchResult?.query !== searchQuery || searchResult.trashed !== inTrash);
  useEffect(() => {
    if (!session || !searchQuery) return;
    let active = true;
    const timer = setTimeout(() => {
      api<Certificate[]>(
        `/certificates?q=${encodeURIComponent(searchQuery)}&trashed=${inTrash}`,
      )
        .then((items) => {
          if (active)
            setSearchResult({ query: searchQuery, trashed: inTrash, items });
        })
        .catch((e) => {
          if (active) {
            setError(e.message);
            setSearchResult({
              query: searchQuery,
              trashed: inTrash,
              items: [],
            });
          }
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [session, searchQuery, inTrash, certs, trash]);

  async function refresh() {
    const [a, b, c, d, e, f, g, h, i, j] = await Promise.all([
      api<Certificate[]>("/certificates"),
      api<Connection[]>("/connections"),
      api<ImportItem[]>("/imports"),
      api<Notice[]>("/notifications"),
      api<Audit[]>("/audit"),
      api<Settings>("/settings"),
      api<Share[]>("/shares"),
      api<Profile | null>("/profile"),
      api<Draft[]>("/social-drafts"),
      api<Certificate[]>("/certificates?trashed=true"),
    ]);
    setCerts(a);
    setConnections(b);
    setImports(c);
    setNotices(d);
    setHistory(e);
    setSettings(f);
    setShares(g);
    setProfile(h);
    setDrafts(i);
    setTrash(j);
  }
  useEffect(() => {
    api<{ authenticated: boolean }>("/auth/status")
      .then(async (status) => {
        if (status.authenticated) {
          setSession(true);
          await refresh();
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setChecking(false));
    const themeTimer = setTimeout(
      () => setDark(localStorage.getItem("cv-theme") === "dark"),
      0,
    );
    return () => clearTimeout(themeTimer);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("cv-theme", dark ? "dark" : "light");
  }, [dark]);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(id);
  }, [toast]);
  async function run(action: () => Promise<unknown>, message = "") {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
      if (message) setToast(message);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Something went wrong. Please retry.",
      );
    } finally {
      setBusy(false);
    }
  }
  function navigate(next: View) {
    setSelecting(false);
    setSelectedIds([]);
    setView(next);
    setMobile(false);
    setQuery("");
    setCategory("All certificates");
    setFavorites(false);
    setError("");
  }
  function openModal(next: typeof modal) {
    modalOpener.current = document.activeElement as HTMLElement;
    setConsent(false);
    setModal(next);
  }
  const filtered = (
    searchQuery
      ? searching
        ? []
        : searchResult?.items || []
      : inTrash
        ? trash
        : certs
  ).filter(
    (c) =>
      (!favorites || c.favorite) &&
      (category === "All certificates" || c.category === category),
  );
  async function start() {
    await run(async () => {
      await api("/auth/demo", "POST");
      setSession(true);
    }, "Your local workspace is ready.");
  }
  async function upload(file: File | undefined) {
    if (!file) return;
    await run(async () => {
      const body = new FormData();
      body.append("file", file);
      const result = await api<{ duplicate: boolean }>(
        "/certificates/upload",
        "POST",
        body,
      );
      setModal(null);
      setToast(
        result.duplicate
          ? "Already in your vault. Duplicate skipped."
          : "PDF added. Review the title and issuer before sharing.",
      );
    });
  }

  if (checking)
    return (
      <main className="welcome">
        <ShieldCheck size={40} />
        <h1>Opening your workspace</h1>
        <p role="status">Checking your local session…</p>
      </main>
    );
  if (!session)
    return (
      <main className="welcome">
        <div className="welcome-brand">
          <ShieldCheck />
          CertVault
        </div>
        <div className="welcome-grid">
          <section>
            <p className="eyebrow">EVERY ACHIEVEMENT. A PLACE TO BELONG.</p>
            <h1>
              You did the work.
              <br />
              <span>Keep the proof.</span>
            </h1>
            <p className="welcome-copy">
              A quiet home for your biggest milestones. Discover, organize, and
              share your learning — on your terms.
            </p>
            <Button disabled={busy} onClick={start}>
              {busy ? <LoaderCircle className="spin" size={18} /> : null}Explore
              local demo <ArrowRight size={17} />
            </Button>
            <p className="fine-print">
              <LockKeyhole size={14} /> Private by default. Always yours.
            </p>
            <Link className="text-button development-link" href="/account">
              Development account sign-in <ArrowRight size={14} />
            </Link>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
          </section>
          <section className="welcome-note">
            <div className="sample-seal">
              <Award size={64} />
            </div>
            <p className="eyebrow">YOUR NEXT CHAPTER STARTS HERE</p>
            <h2>
              A growing collection
              <br />
              of possibilities.
            </h2>
            <div className="demo-disclosure">
              <strong>Local demonstration</strong>
              <p>
                Uses synthetic certificates and sample mailboxes. No Google or
                Microsoft account is accessed. AI and malware scanning are not
                configured. Use sample documents only.
              </p>
            </div>
          </section>
        </div>
      </main>
    );

  return (
    <div className="app-shell">
      {mobile && (
        <button
          className="mobile-scrim"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <aside className={`sidebar ${mobile ? "is-open" : ""}`}>
        <Link className="brand" href="/" aria-label="CertVault home">
          <div className="brand-icon">
            <ShieldCheck size={22} />
          </div>
          CertVault<span className="brand-dot">.</span>
        </Link>
        <div className="workspace">
          <div className="workspace-avatar">D</div>
          <div>
            <strong>Personal workspace</strong>
            <span>
              Local demo <span className="green-dot" />
            </span>
          </div>
          <ChevronRight size={15} />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Workspace">
          {nav.map(({ label, icon: Icon }) => (
            <button
              key={label}
              aria-label={label}
              aria-current={view === label ? "page" : undefined}
              className={`nav-item ${view === label ? "active" : ""}`}
              onClick={() => navigate(label)}
            >
              <Icon size={19} />
              <span>{label}</span>
              {label === "Approval inbox" && approvals.length > 0 && (
                <span className="count">{approvals.length}</span>
              )}
            </button>
          ))}
        </nav>
        <p className="nav-label grow-label">MAKE IT COUNT</p>
        <nav aria-label="Showcase">
          {grow.map(({ label, icon: Icon }) => (
            <button
              key={label}
              aria-label={label}
              aria-current={view === label ? "page" : undefined}
              className={`nav-item ${view === label ? "active" : ""}`}
              onClick={() => navigate(label)}
            >
              <Icon size={19} />
              <span>{label}</span>
              {label === "Post studio" && (
                <span className="new-label">DRAFTS</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-note">
            <ShieldCheck size={22} />
            <strong>
              Your achievements.
              <br />
              Your permission.
            </strong>
            <p>
              Everything in your vault stays private until you choose to share.
            </p>
          </div>
          <button
            className={`nav-item ${view === "Settings" ? "active" : ""}`}
            onClick={() => navigate("Settings")}
          >
            <Settings2 size={19} />
            Settings & privacy
          </button>
          <button
            className={`nav-item ${view === "Trash" ? "active" : ""}`}
            aria-label="Trash"
            onClick={() => navigate("Trash")}
          >
            <Trash2 size={19} />
            Trash
            {trash.length > 0 && <span className="count">{trash.length}</span>}
          </button>
          <div className="user">
            <div className="user-avatar">
              {settings.name.slice(0, 1).toUpperCase()}
            </div>
            <div>
              <strong>{settings.name}</strong>
              <span>Personal account</span>
            </div>
            <button
              aria-label="Sign out"
              title="Sign out"
              onClick={() =>
                run(async () => {
                  await api("/auth/session", "DELETE");
                  setSession(false);
                })
              }
            >
              <ArrowRight size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <Button
              variant="ghost"
              size="icon"
              className="mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu size={22} />
            </Button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{view}</strong>
          </div>
          <div className="topbar-actions">
            <span className="private-status">
              <LockKeyhole size={13} /> Private workspace
            </span>
            <button
              className="notification-button"
              aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
              onClick={() => openModal("notifications")}
            >
              <Bell size={20} />
              {unread > 0 && <span />}
            </button>
            <div className="user-avatar small">
              {settings.name.slice(0, 1).toUpperCase()}
            </div>
          </div>
        </header>
        <div className="demo-bar">
          <span>
            <span className="status-dot" />
            LOCAL DEMO
          </span>
          <p>
            Synthetic mailboxes · Sample documents only · No live integrations
          </p>
          <button onClick={() => navigate("Settings")}>
            Environment details <ArrowRight size={13} />
          </button>
        </div>
        <main id="main" className="main-content" aria-busy={busy}>
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <Button size="sm" variant="outline" onClick={() => run(refresh)}>
                Retry
              </Button>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              <p className="eyebrow">
                {view === "Overview"
                  ? "YOUR LEARNING, BEAUTIFULLY COLLECTED"
                  : view === "My vault"
                    ? "A COLLECTION THAT GROWS WITH YOU"
                    : "YOUR WORKSPACE, YOUR WAY"}
              </p>
              <h1>
                {view === "Overview"
                  ? "Make room for your next milestone."
                  : view}
              </h1>
              <p>
                {view === "Overview"
                  ? "From your inbox to your next opportunity. Keep every achievement in reach."
                  : view === "My vault"
                    ? "All your hard-earned credentials, thoughtfully organized."
                    : subheading(view)}
              </p>
            </div>
            {["Overview", "My vault"].includes(view) && (
              <Button onClick={() => openModal("upload")}>
                <Plus size={18} />
                Add certificate
              </Button>
            )}
          </div>
          {view === "Overview" && (
            <>
              <section className="hero-panel">
                <div className="hero-copy">
                  <span className="hero-kicker">
                    <span />
                    LESS SEARCHING. MORE BECOMING.
                  </span>
                  <h2>
                    Your inbox holds
                    <br />
                    more than messages.
                  </h2>
                  <p>
                    Give your achievements a home. Connect a sample mailbox to
                    see discovery, imports, and approvals in action.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => openModal("connect")}
                  >
                    {connections.some((c) => c.active)
                      ? "Add sample mailbox"
                      : "Connect sample mailbox"}
                    <ArrowRight size={16} />
                  </Button>
                  <span className="hero-footnote">
                    <ShieldCheck size={13} />
                    You stay in control of every import.
                  </span>
                </div>
                <div className="hero-art" aria-hidden="true">
                  <div className="orbit orbit-one" />
                  <div className="orbit orbit-two" />
                  <div className="floating-paper paper-back" />
                  <div className="floating-paper paper-front">
                    <div className="paper-mark">
                      <Award size={32} />
                    </div>
                    <span>CERTIFICATE OF ACHIEVEMENT</span>
                    <strong>Your next big thing.</strong>
                    <i />
                    <i className="short" />
                    <div className="paper-footer">
                      <span>THE LEARNING JOURNEY</span>
                      <ShieldCheck size={22} />
                    </div>
                  </div>
                  <div className="art-pill">
                    <Check size={14} />A milestone, safely collected
                  </div>
                  <span className="spark spark-one">✧</span>
                  <span className="spark spark-two">+</span>
                </div>
              </section>
              <section className="stats" aria-label="Vault statistics">
                <Stat
                  icon={<Award size={21} />}
                  label="Certificates collected"
                  value={certs.length.toString()}
                  detail="Every milestone, in one place"
                />
                <Stat
                  icon={<Mail size={21} />}
                  label="Connected mailboxes"
                  value={connections.filter((c) => c.active).length.toString()}
                  detail="Sample connections only"
                />
                <Stat
                  icon={<Inbox size={21} />}
                  label="Needs your attention"
                  value={approvals.length.toString()}
                  detail={
                    approvals.length
                      ? "Review before downloading"
                      : "You’re all caught up"
                  }
                  accent={approvals.length > 0}
                />
                <Stat
                  icon={<ShieldCheck size={21} />}
                  label="Privacy by default"
                  value="Always"
                  detail="Sharing is your choice"
                />
              </section>
              {approvals.length > 0 && (
                <button
                  className="approval-callout"
                  onClick={() => navigate("Approval inbox")}
                >
                  <span>
                    <Inbox size={22} />
                    <strong>
                      {approvals.length} import needs your permission
                    </strong>
                    <span>
                      Over your {settings.threshold_mib} MiB auto-download
                      limit.
                    </span>
                  </span>
                  <span>
                    Review import <ArrowRight size={16} />
                  </span>
                </button>
              )}
            </>
          )}
          {["Overview", "My vault", "Trash"].includes(view) && (
            <section className="vault-section">
              <div className="section-heading">
                <div>
                  <h2>
                    {view === "Overview"
                      ? "Your collection"
                      : view === "Trash"
                        ? "Recently removed"
                        : "Certificates"}
                    <span className="number-pill">
                      {view === "Trash" ? trash.length : certs.length}
                    </span>
                  </h2>
                  {view === "Overview" && <p>Small steps. Lasting proof.</p>}
                </div>
                {view === "Overview" && (
                  <button
                    className="text-button"
                    onClick={() => navigate("My vault")}
                  >
                    View all certificates <ArrowRight size={16} />
                  </button>
                )}
              </div>
              <div className="vault-toolbar">
                <div
                  className="filter-tabs"
                  role="group"
                  aria-label="Certificate filter"
                >
                  <button
                    className={!favorites ? "selected" : ""}
                    onClick={() => setFavorites(false)}
                  >
                    All certificates
                  </button>
                  <button
                    className={favorites ? "selected" : ""}
                    onClick={() => setFavorites(true)}
                  >
                    <Star size={14} />
                    Favorites
                  </button>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setSelecting(!selecting);
                    setSelectedIds([]);
                  }}
                >
                  {selecting ? "Cancel selection" : "Select certificates"}
                </Button>
                <div className="search-tools">
                  <label className="search-field">
                    <Search size={17} />
                    <input
                      aria-label="Search certificates"
                      placeholder="Search your collection…"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                  </label>
                  <select
                    aria-label="Filter by category"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                  >
                    <option value="All certificates">Category</option>
                    {["Technology", "Design", "Business", "Other"].map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                  <div className="view-toggle">
                    <button
                      aria-label="Grid view"
                      aria-pressed={!list}
                      onClick={() => setList(false)}
                    >
                      <Grid2X2 size={17} />
                    </button>
                    <button
                      aria-label="List view"
                      aria-pressed={list}
                      onClick={() => setList(true)}
                    >
                      <List size={18} />
                    </button>
                  </div>
                </div>
              </div>
              {selecting && (
                <div className="bulk-toolbar">
                  <strong>{selectedIds.length} selected</strong>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy || !selectedIds.length}
                    onClick={() =>
                      run(async () => {
                        await api("/certificates/bulk", "POST", {
                          certificate_ids: selectedIds,
                          action: "favorite",
                        });
                        setSelectedIds([]);
                        setSelecting(false);
                      }, "Selected certificates favorited.")
                    }
                  >
                    Favorite selected
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy || !selectedIds.length}
                    onClick={() =>
                      run(
                        async () => {
                          await api("/certificates/bulk", "POST", {
                            certificate_ids: selectedIds,
                            action: view === "Trash" ? "restore" : "trash",
                          });
                          setSelectedIds([]);
                          setSelecting(false);
                        },
                        view === "Trash"
                          ? "Selected certificates restored."
                          : "Selected certificates moved to trash; share links revoked.",
                      )
                    }
                  >
                    {view === "Trash"
                      ? "Restore selected"
                      : "Move selected to trash"}
                  </Button>
                </div>
              )}
              {searching ? (
                <div className="empty-state" role="status">
                  Searching certificate metadata and document text…
                </div>
              ) : filtered.length > 0 ? (
                <div className={list ? "certificate-list" : "certificate-grid"}>
                  {filtered.map((c, i) => (
                    <article className="certificate-card" key={c.id}>
                      <button
                        className={`certificate-art ${c.category === "Design" ? "sand" : c.category === "Business" ? "mint" : "blue"}`}
                        onClick={() => {
                          setSelected(c);
                          setSharePath("");
                        }}
                        aria-label={`Preview ${c.title}`}
                      >
                        <div className="mini-brand">{c.issuer}</div>
                        <div className="certificate-line" />
                        <Award size={34} />
                        <span>CERTIFICATE OF ACHIEVEMENT</span>
                        <strong>{c.title}</strong>
                        <div className="mini-footer">
                          <span>SAMPLE CREDENTIAL</span>
                          <span>0{i + 1}</span>
                        </div>
                      </button>
                      <div className="card-info">
                        {selecting && (
                          <label className="checkbox-label select-certificate">
                            <input
                              type="checkbox"
                              aria-label={`Select ${c.title}`}
                              checked={selectedIds.includes(c.id)}
                              onChange={(e) =>
                                setSelectedIds(
                                  e.target.checked
                                    ? [...selectedIds, c.id]
                                    : selectedIds.filter((id) => id !== c.id),
                                )
                              }
                            />
                            Select certificate
                          </label>
                        )}
                        <div className="card-heading">
                          <h3>
                            <button
                              onClick={() => {
                                setSelected(c);
                                setSharePath("");
                              }}
                            >
                              {c.title}
                            </button>
                          </h3>
                          <button
                            className={`star-button ${c.favorite ? "is-favorite" : ""}`}
                            aria-label={`${c.favorite ? "Unfavorite" : "Favorite"} ${c.title}`}
                            aria-pressed={c.favorite}
                            disabled={busy}
                            onClick={() =>
                              run(() =>
                                api(`/certificates/${c.id}/favorite`, "PUT", {
                                  value: !c.favorite,
                                }),
                              )
                            }
                          >
                            <Star
                              size={18}
                              fill={c.favorite ? "currentColor" : "none"}
                            />
                          </button>
                        </div>
                        <p>{c.issuer}</p>
                        {(c.tags || []).length > 0 && (
                          <div className="tag-list">
                            {(c.tags || []).map((tag) => (
                              <span className="tag" key={tag}>
                                #{tag}
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="card-bottom">
                          <span className="tag">{c.category}</span>
                          <span>
                            <LockKeyhole size={12} />
                            Private
                          </span>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-icon">
                    {query || favorites ? (
                      <Search size={30} />
                    ) : (
                      <FolderLock size={30} />
                    )}
                  </div>
                  <h3>
                    {query || favorites
                      ? "No matching achievements"
                      : view === "Trash"
                        ? "Your trash is empty"
                        : "Your story is still being collected."}
                  </h3>
                  <p>
                    {query || favorites
                      ? "Try another search or change your filters."
                      : view === "Trash"
                        ? "Removed certificates can be restored here."
                        : "Add a sample PDF or connect a sample mailbox to bring your first milestones home."}
                  </p>
                  {view !== "Trash" && !query && !favorites && (
                    <Button
                      variant="outline"
                      onClick={() => openModal("connect")}
                    >
                      <Mail size={16} />
                      Explore sample mailbox
                    </Button>
                  )}
                </div>
              )}
            </section>
          )}
          {view === "Overview" && (
            <div className="overview-bottom">
              <section className="panel">
                <div className="section-heading">
                  <h2>A little momentum</h2>
                  <Activity size={18} />
                </div>
                {history.slice(0, 3).map((item) => (
                  <div className="timeline-item" key={item.id}>
                    <span className="timeline-dot" />
                    <div>
                      <p>{item.event}</p>
                      <time>
                        {new Date(item.created).toLocaleString(undefined, {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </time>
                    </div>
                  </div>
                ))}
              </section>
              <section className="next-chapter">
                <div className="circle-icon">
                  <Sparkles size={21} />
                </div>
                <div>
                  <p className="eyebrow">MAKE YOUR NEXT MOVE</p>
                  <h2>Good work deserves a good story.</h2>
                  <p>Turn a milestone into a post that sounds like you.</p>
                  <button
                    className="text-button"
                    onClick={() => navigate("Post studio")}
                  >
                    Open post studio <ArrowRight size={15} />
                  </button>
                </div>
              </section>
            </div>
          )}
          {view === "Connected mailboxes" && (
            <section className="panel">
              <div className="section-heading">
                <h2>Your connections</h2>
                <Button onClick={() => openModal("connect")}>
                  <Plus size={16} />
                  Add sample mailbox
                </Button>
              </div>
              <p className="muted">
                This environment uses synthetic mail. Live OAuth is not enabled.
              </p>
              {connections.length === 0 ? (
                <Empty
                  icon={<Mail />}
                  title="A calmer inbox starts here"
                  copy="Try a sample Gmail or Outlook mailbox. We never access an external account in demo mode."
                />
              ) : (
                connections.map((c) => (
                  <div className="resource-row" key={c.id}>
                    <div className="resource-icon">
                      <Mail size={23} />
                    </div>
                    <div className="resource-copy">
                      <h3>
                        {c.provider === "gmail" ? "Gmail" : "Microsoft Outlook"}{" "}
                        sample mailbox
                      </h3>
                      <p>
                        {c.active
                          ? "Connected · Synthetic fixtures · Consent recorded"
                          : "Disconnected · Existing imports retained"}
                      </p>
                    </div>
                    <div className="row-actions">
                      {c.active ? (
                        <>
                          <Button
                            variant="outline"
                            disabled={busy}
                            onClick={() =>
                              run(
                                () => api(`/connections/${c.id}/sync`, "POST"),
                                "Sample scan complete. Check your vault and approval inbox.",
                              )
                            }
                          >
                            {busy ? (
                              <LoaderCircle className="spin" size={15} />
                            ) : (
                              <Activity size={15} />
                            )}
                            Scan samples
                          </Button>
                          <Button
                            variant="ghost"
                            disabled={busy}
                            onClick={() =>
                              run(
                                () => api(`/connections/${c.id}`, "DELETE"),
                                "Disconnected. Existing certificates were retained.",
                              )
                            }
                          >
                            Disconnect
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant="outline"
                          onClick={() => {
                            setProvider(c.provider);
                            openModal("connect");
                          }}
                        >
                          Reconnect
                        </Button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </section>
          )}
          {view === "Approval inbox" && (
            <section className="panel">
              <div className="policy-banner">
                <ShieldCheck size={22} />
                <div>
                  <strong>Your permission comes first</strong>
                  <p>
                    Files over {settings.threshold_mib} MiB wait here. Approval
                    applies to one file. The 100 MiB hard cap always applies.
                  </p>
                </div>
              </div>
              {approvals.length === 0 ? (
                <Empty
                  icon={<CheckCheck />}
                  title="All clear. You're in control."
                  copy="Oversized imports will appear here before they are stored."
                />
              ) : (
                approvals.map((i) => (
                  <div className="resource-row" key={i.id}>
                    <div className="resource-icon amber">
                      <FileCheck2 />
                    </div>
                    <div className="resource-copy">
                      <h3>{i.title}</h3>
                      <p>
                        {i.issuer} · {formatBytes(i.declared_size)} · Awaiting
                        approval
                      </p>
                    </div>
                    <div className="row-actions">
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() =>
                          run(
                            () => api(`/imports/${i.id}/reject`, "POST"),
                            "Import rejected. No file was stored.",
                          )
                        }
                      >
                        Reject
                      </Button>
                      <Button
                        disabled={busy}
                        onClick={() =>
                          run(
                            () => api(`/imports/${i.id}/approve`, "POST"),
                            "Approved sample imported privately.",
                          )
                        }
                      >
                        Approve download
                      </Button>
                    </div>
                  </div>
                ))
              )}
              <h3 className="history-heading">Import history</h3>
              {imports.map((i) => (
                <div className="simple-row" key={i.id}>
                  <span>{i.title}</span>
                  <span
                    className={`status-tag ${i.status === "stored" ? "success" : ""}`}
                  >
                    {i.status.replaceAll("_", " ")}
                  </span>
                </div>
              ))}
            </section>
          )}
          {view === "Collections" && <CollectionManager certs={certs} />}
          {view === "Activity" && (
            <section className="panel">
              <h2>Your workspace history</h2>
              {history.map((h) => (
                <div className="timeline-item" key={h.id}>
                  <span className="timeline-dot" />
                  <div>
                    <p>{h.event}</p>
                    <time>{new Date(h.created).toLocaleString()}</time>
                  </div>
                </div>
              ))}
            </section>
          )}
          {view === "Settings" && (
            <div className="settings-grid">
              <section className="panel">
                <h2>Personal preferences</h2>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    run(
                      () =>
                        api("/settings", "PUT", {
                          name: settings.name,
                          threshold_mib: settings.threshold_mib,
                        }),
                      "Preferences saved.",
                    );
                  }}
                >
                  <label>
                    Display name
                    <input
                      required
                      maxLength={80}
                      value={settings.name}
                      onChange={(e) =>
                        setSettings({ ...settings, name: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Auto-download limit (MiB)
                    <input
                      required
                      type="number"
                      min={1}
                      max={100}
                      value={settings.threshold_mib}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          threshold_mib: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  <p className="muted">
                    Default 50 MiB. Files above this require per-file approval.
                    Administrative hard cap: 100 MiB.
                  </p>
                  <Button disabled={busy} type="submit">
                    Save preferences
                  </Button>
                </form>
                <div className="simple-row">
                  <span>Dark appearance</span>
                  <Button
                    variant="outline"
                    onClick={() => setDark(!dark)}
                    aria-pressed={dark}
                  >
                    {dark ? "On" : "Off"}
                  </Button>
                </div>
                <Button variant="outline" asChild>
                  <a href="/api/export">
                    <ArrowDownToLine size={15} />
                    Export metadata (JSON)
                  </a>
                </Button>
              </section>
              <section className="panel">
                <h2>Environment & privacy</h2>
                <div className="policy-banner">
                  <ShieldCheck />
                  <div>
                    <strong>Local demonstration only</strong>
                    <p>
                      No live mailbox, Supabase, AI, antivirus or OCR
                      integration has been enabled.
                    </p>
                  </div>
                </div>
                <p className="muted">
                  Sample PDFs stay on this computer. The session expires after
                  24 hours. Use synthetic documents only. Extraction does not
                  verify authenticity.
                </p>
                <p className="muted">
                  Link fetching is disabled. Live credentials, scanner
                  isolation, provider consent and cross-tenant RLS verification
                  are required before production use.
                </p>
                <Button variant="ghost" onClick={() => navigate("Sharing")}>
                  Manage shared access <ArrowRight size={15} />
                </Button>
              </section>
            </div>
          )}
          {view === "Sharing" && (
            <section className="panel">
              <h2>Shared on your terms</h2>
              <p className="muted">
                Create links from a certificate preview. Local links only work
                on this computer. Revoking access is immediate.
              </p>
              {shares.length === 0 ? (
                <Empty
                  icon={<LockKeyhole />}
                  title="Nothing shared. Everything private."
                  copy="When you choose to share a certificate, its expiring link appears here."
                />
              ) : (
                shares.map((s) => (
                  <div className="resource-row" key={s.id}>
                    <div className="resource-copy">
                      <h3>{s.title}</h3>
                      <p>
                        {s.revoked
                          ? "Revoked"
                          : `Expires ${new Date(s.expires * 1000).toLocaleString()}`}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      disabled={busy || !!s.revoked}
                      onClick={() =>
                        run(
                          () => api(`/shares/${s.id}`, "DELETE"),
                          "Share link revoked.",
                        )
                      }
                    >
                      Revoke access
                    </Button>
                  </div>
                ))
              )}
            </section>
          )}
          {view === "Post studio" && (
            <div className="settings-grid">
              <section className="panel">
                <span className="tag">LOCAL TEMPLATE · AI NOT CONFIGURED</span>
                <h2 className="spaced-heading">A milestone worth sharing.</h2>
                <p className="muted">
                  Create an editable caption from your certificate metadata.
                  Nothing is published, and no content is sent to an AI
                  provider.
                </p>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    run(async () => {
                      const d = await api<{ id: string; content: string }>(
                        "/social-drafts",
                        "POST",
                        { certificate_id: draftCert, tone },
                      );
                      setDraftContent(d.content);
                      setDraftId(d.id);
                    }, "Draft ready for your edits.");
                  }}
                >
                  <label>
                    Certificate
                    <select
                      required
                      value={draftCert}
                      onChange={(e) => setDraftCert(e.target.value)}
                    >
                      <option value="">Choose a certificate</option>
                      {certs.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Tone
                    <select
                      value={tone}
                      onChange={(e) => setTone(e.target.value)}
                    >
                      <option value="professional">Professional</option>
                      <option value="friendly">Friendly</option>
                      <option value="short">Short & clear</option>
                    </select>
                  </label>
                  <Button disabled={busy || !draftCert}>
                    <Sparkles size={16} />
                    Create template draft
                  </Button>
                </form>
                <label className="draft-label">
                  Your editable caption
                  <textarea
                    rows={8}
                    maxLength={3000}
                    value={draftContent}
                    onChange={(e) => setDraftContent(e.target.value)}
                    placeholder="Your words will appear here…"
                  />
                </label>
                <div className="row-actions">
                  <Button
                    variant="outline"
                    disabled={!draftId || busy}
                    onClick={() =>
                      run(
                        () =>
                          api(`/social-drafts/${draftId}`, "PATCH", {
                            content: draftContent,
                          }),
                        "Draft saved.",
                      )
                    }
                  >
                    Save edits
                  </Button>
                  <Button
                    disabled={!draftContent}
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(draftContent);
                        setToast(
                          "Caption copied. Paste it wherever you choose.",
                        );
                      } catch {
                        setError(
                          "Clipboard unavailable. Select and copy the caption manually.",
                        );
                      }
                    }}
                  >
                    Copy caption
                  </Button>
                </div>
              </section>
              <section className="panel">
                <h2>Draft history</h2>
                {drafts.length === 0 ? (
                  <Empty
                    icon={<Sparkles />}
                    title="Your voice. Your next chapter."
                    copy="Saved drafts live here. You always choose what to publish."
                  />
                ) : (
                  drafts.map((d) => (
                    <button
                      className="draft-history"
                      key={d.id}
                      onClick={() => {
                        setDraftContent(d.content);
                        setDraftId(d.id);
                        setDraftCert(d.certificate_id);
                        setTone(d.tone);
                      }}
                    >
                      <span className="tag">{d.tone}</span>
                      <p>{d.content}</p>
                      <small>{new Date(d.created).toLocaleDateString()}</small>
                    </button>
                  ))
                )}
              </section>
            </div>
          )}
          {view === "Public profile" && (
            <ProfileEditor
              key={profile?.slug || "new"}
              profile={profile}
              certs={certs}
              name={settings.name}
              busy={busy}
              save={(p) =>
                run(
                  () => api("/profile", "PUT", { ...p, consent: true }),
                  "Profile preferences saved.",
                )
              }
            />
          )}
          <footer className="page-footer">
            <span>
              <ShieldCheck size={14} />
              Built around your privacy.
            </span>
            <span>One achievement at a time.</span>
          </footer>
        </main>
      </div>
      {busy && (
        <div className="busy-indicator" role="status">
          <LoaderCircle size={16} className="spin" />
          Working on it…
        </div>
      )}
      {toast && (
        <div className="toast" role="status">
          <Check size={18} />
          {toast}
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      <Dialog
        open={modal !== null}
        onOpenChange={(open) => {
          if (!open) setModal(null);
        }}
      >
        <DialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            modalOpener.current?.focus();
          }}
        >
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {modal === "connect" && (
            <>
              <div className="modal-icon">
                <Mail size={26} />
              </div>
              <DialogTitle>Let your milestones find you.</DialogTitle>
              <DialogDescription>
                Explore discovery with a synthetic mailbox. No external account
                is accessed or authorized.
              </DialogDescription>
              <div className="provider-options">
                <button
                  className={provider === "gmail" ? "selected" : ""}
                  onClick={() => setProvider("gmail")}
                >
                  <Mail />
                  Gmail sample
                </button>
                <button
                  className={provider === "outlook" ? "selected" : ""}
                  onClick={() => setProvider("outlook")}
                >
                  <Grid2X2 />
                  Outlook sample
                </button>
              </div>
              <div className="policy-banner">
                <ShieldCheck size={20} />
                <p>
                  Three sample credentials and one 51 MiB approval scenario.
                  Repeated scans do not duplicate credentials.
                </p>
              </div>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                I agree to import synthetic sample data into my local workspace.
              </label>
              <Button
                disabled={!consent || busy}
                onClick={() =>
                  run(async () => {
                    await api("/connections", "POST", {
                      provider,
                      consent: true,
                    });
                    setModal(null);
                    setView("Connected mailboxes");
                  }, "Sample mailbox connected. Scan when you’re ready.")
                }
              >
                Connect sample mailbox <ArrowRight size={16} />
              </Button>
            </>
          )}
          {modal === "upload" && (
            <>
              <div className="modal-icon">
                <CloudUpload size={28} />
              </div>
              <DialogTitle>A new addition to your story.</DialogTitle>
              <DialogDescription>
                Upload a sample text-based PDF, up to {settings.threshold_mib}{" "}
                MiB. Local malware scanning is not configured. Do not upload
                real private or untrusted documents.
              </DialogDescription>
              <div className="upload-area">
                <CloudUpload size={35} />
                <h3>Choose a sample certificate</h3>
                <p>PDF only · Up to 100 pages · No encrypted files</p>
                <input
                  ref={fileRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  aria-label="Choose sample PDF"
                  disabled={busy}
                  onChange={(e) => upload(e.target.files?.[0])}
                />
              </div>
              <p className="fine-print">
                <LockKeyhole size={14} />
                Private by default. Metadata will need your review.
              </p>
            </>
          )}
          {modal === "notifications" && (
            <>
              <DialogTitle>Your updates</DialogTitle>
              <DialogDescription>
                Imports, approvals, and the little things worth knowing.
              </DialogDescription>
              <Button
                variant="outline"
                disabled={busy || !unread}
                onClick={() => run(() => api("/notifications/read", "PUT"))}
              >
                <CheckCheck size={16} />
                Mark all as read
              </Button>
              <div className="notification-list">
                {notices.length === 0 ? (
                  <p className="muted">
                    You’re all caught up. Updates will appear here.
                  </p>
                ) : (
                  notices.map((n) => (
                    <div
                      className={`notice ${!n.read ? "unread" : ""}`}
                      key={n.id}
                    >
                      <Bell size={17} />
                      <div>
                        <p>{n.message}</p>
                        <small>{new Date(n.created).toLocaleString()}</small>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <DialogContent>
          {selected && (
            <CertificateDetail
              key={selected.id}
              cert={selected}
              busy={busy}
              sharePath={sharePath}
              onSave={(body) =>
                run(async () => {
                  const c = await api<Certificate>(
                    `/certificates/${selected.id}`,
                    "PATCH",
                    body,
                  );
                  setSelected(c);
                }, "Certificate details saved.")
              }
              onTrash={() =>
                run(
                  async () => {
                    await api(`/certificates/${selected.id}/trash`, "PUT", {
                      value: !selected.trashed,
                    });
                    setSelected(null);
                  },
                  selected.trashed
                    ? "Certificate restored."
                    : "Moved to trash. Any share links were revoked.",
                )
              }
              onShare={() =>
                run(async () => {
                  const s = await api<{ path: string }>("/shares", "POST", {
                    certificate_id: selected.id,
                    expires_hours: 24,
                    consent: true,
                  });
                  setSharePath(`${window.location.origin}${s.path}`);
                }, "24-hour local share link created.")
              }
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  detail,
  accent = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
  accent?: boolean;
}) {
  return (
    <div className={`stat ${accent ? "stat-amber" : ""}`}>
      <div className="stat-top">
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}
function Empty({
  icon,
  title,
  copy,
}: {
  icon: React.ReactNode;
  title: string;
  copy: string;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{copy}</p>
    </div>
  );
}
function subheading(view: View) {
  return (
    (
      {
        "Approval inbox": "A little attention keeps your vault safe.",
        "Connected mailboxes":
          "Bring your achievements together, with your permission.",
        Activity: "A transparent record of everything that happens.",
        "Post studio": "Put your progress into your own words.",
        "Public profile": "Share a selected view of your learning journey.",
        Sharing: "A clear view of who can access your achievements.",
        Settings: "Make this space feel like yours.",
        Trash: "A second chance for your removed certificates.",
      } as Partial<Record<View, string>>
    )[view] || ""
  );
}
