"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mail, RefreshCw, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type Pipeline = {
  enabled: boolean;
  reason: string;
  connections: {
    id: string;
    account_label: string;
    state: string;
    scan_days: number;
  }[];
  jobs: {
    id: string;
    status: string;
    stored_files?: { certificate_id: string; filename: string }[];
    summary?: Record<string, number> | null;
    updated_at?: string;
    attempts: number;
    safe_error_code: string | null;
  }[];
  approvals?: Pipeline["imports"];
  imports: {
    certificate_id?: string;
    id: string;
    filename: string;
    declared_bytes: number | null;
    status: string;
    safe_error: string | null;
  }[];
  notifications: { id: string; safe_message: string }[];
};

function importErrorMessage(code: string) {
  if (code === "storage_size_limit_exceeded")
    return "Exceeds the 50 MB (50,000,000-byte) Storage limit. Not saved to your vault; approval cannot bypass this limit.";
  return code.replaceAll("_", " ");
}

export function AccountAutomation({
  onImported,
  section,
  onCounts,
}: {
  section: string;
  onCounts: (counts: { mailboxes: number; approvals: number } | null) => void;
  onImported: () => Promise<void>;
}) {
  const [state, setState] = useState<Pipeline | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [days, setDays] = useState(30);
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
  useEffect(() => {
    onCounts(
      state?.enabled
        ? {
            mailboxes: state.connections.filter((c) => c.state === "connected")
              .length,
            approvals: (
              state.approvals ??
              state.imports.filter((i) => i.status === "awaiting_approval")
            ).length,
          }
        : null,
    );
  }, [state, onCounts]);
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
              "Gmail connected. Start a manual scan whenever you are ready.",
            );
          if (outcome === "failed")
            setError(
              "Gmail connection was not completed. Check consent, account session and configuration, then reconnect.",
            );
        }
        if (next.enabled) timer = setTimeout(poll, 5000);
      } catch (e) {
        if (active) {
          timer = setTimeout(poll, 10000);
          setError(
            e instanceof Error ? e.message : "Import status unavailable.",
          );
        }
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
  if (!["mailboxes", "approvals", "activity"].includes(section)) return null;
  const mailbox = section === "mailboxes",
    approvals = section === "approvals";
  const pending =
    state?.approvals ??
    state?.imports.filter((item) => item.status === "awaiting_approval") ??
    [];
  return (
    <section
      className="panel automation-panel"
      aria-labelledby="automation-heading"
    >
      <div className="section-heading">
        <h2 id="automation-heading">
          <Mail size={20} />{" "}
          {mailbox
            ? "Gmail certificate imports"
            : approvals
              ? "Download decisions"
              : "Import activity"}
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
      {mailbox && (
        <>
          <p className="muted">
            Connect your test Gmail account, then start each scan yourself.
            CertVault looks for certificate files, checks your download limit,
            scans each file and saves it privately.
          </p>
          <p className="fine-print">
            Import PDF, PNG and JPEG attachments. English OCR reads scanned
            documents. Supported direct Udemy certificate files require download
            approval. Other issuer pages need manual review.
          </p>
          <a href="#private-vault">Go to your certificate vault ↓</a>
        </>
      )}
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
          {mailbox && (
            <>
              <p className="fine-print">
                {state.reason} Mail is scanned only after you select Scan now.
              </p>
              {state.connections
                .filter((c) => c.state === "connected")
                .map((c) => (
                  <div className="automation-row" key={c.id}>
                    <div>
                      <strong>{c.account_label}</strong>
                      <p className="muted">
                        Scan on request · Past {c.scan_days} days
                      </p>
                    </div>
                    <label>
                      Scan history
                      <select
                        value={c.scan_days}
                        disabled={busy}
                        onChange={(event) =>
                          act(async () => {
                            await api(
                              `/account/pipeline/connections/${c.id}/range`,
                              "PUT",
                              { scan_days: Number(event.target.value) },
                            );
                            setMessage("Scan range saved. Select Scan now to scan the chosen period.");
                          })
                        }
                      >
                        <option value={7}>Past 7 days</option>
                        <option value={30}>Past 30 days</option>
                        <option value={90}>Past 90 days</option>
                        <option value={365}>Past year</option>
                        <option value={730}>Past 2 years</option>
                        <option value={1825}>Past 5 years</option>
                        <option value={3650}>Past 10 years</option>
                      </select>
                    </label>
                    <div className="automation-actions">
                      <Button
                        disabled={
                          busy ||
                          state.jobs.some((job) =>
                            ["queued", "running"].includes(job.status),
                          )
                        }
                        onClick={() =>
                          act(async () => {
                            await api(
                              `/account/pipeline/connections/${c.id}/scan`,
                              "POST",
                            );
                            setMessage(
                              "Scan queued. Open Activity for progress and results.",
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
                            }>(
                              `/account/pipeline/connections/${c.id}`,
                              "DELETE",
                            );
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
              <details
                open={state.connections.every((c) => c.state !== "connected")}
              >
                <summary>Connect a Gmail mailbox</summary>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    act(async () => {
                      const result = await api<{ url: string }>(
                        "/account/pipeline/gmail/authorize",
                        "POST",
                        { consent, scan_days: days, automatic: false },
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
                      <option value={730}>Past 2 years</option>
                      <option value={1825}>Past 5 years</option>
                      <option value={3650}>Past 10 years</option>
                    </select>
                  </label>
                  <label className="automation-check">
                    <input
                      type="checkbox"
                      required
                      checked={consent}
                      onChange={(e) => setConsent(e.target.checked)}
                    />{" "}
                    I authorize read-only Gmail access for this scan range and
                    private certificate processing. CertVault will not send or
                    delete emails.
                  </label>
                  <Button disabled={busy || !consent}>
                    Connect Gmail securely
                  </Button>
                </form>
              </details>
              <a href="#activity">View scan results →</a>
            </>
          )}
          {section === "activity" && (
            <>
              {state.jobs[0]?.status === "completed" &&
                state.jobs[0].summary &&
                Object.keys(state.jobs[0].summary).length === 0 && (
                  <p role="status">
                    Scan finished with no matching certificates. Check the
                    connected Gmail address and date range, attach a certificate
                    file (PDF or image), and include certificate, credential or
                    achievement in its subject or filename. Then scan again.
                  </p>
                )}
              {state.jobs.length === 0 ? (
                <p className="muted">No scan has been queued yet.</p>
              ) : (
                state.jobs.map((j) => (
                  <p key={j.id} role="status">
                    Scan {j.status.replaceAll("_", " ")}
                    {j.updated_at && (
                      <small>
                        {" "}
                        · {new Date(j.updated_at).toLocaleString()}
                      </small>
                    )}
                    {j.summary && (
                      <span>
                        {" "}
                        ·{" "}
                        {Object.entries(j.summary)
                          .map(([key, n]) => n + " " + key.replaceAll("_", " "))
                          .join(", ") || "0 matching certificates"}
                      </span>
                    )}
                    {j.status === "completed" && !j.summary && (
                      <small> · Outcome counts unavailable for this run</small>
                    )}
                    {j.stored_files?.map((file) => (
                      <a
                        className="text-button"
                        key={file.certificate_id}
                        href={`/api/account/pipeline/certificates/${file.certificate_id}/download?inline=true`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open {file.filename}
                      </a>
                    ))}
                    {j.safe_error_code
                      ? ` · ${j.safe_error_code.replaceAll("_", " ")}`
                      : ""}
                  </p>
                ))
              )}
            </>
          )}
          {approvals && pending.length === 0 && (
            <p>No downloads awaiting approval.</p>
          )}
          {(approvals ? pending : mailbox ? [] : state.imports).map((item) => (
            <div className="automation-row" key={item.id}>
              <div>
                <strong>{item.filename}</strong>
                {item.certificate_id && (
                  <a
                    className="text-button"
                    href={`/api/account/pipeline/certificates/${item.certificate_id}/download?inline=true`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View private file
                  </a>
                )}
                <p className="muted">
                  {item.status.replaceAll("_", " ")} ·{" "}
                  {item.declared_bytes === null
                    ? "Unknown size"
                    : formatBytes(item.declared_bytes)}
                  {item.safe_error
                    ? ` · ${importErrorMessage(item.safe_error)}`
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
                              ? "This file is approved for one download, up to the 50 MB (50,000,000-byte) Storage limit."
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
          {section === "activity" && state.notifications.length > 0 && (
            <>
              <h3>Notifications</h3>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() =>
                  act(async () => {
                    await api("/account/notifications/read", "POST");
                    setMessage(
                      "Notifications cleared. Certificates and import history are retained.",
                    );
                  })
                }
              >
                Clear notifications
              </Button>
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
