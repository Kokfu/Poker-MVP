import { useEffect, useState } from "react";

type Storage = { path: string; size_bytes: number; hands: number; opponents: number; first_logged: string | null; last_logged: string | null };

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Where the Coach keeps logged hands, and controls to delete them. */
export default function CoachData({ opponents, onChanged }: { opponents: { name: string; hands: number }[]; onChanged: () => void }) {
  const [storage, setStorage] = useState<Storage>();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      const response = await fetch("/api/coach/storage");
      if (!response.ok) throw new Error("Could not read the Coach database.");
      setStorage(await response.json());
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Could not read the Coach database.");
    }
  }

  useEffect(() => { load(); }, []);

  async function remove(url: string, key: string, question: string, done: string) {
    if (!window.confirm(question)) return;
    setBusy(key); setError(""); setNotice("");
    try {
      const response = await fetch(url, { method: "DELETE" });
      if (!response.ok) throw new Error("Delete failed. Nothing was removed.");
      setNotice(done);
      onChanged();
      await load();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Delete failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="coach-data">
      <h3>Saved data</h3>
      <p className="muted">Logged hands are kept in one SQLite file on this computer. The app never uploads it, but a cloud-synced folder (such as OneDrive) will sync it. Deleting cannot be undone, so copy the file first if you want a backup.</p>
      {storage && (
        <dl className="stat-row">
          <div className="stat-wide"><dt>File</dt><dd><code>{storage.path}</code></dd></div>
          <div><dt>Hands</dt><dd>{storage.hands}</dd></div>
          <div><dt>Opponents</dt><dd>{storage.opponents}</dd></div>
          <div><dt>Size</dt><dd>{formatBytes(storage.size_bytes)}</dd></div>
          {storage.first_logged && <div><dt>Logged</dt><dd>{new Date(storage.first_logged).toLocaleDateString()} – {new Date(storage.last_logged ?? storage.first_logged).toLocaleDateString()}</dd></div>}
        </dl>
      )}
      {notice && <p className="coach-notice" role="status">{notice}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {opponents.length > 0 ? (
        <>
          <h4>By opponent</h4>
          <ul className="data-list">
            {opponents.map((item) => (
              <li key={item.name}>
                <span>{item.name}</span>
                <span className="muted">{item.hands} {item.hands === 1 ? "hand" : "hands"}</span>
                <button
                  type="button" className="secondary danger" disabled={busy !== null}
                  onClick={() => remove(`/api/coach/opponents/${encodeURIComponent(item.name)}`, item.name,
                    `Delete all ${item.hands} hands logged against ${item.name}? This cannot be undone.`, `Deleted ${item.name}'s hands.`)}
                >
                  {busy === item.name ? "Deleting…" : "Delete"}
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button" className="danger-solid" disabled={busy !== null}
            onClick={() => remove("/api/coach/hands?confirm=delete-all", "all",
              `Delete every logged hand (${storage?.hands ?? "all"}) for every opponent? This cannot be undone.`, "All Coach data deleted.")}
          >
            {busy === "all" ? "Deleting…" : "Delete all Coach data"}
          </button>
        </>
      ) : (
        <p className="muted">No hands logged yet. Finish a heads-up hand and press “Log hand” to start building opponent profiles.</p>
      )}
    </div>
  );
}
