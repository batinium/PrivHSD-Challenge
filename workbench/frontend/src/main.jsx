import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Clipboard,
  Copy,
  Download,
  Play,
  RotateCcw,
  ShieldCheck
} from "lucide-react";
import "./styles.css";

const SAMPLE_TEXT =
  "My name is Alex Morgan, email alex.morgan@example.com. @angry_user said Muslims should leave Boston on Jan 12, 2025.";

function Gauge({ label, value, tone = "good" }) {
  return (
    <section className="gauge">
      <div className="gauge-top">
        <span>{label}</span>
        <strong>{value}%</strong>
      </div>
      <div className="meter" aria-hidden="true">
        <div className={`meter-fill ${tone}`} style={{ width: `${value}%` }} />
      </div>
    </section>
  );
}

function splitByRanges(text, ranges) {
  if (!text || !ranges?.length) {
    return [{ text, marked: false, key: "plain" }];
  }
  const spans = ranges
    .filter((item) => Number.isInteger(item.start) && Number.isInteger(item.end) && item.end > item.start)
    .sort((a, b) => a.start - b.start || b.priority - a.priority);
  const parts = [];
  let cursor = 0;
  spans.forEach((span, index) => {
    if (span.start < cursor) {
      return;
    }
    if (span.start > cursor) {
      parts.push({ text: text.slice(cursor, span.start), marked: false, key: `p-${index}` });
    }
    parts.push({
      text: text.slice(span.start, span.end),
      marked: true,
      type: span.type,
      role: span.role,
      key: `m-${index}`
    });
    cursor = span.end;
  });
  if (cursor < text.length) {
    parts.push({ text: text.slice(cursor), marked: false, key: "tail" });
  }
  return parts;
}

function splitOriginal(text, transformations, protectedSpans) {
  const masked = (transformations || []).map((item) => ({
    start: item.source_start,
    end: item.source_end,
    type: item.entity_type,
    role: "mask",
    priority: 2
  }));
  const protectedRanges = (protectedSpans || []).map((item) => ({
    start: item.start,
    end: item.end,
    type: item.category || item.entity_type,
    role: "protect",
    priority: 1
  }));
  return splitByRanges(text, [...masked, ...protectedRanges]);
}

function splitOutput(text, protectedSpans) {
  const pattern = /(\[[A-Z][A-Z_]*(?::[A-Za-z0-9_/-]+)?\])/g;
  const ranges = [];
  let match;
  while ((match = pattern.exec(text)) !== null) {
    ranges.push({
      start: match.index,
      end: pattern.lastIndex,
      type: "placeholder",
      role: "mask",
      priority: 2
    });
  }
  const protectedRanges = (protectedSpans || []).map((item) => ({
    start: item.start,
    end: item.end,
    type: item.category || item.entity_type,
    role: "protect",
    priority: 1
  }));
  return splitByRanges(text, [...ranges, ...protectedRanges]);
}

function HighlightedText({ parts, empty }) {
  if (empty) {
    return <div className="empty-output">No output yet</div>;
  }
  return (
    <pre className="highlight-box">
      {parts.map((part) =>
        part.marked ? (
          <mark className={part.role || "mask"} key={part.key} title={part.type || "placeholder"}>
            {part.text}
          </mark>
        ) : (
          <span key={part.key}>{part.text}</span>
        )
      )}
    </pre>
  );
}

function Tags({ values }) {
  if (!values?.length) {
    return <span className="muted">None</span>;
  }
  return (
    <div className="tag-list">
      {values.map((value) => (
        <span className="tag" key={value}>
          {value}
        </span>
      ))}
    </div>
  );
}

function App() {
  const [text, setText] = useState("");
  const [mode, setMode] = useState("balanced");
  const [styleScrub, setStyleScrub] = useState(false);
  const [generalizeTargets, setGeneralizeTargets] = useState(false);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const originalParts = useMemo(
    () => splitOriginal(text, result?.transformations || [], result?.protected_spans || []),
    [text, result]
  );
  const outputParts = useMemo(
    () => splitOutput(result?.privatized_text || "", result?.protected_output_spans || []),
    [result]
  );

  async function runPrivatize() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/privatize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          mode,
          style_scrub: styleScrub,
          generalize_targets: generalizeTargets ? true : null
        })
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed with ${response.status}`);
      }
      setResult(await response.json());
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setBusy(false);
    }
  }

  function copyOutput() {
    if (result?.privatized_text) {
      navigator.clipboard.writeText(result.privatized_text);
    }
  }

  function downloadAudit() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json"
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "contextsafe-hsd-audit.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="brand">
            <ShieldCheck size={22} />
            <span>ContextSafe-HSD Workbench</span>
          </div>
          <p>Local privacy review</p>
        </div>
        <div className="status-pill">FastAPI + React</div>
      </header>

      <section className="toolbar" aria-label="Controls">
        <div className="segmented" role="group" aria-label="Mode">
          {["balanced", "utility", "privacy"].map((option) => (
            <button
              className={mode === option ? "active" : ""}
              key={option}
              onClick={() => setMode(option)}
              type="button"
            >
              {option}
            </button>
          ))}
        </div>
        <label className="check">
          <input
            checked={styleScrub}
            onChange={(event) => setStyleScrub(event.target.checked)}
            type="checkbox"
          />
          <span>Style scrub</span>
        </label>
        <label className="check">
          <input
            checked={generalizeTargets}
            onChange={(event) => setGeneralizeTargets(event.target.checked)}
            type="checkbox"
          />
          <span>Generalize targets</span>
        </label>
        <button className="ghost" onClick={() => setText(SAMPLE_TEXT)} type="button">
          <Clipboard size={17} />
          Sample
        </button>
        <button className="ghost icon-only" onClick={() => { setText(""); setResult(null); }} title="Reset" type="button">
          <RotateCcw size={18} />
        </button>
        <button className="primary" disabled={busy} onClick={runPrivatize} type="button">
          <Play size={18} />
          {busy ? "Running" : "Run"}
        </button>
      </section>

      {error ? (
        <section className="error-line">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </section>
      ) : null}

      <section className="workspace">
        <section className="editor-pane">
          <div className="pane-title">
            <h2>Input</h2>
            <span>{text.length} chars</span>
          </div>
          <textarea
            aria-label="Input text"
            onChange={(event) => setText(event.target.value)}
            placeholder="Paste text here"
            spellCheck="false"
            value={text}
          />
          <div className="preview-block">
            <h3>Detected spans</h3>
            <HighlightedText parts={originalParts} empty={!text} />
          </div>
        </section>

        <section className="editor-pane">
          <div className="pane-title">
            <h2>Output</h2>
            <div className="pane-actions">
              <button className="ghost icon-only" disabled={!result} onClick={copyOutput} title="Copy output" type="button">
                <Copy size={17} />
              </button>
              <button className="ghost icon-only" disabled={!result} onClick={downloadAudit} title="Download audit JSON" type="button">
                <Download size={17} />
              </button>
            </div>
          </div>
          <HighlightedText parts={outputParts} empty={!result} />
        </section>
      </section>

      <section className="evidence-grid">
        <section className="panel">
          <h2>Gauges</h2>
          <div className="gauge-grid">
            <Gauge label="Privacy gain" value={result?.gauges?.privacy_gain ?? 0} />
            <Gauge label="Cue retention" value={result?.gauges?.cue_retention ?? 100} />
            <Gauge label="Text similarity" value={result?.gauges?.text_similarity ?? 100} tone="neutral" />
            <Gauge label="Residual risk" value={result?.gauges?.residual_risk ?? 0} tone="risk" />
          </div>
        </section>

        <section className="panel">
          <h2>Context</h2>
          <Tags values={result?.context?.original?.context_tags || []} />
          <h3>Warnings</h3>
          <Tags values={result?.warnings || []} />
        </section>

        <section className="panel wide">
          <h2>Transformations</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Replacement</th>
                  <th>Source</th>
                  <th>Input Offset</th>
                  <th>Output Offset</th>
                </tr>
              </thead>
              <tbody>
                {(result?.transformations || []).map((item, index) => (
                  <tr key={`${item.entity_type}-${index}`}>
                    <td>{item.entity_type || "STYLE"}</td>
                    <td>{item.replacement || "-"}</td>
                    <td>{item.source || "-"}</td>
                    <td>{Number.isInteger(item.source_start) ? `${item.source_start}-${item.source_end}` : "-"}</td>
                    <td>{Number.isInteger(item.output_start) ? `${item.output_start}-${item.output_end}` : "-"}</td>
                  </tr>
                ))}
                {!result?.transformations?.length ? (
                  <tr>
                    <td colSpan="5" className="muted-cell">No transformations</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
