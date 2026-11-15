"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Globe, ArrowRight } from "lucide-react";
import type { Certificate, Profile } from "@/lib/api";

export function ProfileEditor({
  profile,
  certs,
  name,
  busy,
  save,
}: {
  profile: Profile | null;
  certs: Certificate[];
  name: string;
  busy: boolean;
  save: (p: Profile) => void;
}) {
  const [value, setValue] = useState<Profile>(
      profile || { enabled: false, slug: "", name, featured: [] },
    ),
    [consent, setConsent] = useState(false);
  return (
    <section className="panel profile-panel">
      <div className="policy-banner">
        <Globe />
        <div>
          <strong>Private until you decide otherwise</strong>
          <p>
            Only the titles, issuers and categories of selected certificates
            appear. Certificate files remain private.
          </p>
        </div>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save(value);
        }}
      >
        <label>
          Profile name
          <input
            required
            maxLength={80}
            value={value.name}
            onChange={(e) => setValue({ ...value, name: e.target.value })}
          />
        </label>
        <label>
          Profile address
          <input
            required
            minLength={3}
            maxLength={40}
            pattern="[a-z0-9-]+"
            placeholder="your-name"
            value={value.slug}
            onChange={(e) => setValue({ ...value, slug: e.target.value })}
          />
        </label>
        <fieldset>
          <legend>Choose featured achievements</legend>
          {certs.length === 0 && (
            <p className="muted">
              Add certificates to choose your featured achievements.
            </p>
          )}
          {certs.map((c) => (
            <label className="checkbox-label" key={c.id}>
              <input
                type="checkbox"
                checked={value.featured.includes(c.id)}
                onChange={(e) =>
                  setValue({
                    ...value,
                    featured: e.target.checked
                      ? [...value.featured, c.id]
                      : value.featured.filter((id) => id !== c.id),
                  })
                }
              />
              {c.title}
            </label>
          ))}
        </fieldset>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={!!value.enabled}
            onChange={(e) => setValue({ ...value, enabled: e.target.checked })}
          />
          Enable my public profile
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          I confirm the visibility and featured certificate choices above.
        </label>
        <div className="row-actions">
          <Button disabled={!consent || busy}>Save profile choices</Button>
          {profile?.enabled && (
            <Button asChild variant="outline">
              <a
                href={`/p/${encodeURIComponent(profile.slug)}`}
                target="_blank"
                rel="noreferrer"
              >
                View local profile <ArrowRight size={14} />
              </a>
            </Button>
          )}
        </div>
      </form>
    </section>
  );
}
