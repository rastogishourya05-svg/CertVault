"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Award,
  Eye,
  LockKeyhole,
  Search,
  ShieldCheck,
  Star,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { AccountAutomation } from "@/components/account-automation";
import { CertificateVerification } from "@/components/certificate-verification";

type LiveCertificate = {
  id: string;
  title: string;
  issuer: string | null;
  category: string;
  favorite: boolean;
  source: string;
  issued_on: string | null;
};
type Profile = { display_name: string; download_limit_bytes: number };

export default function DevelopmentAccount() {
  const [checking, setChecking] = useState(true),
    [configured, setConfigured] = useState(false),
    [uploadsEnabled, setUploadsEnabled] = useState(false),
    [authenticated, setAuthenticated] = useState(false),
    [creatingAccount, setCreatingAccount] = useState(false),
    [busy, setBusy] = useState(false),
    [loadingVault, setLoadingVault] = useState(true),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [query, setQuery] = useState(""),
    [sourceFilter, setSourceFilter] = useState("all"),
    [certs, setCerts] = useState<LiveCertificate[]>([]),
    [profile, setProfile] = useState<Profile>({
      display_name: "Your workspace",
      download_limit_bytes: 52428800,
    });
  const refresh = useCallback(
    async (accept: () => boolean = () => true) => {
      const c = await api<LiveCertificate[]>(
        `/account/certificates?q=${encodeURIComponent(query)}`,
      );
      if (accept()) setCerts(c);
    },
    [query],
  );
  useEffect(() => {
    api<{ configured: boolean; uploads_enabled: boolean }>("/account/config")
      .then(async (c) => {
        setConfigured(c.configured);
        setUploadsEnabled(c.uploads_enabled);
        if (c.configured) {
          const s = await api<{ authenticated: boolean }>("/account/status");
          setAuthenticated(s.authenticated);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setChecking(false));
  }, []);
  useEffect(() => {
    if (!authenticated) return;
    let active = true;
    const timer = setTimeout(() => {
      setLoadingVault(true);
      refresh(() => active)
        .catch((e) => {
          if (active) setError(e.message);
        })
        .finally(() => {
          if (active) setLoadingVault(false);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [authenticated, refresh]);
  useEffect(() => {
    if (!authenticated) return;
    let active = true;
    api<Profile>("/account/profile")
      .then((p) => {
        if (active) setProfile(p);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [authenticated]);
  async function action(callback: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await callback();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Please retry.");
    } finally {
      setBusy(false);
    }
  }
  const visibleCertificates = certs.filter(
    (certificate) =>
      sourceFilter === "all" || certificate.source === sourceFilter,
  );
  return (
    <main className="account-page">
      <Link className="brand" href="/">
        <ShieldCheck />
        CertVault<span className="beta">DEVELOPMENT</span>
      </Link>
      <div className="account-banner">
        <ShieldCheck size={20} />
        <p>
          Local hackathon workspace · Supabase Auth, PostgreSQL and private
          certificate storage. Gmail scanning is always manual.
        </p>
      </div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR IDENTITY. YOUR PRIVATE WORKSPACE.</p>
          <h1>
            {authenticated
              ? profile.display_name
              : "A secure home for your learning."}
          </h1>
          <p>
            {authenticated
              ? "This view uses real owner-scoped Supabase data. Your local demo is separate."
              : "Sign in with an existing account in the authorized development project."}
          </p>
        </div>
        <Link className="text-button" href="/">
          <ArrowLeft size={15} />
          Local demo
        </Link>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      {message && (
        <p className="account-message" role="status">
          {message}
        </p>
      )}
      {checking ? (
        <p role="status">Checking account configuration…</p>
      ) : !configured ? (
        <section className="panel">
          <h2>Development sign-in is not configured</h2>
          <p className="muted">
            The local demo remains available. Secure server configuration is
            required before connecting a development account.
          </p>
        </section>
      ) : !authenticated ? (
        <div className="settings-grid">
          <section className="panel">
            <h2>Sign in to your development account</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                action(async () => {
                  const result = await api<{
                    authenticated: boolean;
                    confirmation_required?: boolean;
                  }>(
                    creatingAccount ? "/account/register" : "/account/login",
                    "POST",
                    { email, password },
                  );
                  setPassword("");
                  if (result.authenticated) setAuthenticated(true);
                  else
                    setMessage(
                      "Account created. Check local Auth mail in Supabase Inbucket, then sign in.",
                    );
                });
              }}
            >
              <label>
                Email address
                <input
                  required
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
              <label>
                Password
                <input
                  required
                  type="password"
                  autoComplete={creatingAccount ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              <Button disabled={busy}>
                {busy
                  ? creatingAccount
                    ? "Creating account…"
                    : "Signing in…"
                  : creatingAccount
                    ? "Create local account"
                    : "Sign in securely"}
              </Button>
            </form>
            <button
              className="text-button"
              type="button"
              disabled={busy}
              onClick={() => setCreatingAccount((value) => !value)}
            >
              {creatingAccount
                ? "Already have an account? Sign in"
                : "New to the local demo? Create an account"}
            </button>
            <p className="fine-print">
              <LockKeyhole size={14} />
              Your access and refresh tokens stay server-side.
            </p>
          </section>
          <section className="panel">
            <h2>A focused development slice</h2>
            <p className="muted">
              Create a local account, sign in, search and favorite certificates,
              and save profile preferences. Private PDF upload is available once
              local scanning and Storage configuration are present. Gmail scans
              require a separate manual consent step.
            </p>
            <p className="muted">
              Never paste passwords or API secrets into chat. Enter account
              credentials only in this form.
            </p>
          </section>
        </div>
      ) : (
        <>
          <AccountAutomation onImported={refresh} />
          <div className="section-heading">
            <h2>
              <span id="private-vault">Your private certificates</span>{" "}
              <span className="number-pill">{certs.length}</span>
            </h2>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() =>
                action(async () => {
                  const r = await api<{
                    provider_revocation_confirmed: boolean;
                  }>("/account/logout", "POST");
                  setAuthenticated(false);
                  setCerts([]);
                  setMessage(
                    r.provider_revocation_confirmed
                      ? "Signed out securely."
                      : "Signed out here. Provider session revocation could not be confirmed.",
                  );
                })
              }
            >
              Sign out
            </Button>
          </div>
          <label className="search-field account-search">
            <Search size={18} />
            <input
              aria-label="Search development certificates"
              disabled={busy}
              maxLength={200}
              placeholder="Search titles, issuers and extracted text…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <label className="account-source-filter">
            Filter by source
            <select
              aria-label="Filter certificates by source"
              value={sourceFilter}
              onChange={(event) => setSourceFilter(event.target.value)}
            >
              <option value="all">All certificates</option>
              <option value="gmail">Gmail imports</option>
              <option value="manual">Manual uploads</option>
            </select>
          </label>
          {loadingVault ? (
            <div className="empty-state" role="status">
              Loading your private certificates…
            </div>
          ) : visibleCertificates.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">
                <Award size={30} />
              </div>
              <h3>Your private vault is ready for its next chapter.</h3>
              <p>
                {query
                  ? "No certificates match this search."
                  : "No certificates yet. Import availability and setup are shown above; demo certificates are kept separate."}
              </p>
            </div>
          ) : (
            <div className="certificate-grid">
              {visibleCertificates.map((c) => (
                <article key={c.id} className="certificate-card">
                  <div className="certificate-art blue">
                    <Award size={36} />
                    <strong>{c.title}</strong>
                  </div>
                  <div className="card-info">
                    <div className="card-heading">
                      <h3>{c.title}</h3>
                      <button
                        className={`star-button ${c.favorite ? "is-favorite" : ""}`}
                        aria-label={`${c.favorite ? "Unfavorite" : "Favorite"} ${c.title}`}
                        aria-pressed={c.favorite}
                        disabled={busy}
                        onClick={() =>
                          action(async () => {
                            await api(
                              `/account/certificates/${c.id}/favorite`,
                              "PUT",
                              {
                                value: !c.favorite,
                              },
                            );
                            await refresh();
                          })
                        }
                      >
                        <Star
                          size={18}
                          fill={c.favorite ? "currentColor" : "none"}
                        />
                      </button>
                    </div>
                    <p>{c.issuer || "Issuer needs review"}</p>
                    <CertificateVerification id={c.id} />
                    <a
                      className="text-button"
                      target="_blank"
                      rel="noreferrer"
                      href={`/api/account/pipeline/certificates/${c.id}/download?inline=true`}
                    >
                      <Eye size={14} /> View PDF
                    </a>
                    <a
                      className="text-button"
                      href={`/api/account/pipeline/certificates/${c.id}/download`}
                    >
                      Download private PDF
                    </a>
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
          )}
          {uploadsEnabled && (
            <section className="panel account-upload">
              <h2>Add a certificate PDF</h2>
              <p className="muted">
                Files are size-checked, scanned, processed in an isolated parser,
                and stored privately before appearing in your vault.
              </p>
              <label>
                PDF certificate
                <input
                  aria-label="Certificate PDF to upload"
                  type="file"
                  accept="application/pdf,.pdf"
                  disabled={busy}
                  onChange={(event) => {
                    const input = event.currentTarget;
                    const selected = input.files?.[0];
                    if (!selected) return;
                    const form = new FormData();
                    form.append("file", selected);
                    action(async () => {
                      const result = await api<{
                        status: string;
                        certificate_id: string;
                      }>("/account/certificates/upload", "POST", form);
                      setMessage(
                        result.status === "duplicate"
                          ? "This certificate is already in your vault; the duplicate was skipped."
                          : "Certificate uploaded and saved privately.",
                      );
                      await refresh();
                      input.value = "";
                    });
                  }}
                />
              </label>
            </section>
          )}
          <section className="panel account-preferences">
            <h2>Profile preferences</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                action(async () => {
                  await api("/account/profile", "PUT", profile);
                  setMessage(
                    "Profile saved to your private development account.",
                  );
                });
              }}
            >
              <label>
                Display name
                <input
                  required
                  maxLength={80}
                  value={profile.display_name}
                  onChange={(e) =>
                    setProfile({ ...profile, display_name: e.target.value })
                  }
                />
              </label>
              <label>
                Auto-download limit (MiB)
                <input
                  type="number"
                  min={1}
                  max={100}
                  required
                  value={profile.download_limit_bytes / 1048576}
                  onChange={(e) =>
                    setProfile({
                      ...profile,
                      download_limit_bytes: Number(e.target.value) * 1048576,
                    })
                  }
                />
              </label>
              <p className="muted">
                This preference stays configurable. The current Supabase Free
                Storage limit is 50 MB (50,000,000 bytes); larger files are
                blocked even if you approve them.
              </p>
              <Button disabled={busy}>Save development preferences</Button>
            </form>
          </section>
        </>
      )}
    </main>
  );
}
