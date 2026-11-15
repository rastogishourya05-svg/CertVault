"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { DialogTitle, DialogDescription } from "@/components/ui/dialog";
import {
  Award,
  LockKeyhole,
  ArrowDownToLine,
  Globe,
  Trash2,
} from "lucide-react";
import type { Certificate } from "@/lib/api";
import { formatBytes } from "@/lib/utils";

export function CertificateDetail({
  cert,
  busy,
  sharePath,
  onSave,
  onTrash,
  onShare,
}: {
  cert: Certificate;
  busy: boolean;
  sharePath: string;
  onSave: (body: unknown) => void;
  onTrash: () => void;
  onShare: () => void;
}) {
  const [title, setTitle] = useState(cert.title),
    [issuer, setIssuer] = useState(cert.issuer),
    [category, setCategory] = useState(cert.category),
    [issued, setIssued] = useState(cert.issued || ""),
    [tags, setTags] = useState((cert.tags || []).join(", ")),
    [shareConsent, setShareConsent] = useState(false);
  return (
    <>
      <div className="detail-heading">
        <div className="modal-icon">
          <Award size={26} />
        </div>
        <span className="tag">
          <LockKeyhole size={12} />
          PRIVATE
        </span>
      </div>
      <DialogTitle>{cert.title}</DialogTitle>
      <DialogDescription>
        {cert.source} · {formatBytes(cert.bytes)} · Authenticity not verified
      </DialogDescription>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave({
            title,
            issuer,
            category,
            issued: issued || null,
            tags: tags
              .split(",")
              .map((t) => t.trim())
              .filter(Boolean),
          });
        }}
      >
        <label>
          Certificate title
          <input
            required
            maxLength={160}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label>
          Issuer
          <input
            required
            maxLength={100}
            value={issuer}
            onChange={(e) => setIssuer(e.target.value)}
          />
        </label>
        <div className="form-row">
          <label>
            Category
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {["Technology", "Design", "Business", "Other"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            Issue date
            <input
              type="date"
              value={issued}
              onChange={(e) => setIssued(e.target.value)}
            />
          </label>
        </div>
        <label>
          Tags (comma-separated)
          <input
            value={tags}
            maxLength={600}
            onChange={(e) => setTags(e.target.value)}
            placeholder="cloud, leadership, design"
          />
        </label>
        <div className="row-actions">
          <Button disabled={busy} type="submit">
            Save details
          </Button>
          {!cert.trashed && (
            <Button variant="outline" asChild>
              <a href={`/api/certificates/${cert.id}/download`}>
                <ArrowDownToLine size={15} />
                Download PDF
              </a>
            </Button>
          )}
        </div>
      </form>
      {!cert.trashed && (
        <div className="share-controls">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={shareConsent}
              onChange={(e) => setShareConsent(e.target.checked)}
            />
            Allow anyone with this link to download this certificate for 24
            hours.
          </label>
          <Button
            variant="outline"
            disabled={!shareConsent || busy}
            onClick={onShare}
          >
            <Globe size={15} />
            Create expiring share link
          </Button>
          {sharePath && (
            <label>
              Local share link
              <input
                aria-label="Local share link"
                readOnly
                value={sharePath}
                onFocus={(e) => e.target.select()}
              />
            </label>
          )}
        </div>
      )}
      <Button variant="ghost" disabled={busy} onClick={onTrash}>
        <Trash2 size={15} />
        {cert.trashed ? "Restore certificate" : "Move to trash"}
      </Button>
    </>
  );
}
