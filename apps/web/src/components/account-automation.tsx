"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mail, RefreshCw, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

type Pipeline = {
  enabled: boolean;
  reason: string;
  connections: {
    id: string;
    account_label: string;
    state: string;
    automatic: boolean;
    scan_days: number;
  }[];
  jobs: {
    id: string;
    status: string;
    attempts: number;
    safe_error_code: string | null;
  }[];
  imports: {
    id: string;
    filename: string;
    declared_bytes: number | null;
    status: string;
    safe_error: string | null;
  }[];
  notifications: { id: string; safe_message: string }[];
};

export function AccountAutomation({
  onImported,
}: {
  onImported: () => Promise<void>;
}) {
  const [state, setState] = useState<Pipeline | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [days, setDays] = useState(30);
  const [automatic, setAutomatic] = useState(false);
  const lastImported = useRef("");
  useEffect(() => {
    const signature =
      state?.imports
        .filter((i) => i.status === "stored")
        .map((i) => i.id)
        .sort()
        .join(",") || "";
    if (signature && signature !== lastImported.current) {
      lastImported.current = signature;
      onImported().catch(() =>
        setError(
          "Import completed, but the vault could not refresh. Use Refresh activity.",
        ),
      );
    }
  }, [state, onImported]);
  const refresh = useCallback(async () => {
    const next = await api<Pipeline>("/account/pipeline/status");
    setState(next);
    return next;
  }, []);

  useEffect(() => {
    let active = true;
    let initial = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<Pipeline>("/account/pipeline/status");
        if (!active) return;
        setState(next);
        if (initial) {
          initial = false;
          const outcome = new URLSearchParams(window.location.search).get(
            "mailbox",
          );
          if (outcome === "connected")
            setMessage(
              "Gmail connected. Queue a scan below, or wait for your opted-in automatic scan.",
            );
          if (outcome === "failed")
            setError(
              "Gmail connection was not completed. Check consent, account session and configuration, then reconnect.",
            );
        }
        if (next.enabled) timer = setTimeout(poll, 5000);
      } catch (e) {
        if (active)
          setError(
            e instanceof Error ? e.message : "Import status unavailable.",
          );
      }
    }
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

  async function act(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await work();
      await refresh();
      await onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Please retry.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="panel automation-panel"
      aria-labelledby="automation-heading"
    >
      <div className="section-heading">
        <h2 id="automation-heading">
          <Mail size={20} /> Automatic certificate imports
        </h2>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            act(async () => {
              setMessage("Import activity refreshed.");
            })
          }
        >
          <RefreshCw size={15} /> Refresh activity
        </Button>
      </div>
      <p className="muted">
        Connect Gmail once. CertVault looks for certificate PDF attachments,
        checks your download limit, scans each file and saves it privately. No
        manual upload is required.
      </p>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {!state ? (
        <p role="status">Checking import availability…</p>
      ) : !state.enabled ? (
        <div className="account-banner">
          <ShieldCheck size={20} />
          <p>
            <strong>Live imports are not enabled.</strong> {state.reason} Your
            mailbox has not been accessed.
          </p>
        </div>
      ) : (
        <>
          <p className="fine-print">
            {state.reason} Automatic scans poll approximately every five minutes
            while the worker and scheduler are running.
          </p>
          {state.connections
            .filter((c) => c.state === "connected")
            .map((c) => (
              <div className="automation-row" key={c.id}>
                <div>
                  <strong>{c.account_label}</strong>
                  <p className="muted">
                    {c.automatic
                      ? "Automatic scans enabled"
                      : "Scan on request"}{" "}
                    · Past {c.scan_days} days
                  </p>
                </div>
                <div className="automation-actions">
                  <Button
                    disabled={busy}
                    onClick={() =>
                      act(async () => {
                        await api(
                          `/account/pipeline/connections/${c.id}/scan`,
                          "POST",
                        );
                        setMessage(
                          "Scan queued. Activity updates automatically; use Refresh activity to reload the vault.",
                        );
                      })
                    }
                  >
                    Scan now
                  </Button>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      act(async () => {
                        const r = await api<{
                          provider_revocation_confirmed: boolean;
                        }>(`/account/pipeline/connections/${c.id}`, "DELETE");
                        setMessage(
                          r.provider_revocation_confirmed
                            ? "Disconnected. Existing certificates are retained."
                            : "Disconnected locally. Remove CertVault access in your Google account to confirm provider revocation.",
                        );
                      })
                    }
                  >
                    Disconnect
                  </Button>
                </div>
              </div>
            ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => {
                const result = await api<{ url: string }>(
                  "/account/pipeline/gmail/authorize",
                  "POST",
                  { consent, scan_days: days, automatic },
                );
                const url = new URL(result.url);
                if (url.origin !== "https://accounts.google.com")
                  throw new Error("Invalid authorization destination.");
                window.location.assign(url.href);
              });
            }}
          >
            <label>
              Scan range
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              >
                <option value={7}>Past 7 days</option>
                <option value={30}>Past 30 days</option>
                <option value={90}>Past 90 days</option>
                <option value={365}>Past year</option>
              </select>
            </label>
            <label className="automation-check">
              <input
                type="checkbox"
                checked={automatic}
                onChange={(e) => setAutomatic(e.target.checked)}
              />{" "}
              Automatically check for new certificates while connected
            </label>
            <label className="automation-check">
              <input
                type="checkbox"
                required
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />{" "}
              I authorize read-only Gmail access for this scan range and private
              certificate processing. CertVault will not send or delete emails.
            </label>
            <Button disabled={busy || !consent}>Connect Gmail securely</Button>
          </form>
          <h3>Import activity</h3>
          {state.jobs.length === 0 ? (
            <p className="muted">No scan has been queued yet.</p>
          ) : (
            state.jobs.slice(0, 5).map((j) => (
              <p key={j.id} role="status">
                Scan {j.status.replaceAll("_", " ")}
                {j.safe_error_code
                  ? ` · ${j.safe_error_code.replaceAll("_", " ")}`
                  : ""}
              </p>
            ))
          )}
          {state.imports.map((item) => (
            <div className="automation-row" key={item.id}>
              <div>
                <strong>{item.filename}</strong>
                <p className="muted">
                  {item.status.replaceAll("_", " ")} ·{" "}
                  {item.declared_bytes === null
                    ? "Unknown size"
                    : `${(item.declared_bytes / 1048576).toFixed(1)} MiB`}
                  {item.safe_error
                    ? ` · ${item.safe_error.replaceAll("_", " ")}`
                    : ""}
                </p>
              </div>
              {item.status === "awaiting_approval" && (
                <div className="automation-actions">
                  {[true, false].map((approve) => (
                    <Button
                      key={String(approve)}
                      variant={approve ? "default" : "outline"}
                      disabled={busy}
                      onClick={() =>
                        act(async () => {
                          await api(
                            `/account/pipeline/imports/${item.id}/decision`,
                            "POST",
                            { approve },
                          );
                          setMessage(
                            approve
                              ? "This file is approved up to the 100 MiB hard cap and queued for processing."
                              : "Download rejected. No certificate was stored.",
                          );
                        })
                      }
                    >
                      {approve ? "Approve download" : "Reject"}
                    </Button>
                  ))}
                </div>
              )}
            </div>
          ))}
          {state.notifications.length > 0 && (
            <>
              <h3>Notifications</h3>
              <ul>
                {state.notifications.map((n) => (
                  <li key={n.id}>{n.safe_message}</li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}
