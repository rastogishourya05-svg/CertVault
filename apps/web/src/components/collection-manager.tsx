"use client";
import { useEffect, useState } from "react";
import { FolderLock, Plus, ShieldCheck } from "lucide-react";
import { Button } from "./ui/button";
import { api, type Certificate } from "@/lib/api";
type Collection = {
  id: string;
  name: string;
  certificate_ids: string[];
  created: string;
};
export function CollectionManager({ certs }: { certs: Certificate[] }) {
  const [items, setItems] = useState<Collection[]>([]),
    [current, setCurrent] = useState(""),
    [name, setName] = useState(""),
    [ids, setIds] = useState<string[]>([]),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  useEffect(() => {
    api<Collection[]>("/collections")
      .then(setItems)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  function select(c: Collection | null) {
    setCurrent(c?.id || "");
    setName(c?.name || "");
    setIds(c?.certificate_ids || []);
    setMessage("");
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ id?: string }>(
        current ? `/collections/${current}` : "/collections",
        current ? "PUT" : "POST",
        { name, certificate_ids: ids },
      );
      setItems(await api<Collection[]>("/collections"));
      if (result.id) setCurrent(result.id);
      setMessage("Private collection saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save collection.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="settings-grid">
      <section className="panel">
        <div className="section-heading">
          <h2>Your collections</h2>
          <Button variant="outline" onClick={() => select(null)}>
            <Plus size={16} />
            New
          </Button>
        </div>
        <p className="muted">
          Group your learning by goal, opportunity, or chapter. Collections stay
          private.
        </p>
        {loading ? (
          <p role="status">Loading collections…</p>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <FolderLock size={32} />
            <h3>Make space for a new chapter.</h3>
            <p>Create your first collection alongside.</p>
          </div>
        ) : (
          items.map((c) => (
            <button
              key={c.id}
              className={`collection-choice ${current === c.id ? "selected" : ""}`}
              onClick={() => select(c)}
            >
              <FolderLock size={19} />
              <span>
                <strong>{c.name}</strong>
                <small>{c.certificate_ids.length} certificates · Private</small>
              </span>
            </button>
          ))
        )}
      </section>
      <section className="panel">
        <h2>{current ? "Edit collection" : "Create a collection"}</h2>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {message && (
          <p role="status" className="muted">
            {message}
          </p>
        )}
        <form onSubmit={save}>
          <label>
            Collection name
            <input
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My next opportunity"
            />
          </label>
          <fieldset>
            <legend>Choose certificates</legend>
            {certs.length === 0 ? (
              <p className="muted">
                Import a certificate to add it here. Empty collections are
                welcome too.
              </p>
            ) : (
              certs.map((c) => (
                <label key={c.id} className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={ids.includes(c.id)}
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
          </fieldset>
          <Button disabled={busy || !name.trim()}>
            {busy ? "Saving…" : "Save collection"}
          </Button>
        </form>
        <p className="fine-print">
          <ShieldCheck size={14} />
          Organizing never changes who can access your files.
        </p>
      </section>
    </div>
  );
}
