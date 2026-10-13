import { useEffect, useId, useRef, useState } from "react";
import { searchPlaces } from "../lib/api";

/** Text field with place suggestions. `value` is {label, lat, lon} or null. */
export default function PlaceInput({ label, name, value, onChange, placeholder }) {
  const id = useId();
  const [text, setText] = useState(value?.label ?? "");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [status, setStatus] = useState("idle"); // idle | loading | empty | error
  const typed = useRef(false);

  // Sync when a place is chosen from outside (e.g. "Fill an example trip").
  // Typing clears `value` to null, which must not wipe what the user typed.
  useEffect(() => {
    if (value) setText(value.label);
  }, [value]);

  useEffect(() => {
    if (!typed.current) return;
    const q = text.trim();
    if (q.length < 2) {
      setResults([]);
      setStatus("idle");
      return;
    }
    const ctrl = new AbortController();
    setStatus("loading");
    const t = setTimeout(() => {
      searchPlaces(q, ctrl.signal)
        .then((r) => {
          setResults(r);
          setActive(0);
          setStatus(r.length ? "idle" : "empty");
        })
        .catch((e) => {
          if (e.name !== "AbortError") setStatus("error");
        });
    }, 220);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [text]);

  const choose = (place) => {
    typed.current = false;
    onChange(place);
    setText(place.label);
    setOpen(false);
  };

  const onKeyDown = (e) => {
    if (!open || !results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const listId = `${id}-list`;
  return (
    <div className="field place">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        name={name}
        type="text"
        autoComplete="off"
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls={listId}
        aria-activedescendant={open && results.length ? `${listId}-${active}` : undefined}
        placeholder={placeholder}
        value={text}
        onChange={(e) => {
          typed.current = true;
          setText(e.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
      />
      {open && (results.length > 0 || status !== "idle") && (
        <ul className="suggestions" id={listId} role="listbox">
          {status === "loading" && !results.length && <li className="hint">Searching…</li>}
          {status === "empty" && <li className="hint">No places match “{text}”.</li>}
          {status === "error" && <li className="hint">Place search is unavailable right now.</li>}
          {results.map((r, i) => (
            <li
              key={`${r.label}-${i}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "is-active" : ""}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(r);
              }}
              onMouseEnter={() => setActive(i)}
            >
              {r.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
