import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { streamChat } from "../lib/data";

const QUICK = [
  ["Explain simply", "Explain this paper simply, as if to a final-year computer science student."],
  ["Key contributions", "What are the key contributions of this paper?"],
  ["Limitations", "What are the limitations and open questions of this paper?"],
  ["Reuse in my project", "How could I reuse the ideas or code from this paper in my own project?"],
];

const storageKey = (id) => `rinfo-chat:${id}`;

function loadHistory(id) {
  try {
    return JSON.parse(sessionStorage.getItem(storageKey(id))) || [];
  } catch {
    return [];
  }
}

export default function ChatPanel({ paper }) {
  const [messages, setMessages] = useState(() => loadHistory(paper.id));
  const [input, setInput] = useState("");
  const [web, setWeb] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [noFulltext, setNoFulltext] = useState(false);
  const abortRef = useRef(null);
  const logRef = useRef(null);

  useEffect(() => {
    setMessages(loadHistory(paper.id));
    setError("");
    return () => abortRef.current?.abort();
  }, [paper.id]);

  useEffect(() => {
    sessionStorage.setItem(storageKey(paper.id), JSON.stringify(messages.filter((m) => !m.pending)));
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, paper.id]);

  async function ask(question) {
    const text = question.trim();
    if (!text || busy) return;
    setError("");
    setInput("");
    const history = [...messages, { role: "user", content: text }];
    setMessages([...history, { role: "assistant", content: "", pending: true, sources: [] }]);
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const update = (fn) =>
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = fn(next[next.length - 1]);
        return next;
      });
    try {
      await streamChat(
        { paper, messages: history.map(({ role, content }) => ({ role, content })), web, signal: controller.signal },
        (ev) => {
          if (ev.type === "sources") {
            setNoFulltext(!ev.fulltext);
            update((m) => ({ ...m, sources: ev.sources }));
          } else if (ev.type === "delta") update((m) => ({ ...m, content: m.content + ev.text }));
          else if (ev.type === "error") throw new Error(ev.message);
          else if (ev.type === "done") update((m) => ({ ...m, pending: false }));
        },
      );
      update((m) => ({ ...m, pending: false }));
    } catch (err) {
      if (err.name === "AbortError") return;
      setError(err.message);
      setMessages(history.slice(0, -1)); // drop the failed turn so a retry starts clean
      setInput(text);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="chat" aria-label="Ask about this paper">
      <div className="chat-head">
        <div className="kicker">The Research Desk</div>
        <h2 className="chat-title">Ask about this paper</h2>
        <p className="chat-sub">Answers come only from the paper&rsquo;s own text.</p>
      </div>
      <div className="chat-log" ref={logRef}>
        {messages.length === 0 && (
          <div className="chat-quick">
            {QUICK.map(([label, q]) => (
              <button key={label} type="button" className="chip" onClick={() => ask(q)} disabled={busy}>
                {label}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg msg-${m.role}`}>
            <div className="msg-who">{m.role === "user" ? "You" : "The Desk"}</div>
            {m.role === "assistant" ? (
              <div className="msg-body">
                {m.content ? <Markdown>{m.content}</Markdown> : <span className="typing">Reading the paper…</span>}
                {m.sources?.length > 0 && (
                  <p className="msg-sources">
                    Web sources:{" "}
                    {m.sources.map((s, j) => (
                      <a key={s.url} href={s.url} target="_blank" rel="noreferrer">
                        {s.host || s.title}
                        {j < m.sources.length - 1 ? " · " : ""}
                      </a>
                    ))}
                  </p>
                )}
              </div>
            ) : (
              <div className="msg-body">{m.content}</div>
            )}
          </div>
        ))}
      </div>
      {noFulltext && <p className="notice notice-warn">The PDF couldn&rsquo;t be read, so answers use the abstract only.</p>}
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      <form
        className="chat-form"
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <textarea
          rows={2}
          placeholder="Ask anything about this paper…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(input);
            }
          }}
        />
        <div className="chat-actions">
          <label className="check">
            <input type="checkbox" checked={web} onChange={(e) => setWeb(e.target.checked)} /> Also search the web
          </label>
          <span className="chat-buttons">
            {messages.length > 0 && !busy && (
              <button type="button" className="link-button" onClick={() => setMessages([])}>
                Clear
              </button>
            )}
            <button className="btn btn-ink" type="submit" disabled={busy || !input.trim()}>
              {busy ? "Answering…" : "Ask"}
            </button>
          </span>
        </div>
      </form>
    </aside>
  );
}
