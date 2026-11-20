"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

type Evidence = {
  credential_id: string | null;
  recipient: string | null;
  title?: string;
  issuer?: string | null;
  status: string;
  explanation: string;
  issuer_links: { issuer: string; url: string }[];
};

export function CertificateVerification({ id }: { id: string }) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div>
      <Button
        variant="outline"
        disabled={busy}
        onClick={async () => {
          if (evidence) {
            setEvidence(null);
            return;
          }
          setBusy(true);
          setError("");
          try {
            setEvidence(
              await api<Evidence>(`/account/certificates/${id}/verification`),
            );
          } catch (e) {
            setError(
              e instanceof Error
                ? e.message
                : "Verification details unavailable",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy
          ? "Loading details…"
          : evidence
            ? "Close verification details"
            : "Credential & issuer verification"}
      </Button>
      {error && <p role="alert">{error}</p>}
      {evidence && (
        <div aria-live="polite">
          <p>
            <strong>Authenticity: not verified</strong>
          </p>
          <p>Vault title: {evidence.title || "See original document"}</p>
          <p>Recorded issuer: {evidence.issuer || "See original document"}</p>
          <p>Recipient: {evidence.recipient || "See original document"}</p>
          <p>Credential ID: {evidence.credential_id || "Not found"}</p>
          <p>{evidence.explanation}</p>
          {evidence.issuer_links.map((link) => (
            <p key={link.url}>
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                referrerPolicy="no-referrer"
              >
                Review on {link.issuer} ↗
              </a>
            </p>
          ))}
          {!evidence.issuer_links.length && (
            <p>
              No supported issuer verification link found. Use the issuer’s
              official portal; this does not mean the certificate is invalid.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
