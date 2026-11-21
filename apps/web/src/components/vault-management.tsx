"use client";
import { Dictation } from "./dictation";
import { useEffect, useRef, useState } from "react";
import { Button } from "./ui/button";
import { api } from "@/lib/api";

export type ReviewData = {
  id: string;
  title: string;
  issuer: string | null;
  recipient?: string | null;
  issued_on: string | null;
  category: string;
  reviewed_at?: string | null;
};

export function MetadataReview({
  certificate: c,
  saved,
}: {
  certificate: ReviewData;
  saved: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  if (!editing)
    return (
      <Button variant="outline" onClick={() => setEditing(true)}>
        {c.reviewed_at ? "Edit reviewed details" : "Review extracted details"}
      </Button>
    );
  return (
    <form
      ref={formRef}
      onSubmit={async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setBusy(true);
        setError("");
        try {
          await api(`/account/certificates/${c.id}/review`, "PUT", {
            title: form.get("title"),
            issuer: form.get("issuer") || null,
            recipient: form.get("recipient") || null,
            issued_on: form.get("issued_on") || null,
            category: form.get("category"),
          });
          await saved();
          setEditing(false);
        } catch (e) {
          setError(e instanceof Error ? e.message : "Save failed");
        } finally {
          setBusy(false);
        }
      }}
    >
      <h3>Review extracted details</h3>
      <p className="muted">Tap a field’s microphone to dictate. Stopping sends the recording to ElevenLabs automatically, up to 15 seconds. Cancel to discard while recording.</p>
      {([
        ["title", "Title", 160], ["issuer", "Issuer", 120],
        ["recipient", "Recipient", 120], ["issued_on", "Issue date", 80],
        ["category", "Category", 80],
      ] as const).map(([name, label, limit]) => (
        <div className="voice-field" key={name}>
          <label>{label}
            <input name={name} type={name === "issued_on" ? "date" : "text"}
              defaultValue={c[name] ?? ""} maxLength={limit} required={name === "title" || name === "category"} />
          </label>
          <Dictation label={label.toLowerCase()} limit={limit} compact apply={value => {
            const input = formRef.current?.elements.namedItem(name);
            if (!(input instanceof HTMLInputElement)) return;
            if (name === "issued_on") {
              const date = document.createElement("input");
              date.type = "date";
              date.value = value.replace(/[.]$/, "");
              if (!date.value) throw Error("Use YYYY-MM-DD or choose the date in the calendar.");
              value = date.value;
            }
            input.value = value;
            input.focus();
          }} />
        </div>
      ))}
      <details>
        <summary>Correct several fields by voice</summary>
        <p>Say Issuer is AWS, recipient is Alex, and issue date is 2025-05-14. Review the proposed values above before saving.</p>
        <Dictation label="field corrections" limit={600} apply={value => {
          const matches = Array.from(value.matchAll(/(?:^|[,;.]\s*|\s+and\s+)(?:and\s+)?(?:the\s+)?(issuer|recipient|title|category|issue date)\s+(?:is\s+)?/gi));
          const edits = [];
          for (const [i, match] of matches.entries()) {
            const name = match[1].toLowerCase();
            const input = formRef.current?.elements.namedItem(name === "issue date" ? "issued_on" : name);
            const text = value.slice(match.index! + match[0].length, matches[i+1]?.index).trim().replace(/[.,;]+$/, "");
            if (!(input instanceof HTMLInputElement) || !text || (input.maxLength > 0 && text.length > input.maxLength)) continue;
            if (name === "issue date") {
              const date = document.createElement("input"); date.type = "date"; date.value = text;
              if (!date.value) continue;
            }
            input.value = text; edits.push(name);
          }
          setError(edits.length ? "Proposed changes: " + edits.join(", ") + ". Check the fields and save." : "No fields recognized. Use the example or edit the fields directly.");
        }}/>
      </details>
      <p className="muted">
        Check the suggested category and extracted fields against the original
        document.
      </p>
      {error && <p role="alert">{error}</p>}
      <Button disabled={busy}>Save reviewed details</Button>
      <Button
        type="button"
        variant="outline"
        disabled={busy}
        onClick={() => setEditing(false)}
      >
        Cancel
      </Button>
    </form>
  );
}

export function PasswordRecovery() {
  const [requested, setRequested] = useState(false),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <details>
      <summary>Forgot your password?</summary>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const data = new FormData(form);
          setBusy(true);
          setMessage("");
          try {
            if (!requested) {
              await api("/account/recovery/request", "POST", {
                email: data.get("email"),
              });
              setRequested(true);
              setMessage(
                "If the account exists, a recovery email is available in the local test inbox.",
              );
            } else {
              const link = new URL(String(data.get("proof")));
              const token =
                link.searchParams.get("token") ??
                link.searchParams.get("token_hash");
              if (!token || link.searchParams.get("type") !== "recovery")
                throw Error(
                  "Copy the recovery link from the latest recovery email.",
                );
              await api("/account/recovery/finish", "POST", {
                token_hash: token,
                password: data.get("password"),
              });
              form.reset();
              setRequested(false);
              setMessage("Password changed. Sign in with your new password.");
            }
          } catch (e) {
            setMessage(e instanceof Error ? e.message : "Recovery failed.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {!requested ? (
          <label>
            Recovery email
            <input required name="email" type="email" />
          </label>
        ) : (
          <>
            <p>
              Open the{" "}
              <a href="http://127.0.0.1:54324" target="_blank" rel="noreferrer">
                local test inbox
              </a>
              . Copy the password reset link without opening it.
            </p>
            <label>
              Recovery link
              <input type="password" name="proof" required autoComplete="off" />
            </label>
            <label>
              New password (12 characters minimum)
              <input
                required
                minLength={12}
                maxLength={128}
                name="password"
                type="password"
                autoComplete="new-password"
              />
            </label>
          </>
        )}
        <Button disabled={busy}>
          {requested ? "Set new password" : "Request recovery email"}
        </Button>
      </form>
      {message && <p role="status">{message}</p>}
    </details>
  );
}

export async function exportFiles(ids: string[]) {
  const response = await fetch("/api/account/pipeline/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Error(body.detail || "Export failed");
  }
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = "certvault.zip";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export function Trash({ restored }: { restored: () => Promise<void> }) {
  const [files, setFiles] = useState<{ id: string; title: string }[]>([]),
    [ids, setIds] = useState<string[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(true);
  useEffect(() => {
    let active = true;
    async function load() {
      const rows: { id: string; title: string }[] = [];
      while (active) {
        const page = await api<typeof rows>(
          `/account/certificates?trash=true&offset=${rows.length}`,
        );
        rows.push(...page);
        if (page.length < 100) break;
      }
      if (active) setFiles(rows);
    }
    load()
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, []);
  return (
    <section className="panel">
      <h2>Restore certificates</h2>
      {error && <p role="alert">{error}</p>}
      {busy ? (
        <p role="status">Loading…</p>
      ) : !files.length && !error ? (
        <p>Trash is empty.</p>
      ) : (
        files.map((c) => (
          <label key={c.id} className="automation-check">
            <input
              type="checkbox"
              checked={ids.includes(c.id)}
              disabled={busy || (!ids.includes(c.id) && ids.length >= 100)}
              onChange={(e) =>
                setIds(
                  e.target.checked
                    ? [...ids, c.id]
                    : ids.filter((id) => id !== c.id),
                )
              }
            />
            {c.title}
          </label>
        ))
      )}
      <Button
        disabled={busy || !ids.length}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await api("/account/vault/bulk", "POST", {
              ids,
              operation: "restore",
            });
            setFiles(files.filter((c) => !ids.includes(c.id)));
            setIds([]);
            await restored();
          } catch (e) {
            setError(e instanceof Error ? e.message : "Restore failed");
          } finally {
            setBusy(false);
          }
        }}
      >
        Restore selected
      </Button>
    </section>
  );
}
