"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Award,
  LockKeyhole,
  Search,
  ShieldCheck,
  Star,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

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
    [authenticated, setAuthenticated] = useState(false),
    [busy, setBusy] = useState(false),
    [loadingVault, setLoadingVault] = useState(true),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [query, setQuery] = useState(""),
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
    api<{ configured: boolean }>("/account/config")
      .then(async (c) => {
        setConfigured(c.configured);
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
  return (
    <main className="account-page">
      <Link className="brand" href="/">
        <ShieldCheck />
        CertVault<span className="beta">DEVELOPMENT</span>
      </Link>
      <div className="account-banner">
        <ShieldCheck size={20} />
        <p>
          Development account area · Supabase Auth & private PostgreSQL.
          Uploads, mailbox imports and AI stay disabled until their security
          gates pass.
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
                  await api("/account/login", "POST", { email, password });
                  setPassword("");
                  setAuthenticated(true);
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
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              <Button disabled={busy}>
                {busy ? "Signing in…" : "Sign in securely"}
              </Button>
            </form>
            <p className="fine-print">
              <LockKeyhole size={14} />
              Your access and refresh tokens stay server-side.
            </p>
          </section>
          <section className="panel">
            <h2>A focused development slice</h2>
            <p className="muted">
              Sign-in, sign-out, private certificate search, favorites and
              profile preferences use Supabase authorization. Registration,
              password recovery, uploads and mail sync are still being
              integrated; they are not represented as ready.
            </p>
            <p className="muted">
              Never paste passwords or API secrets into chat. Enter account
              credentials only in this form.
            </p>
          </section>
        </div>
      ) : (
        <>
          <div className="section-heading">
            <h2>
              Your private certificates{" "}
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
          {loadingVault ? (
            <div className="empty-state" role="status">
              Loading your private certificates…
            </div>
          ) : certs.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">
                <Award size={30} />
              </div>
              <h3>Your private vault is ready for its next chapter.</h3>
              <p>
                {query
                  ? "No certificates match this search."
                  : "There are no certificates in this development account. Ingestion is still disabled; no demo certificates are copied here."}
              </p>
            </div>
          ) : (
            <div className="certificate-grid">
              {certs.map((c) => (
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
              <Button disabled={busy}>Save development preferences</Button>
            </form>
          </section>
        </>
      )}
    </main>
  );
}
