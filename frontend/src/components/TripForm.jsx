import { useState } from "react";
import { searchPlaces } from "../lib/api";
import { toLocalInput, tzName } from "../lib/format";
import PlaceInput from "./PlaceInput";

const INTERVALS = [10, 25, 50];

function defaultDeparture() {
  const d = new Date(Date.now() + 30 * 60 * 1000);
  d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15, 0, 0);
  return toLocalInput(d);
}

const EXAMPLE = {
  origin: { label: "Dallas, Texas, United States", lat: 32.7767, lon: -96.797 },
  destination: { label: "Chicago, Illinois, United States", lat: 41.8781, lon: -87.6298 },
  load: "42000",
};

export default function TripForm({ onSubmit, busy }) {
  const [origin, setOrigin] = useState(null);
  const [destination, setDestination] = useState(null);
  const [departure, setDeparture] = useState(defaultDeparture);
  const [load, setLoad] = useState("");
  const [interval, setInterval] = useState(25);
  const [formError, setFormError] = useState("");

  // If the user typed a place but didn't pick a suggestion, take the top match.
  const resolve = async (place, inputLabel) => {
    if (place) return place;
    const text = inputLabel?.trim();
    if (!text) return null;
    const [first] = await searchPlaces(text);
    return first ?? null;
  };

  const submit = async (e) => {
    e.preventDefault();
    setFormError("");
    const form = e.currentTarget;
    const o = await resolve(origin, form.elements.origin_text?.value);
    const d = await resolve(destination, form.elements.destination_text?.value);
    if (!o || !d) return setFormError("Pick an origin and a destination from the suggestions.");
    const loadLb = Number(load);
    if (!load || Number.isNaN(loadLb) || loadLb < 0) return setFormError("Enter the load weight in pounds.");
    const dep = new Date(departure);
    if (Number.isNaN(dep.getTime())) return setFormError("Enter a departure date and time.");
    setOrigin(o);
    setDestination(d);
    onSubmit({ origin: o, destination: d, departure: dep.toISOString(), load_lb: loadLb, interval_miles: interval });
  };

  const fillExample = () => {
    setOrigin(EXAMPLE.origin);
    setDestination(EXAMPLE.destination);
    setLoad(EXAMPLE.load);
    setFormError("");
  };

  return (
    <form className="trip-form" onSubmit={submit} noValidate>
      <div className="od">
        <PlaceInput label="From" name="origin_text" value={origin} onChange={setOrigin} placeholder="City or address" />
        <PlaceInput label="To" name="destination_text" value={destination} onChange={setDestination} placeholder="City or address" />
      </div>
      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure ({tzName()})</label>
          <input id="departure" type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight</label>
          <div className="suffix-input">
            <input
              id="load"
              type="number"
              inputMode="numeric"
              min="0"
              max="120000"
              step="500"
              placeholder="42000"
              value={load}
              onChange={(e) => setLoad(e.target.value)}
            />
            <span>lb</span>
          </div>
        </div>
      </div>
      <fieldset className="field">
        <legend>Check weather every</legend>
        <div className="segmented" role="radiogroup">
          {INTERVALS.map((n) => (
            <label key={n} className={interval === n ? "is-on" : ""}>
              <input type="radio" name="interval" value={n} checked={interval === n} onChange={() => setInterval(n)} />
              {n} mi
            </label>
          ))}
        </div>
      </fieldset>
      {formError && (
        <p className="form-error" role="alert">
          {formError}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Planning routes…" : "Plan routes"}
        </button>
        <button type="button" className="link" onClick={fillExample} disabled={busy}>
          Fill an example trip
        </button>
      </div>
    </form>
  );
}
