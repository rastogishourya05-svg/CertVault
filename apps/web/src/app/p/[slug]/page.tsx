"use client";
import { use, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ShieldCheck, Award } from "lucide-react";
import Link from "next/link";
export default function PublicProfile({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const [profile, setProfile] = useState<{
    name: string;
    certificates: { title: string; issuer: string; category: string }[];
  } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{
      name: string;
      certificates: { title: string; issuer: string; category: string }[];
    }>(`/public/${encodeURIComponent(slug)}`)
      .then(setProfile)
      .catch((e) => setError(e.message));
  }, [slug]);
  return (
    <main className="public-page">
      <Link className="brand" href="/">
        <ShieldCheck />
        CertVault<span className="beta">LOCAL DEMO</span>
      </Link>
      {error ? (
        <p role="alert">{error}</p>
      ) : profile ? (
        <>
          <p className="eyebrow">A JOURNEY OF CONTINUOUS LEARNING</p>
          <h1>{profile.name}</h1>
          <p>
            Selected achievements · Shared by their owner · Authenticity not
            verified
          </p>
          <div className="certificate-grid">
            {profile.certificates.map((c, i) => (
              <article className="certificate-card" key={i}>
                <div className="certificate-art blue">
                  <Award size={50} />
                  <h2>{c.title}</h2>
                </div>
                <div className="card-info">
                  <h2>{c.title}</h2>
                  <p>{c.issuer}</p>
                  <span className="tag">{c.category}</span>
                </div>
              </article>
            ))}
          </div>
          {profile.certificates.length === 0 && (
            <p>No featured achievements yet.</p>
          )}
        </>
      ) : (
        <p role="status">Loading profile…</p>
      )}
    </main>
  );
}
