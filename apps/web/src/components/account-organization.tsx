"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "./ui/button";

type Kind = "collections" | "tags";
type Group = {
  id: string;
  name: string;
  collection_items?: Member[];
  certificate_tags?: Member[];
};
type Member = { certificate_id: string };

export function AccountOrganization({
  certificates,
}: {
  certificates: { id: string; title: string }[];
}) {
  const [kind, setKind] = useState<Kind>("collections");
  const [groups, setGroups] = useState<Group[]>([]);
  const [membersOnly, setMembersOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(
    () => api<Group[]>(`/account/organization/${kind}`),
    [kind],
  );
  useEffect(() => {
    let active = true;
    load()
      .then((rows) => {
        if (active) setGroups(rows);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [load]);
  const group = groups.find((row) => row.id === selected);
  const members = group?.collection_items ?? group?.certificate_tags ?? [];
  async function change(work: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await work();
      setGroups(await load());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Please retry.");
    } finally {
      setBusy(false);
    }
  }
  async function toggleMembership(certificateId: string, checked: boolean) {
    if (!group || busy) return;
    const previous = groups;
    const key = kind === "tags" ? "certificate_tags" : "collection_items";
    const next = checked
      ? members.filter((m) => m.certificate_id !== certificateId)
      : [...members, { certificate_id: certificateId }];
    setGroups(
      groups.map((row) =>
        row.id === group.id ? { ...row, [key]: next } : row,
      ),
    );
    setBusy(true);
    setError("");
    try {
      await api(
        `/account/organization/${kind}/${group.id}/${certificateId}`,
        checked ? "DELETE" : "PUT",
      );
    } catch (e) {
      setGroups(previous);
      setError(e instanceof Error ? e.message : "Membership update failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>Collections and tags</h2>
      {loading && <p role="status">Loading your library…</p>}
      <label>
        Organize by
        <select
          disabled={busy}
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as Kind);
            setGroups([]);
            setLoading(true);
            setSelected("");
            setError("");
          }}
        >
          <option value="collections">Collections</option>
          <option value="tags">Tags</option>
        </select>
      </label>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void change(async () => {
            const [created] = await api<Group[]>(
              `/account/organization/${kind}`,
              "POST",
              { name: name.trim() },
            );
            setSelected(created.id);
            setName("");
          });
        }}
      >
        <label>
          New {kind === "tags" ? "tag" : "collection"} name
          <input
            required
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <Button disabled={loading || busy || !name.trim()}>
          Create {kind === "tags" ? "tag" : "collection"}
        </Button>
      </form>
      <label>
        Manage membership
        <select
          value={selected}
          disabled={busy}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">
            Choose a {kind === "tags" ? "tag" : "collection"}
          </option>
          {groups.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
      </label>
      {group && (
        <label className="automation-check">
          <input
            type="checkbox"
            checked={membersOnly}
            onChange={(e) => setMembersOnly(e.target.checked)}
          />
          Show assigned certificates only
        </label>
      )}
      {group && (
        <fieldset>
          <legend>Certificates in {group.name}</legend>
          {certificates.length === 0 && (
            <p>No certificates in this vault view.</p>
          )}
          {membersOnly && !members.length && (
            <p>No certificates assigned yet.</p>
          )}
          {certificates
            .filter(
              (c) =>
                !membersOnly || members.some((m) => m.certificate_id === c.id),
            )
            .map((c) => {
              const checked = members.some((m) => m.certificate_id === c.id);
              return (
                <div className="automation-row" key={c.id}>
                  <label className="automation-check">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={busy}
                      onChange={() => void toggleMembership(c.id, checked)}
                    />
                    {c.title}
                  </label>
                  <a
                    href={`/api/account/pipeline/certificates/${c.id}/download?inline=true`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View PDF
                  </a>
                </div>
              );
            })}
        </fieldset>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
