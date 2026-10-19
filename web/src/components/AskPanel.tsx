import { useRef, useState } from "react";
import { ask } from "../api";
import { LABELS, SUGGESTED, askMeta, askStatus, pushExchange } from "../lib/ask";
import type { AskResult, Lang, Profile } from "../types";

interface Props {
  matchId: string;
  profile: Profile;
  lang: Lang;
}

interface Exchange {
  id: number;
  question: string;
  result: AskResult | null;
  error: string | null;
}

const QUESTION_MAX = 300;

/** The question desk: one question at a time, answered from this match's data only. Mount it with `key={matchId}`. */
export function AskPanel({ matchId, profile, lang }: Props) {
  const L = LABELS[lang];
  const [draft, setDraft] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const conversation = useRef<string | null>(null);
  const seq = useRef(0);

  const submit = async (text: string) => {
    const question = text.trim().slice(0, QUESTION_MAX);
    if (!question || busy) return;
    const id = ++seq.current;
    setBusy(true);
    setDraft("");
    setExchanges((list) => pushExchange(list, { id, question, result: null, error: null }));
    const patch = (update: Partial<Exchange>) =>
      setExchanges((list) => list.map((x) => (x.id === id ? { ...x, ...update } : x)));
    try {
      const result = await ask(matchId, { question, profile, lang, conversation_id: conversation.current });
      conversation.current = result.conversation_id;
      patch({ result });
    } catch {
      patch({ error: L.error });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="ask" aria-label={L.title}>
      <form
        className="ask__head"
        onSubmit={(e) => {
          e.preventDefault();
          void submit(draft);
        }}
      >
        <h2>
          <label htmlFor="ask-input">{L.title}</label>
        </h2>
        <input
          id="ask-input"
          className="ask__input"
          type="text"
          autoComplete="off"
          maxLength={QUESTION_MAX}
          placeholder={L.placeholder}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className="button" disabled={busy || !draft.trim()}>
          {L.ask}
        </button>
      </form>
      <ul className="ask__chips" aria-label={L.suggested}>
        {SUGGESTED[lang].map((q) => (
          <li key={q}>
            <button type="button" className="ask__chip" disabled={busy} onClick={() => void submit(q)}>
              {q}
            </button>
          </li>
        ))}
      </ul>
      {exchanges.length ? (
        <ol className="ask__log" aria-live="polite">
          {exchanges.map((x) => {
            const status = x.result ? askStatus(x.result, lang) : null;
            return (
              <li key={x.id} className="ask__item">
                <p className="ask__q">{x.question}</p>
                {x.result ? (
                  <>
                    <p className="ask__a">{x.result.answer}</p>
                    <footer className="ask__meta">
                      <span className={`badge badge--${status!.tone}`}>{status!.label}</span>
                      {x.result.citations.length ? (
                        <ul className="chips">
                          {x.result.citations.map((c, i) => (
                            <li key={`${c.stat}-${i}`}>
                              <span>{c.stat.replace("_", " ")}</span> {c.value}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <span className="ask__time">{askMeta(x.result, lang)}</span>
                    </footer>
                  </>
                ) : (
                  <p className={x.error ? "ask__a error" : "ask__a ask__a--pending"}>{x.error ?? L.thinking}</p>
                )}
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}
