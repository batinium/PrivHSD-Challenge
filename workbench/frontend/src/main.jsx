import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Brain,
  Clipboard,
  Copy,
  Download,
  Info,
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

function ModelPanel({ status, result, runModel, setRunModel }) {
  const ensemble = status?.token_policy_ensemble || {};
  const advisory = result?.model_advisory;
  const metrics = advisory?.metrics || ensemble.metrics;
  const actionCounts = advisory?.action_counts || {};
  const modelSpans = advisory?.spans || [];
  return (
    <section className="panel model-panel">
      <div className="panel-heading">
        <h2>Model Guidance</h2>
        <Brain size={18} />
      </div>
      <div className="layer-row active">
        <strong>Deterministic layer</strong>
        <span>Active</span>
      </div>
      <div className={`layer-row ${ensemble.available ? "ready" : "inactive"}`}>
        <strong>RoBERTa + HateBERT ensemble</strong>
        <span>{runModel ? "Requested" : ensemble.available ? "Available" : "Missing"}</span>
      </div>
      <label className="check model-toggle">
        <input
          checked={runModel}
          disabled={!ensemble.available}
          onChange={(event) => setRunModel(event.target.checked)}
          type="checkbox"
        />
        <span>Run ensemble on this text</span>
      </label>
      {metrics ? (
        <div className="metric-strip">
          <span>Macro F1 {metrics.macro_f1 ?? "n/a"}</span>
          <span>Target F1 {metrics.protect_target_f1 ?? "n/a"}</span>
          <span>HSD F1 {metrics.protect_hsd_f1 ?? "n/a"}</span>
        </div>
      ) : null}
      {advisory ? (
        <div className="advisory-box">
          <strong>Status: {advisory.status}</strong>
          <p>{advisory.message || "Advisory token actions are available below."}</p>
          {Object.keys(actionCounts).length ? (
            <Tags values={Object.entries(actionCounts).map(([key, value]) => `${key}: ${value}`)} />
          ) : null}
          {modelSpans.length ? (
            <div className="mini-table">
              {modelSpans.slice(0, 8).map((span, index) => (
                <div className="mini-row" key={`${span.action}-${index}`}>
                  <span>{span.action}</span>
                  <span>{span.start}-{span.end}</span>
                  <span>{span.confidence}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function GuidancePanel({ result, status }) {
  const llm = result?.llm_guidance || status?.llm_guidance;
  const lexicon = status?.lexicon_policy;
  const presidio = result?.presidio_augment;
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Fallbacks</h2>
        <Info size={18} />
      </div>
      <div className="guidance-block">
        <strong>LLM guidance</strong>
        <p>{llm?.message || llm?.role || "Last-resort semantic review is not automatic."}</p>
        {result?.llm_guidance ? (
          <Tags
            values={
              result.llm_guidance.recommend_review
                ? result.llm_guidance.reasons
                : ["no_llm_review_recommended"]
            }
          />
        ) : null}
      </div>
      <div className="guidance-block">
        <strong>Lexicon and rules</strong>
        <p>{lexicon?.role || "Street suffixes, target lexicons, and cue checks run first."}</p>
        {presidio ? (
          <Tags
            values={[
              `presidio: ${presidio.enabled ? "enabled" : "off"}`,
              `accepted: ${presidio.accepted_span_count ?? 0}`,
              `rejected: ${presidio.rejected_span_count ?? 0}`
            ]}
          />
        ) : null}
      </div>
    </section>
  );
}

function App() {
  const [text, setText] = useState("");
  const [mode, setMode] = useState("balanced");
  const [styleScrub, setStyleScrub] = useState(false);
  const [generalizeTargets, setGeneralizeTargets] = useState(false);
  const [usePresidio, setUsePresidio] = useState(false);
  const [runModel, setRunModel] = useState(false);
  const [modelStatus, setModelStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/model-status")
      .then((response) => response.json())
      .then(setModelStatus)
      .catch(() => setModelStatus(null));
  }, []);

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
          generalize_targets: generalizeTargets ? true : null,
          use_presidio: usePresidio,
          run_model_ensemble: runModel
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
        <label className="check">
          <input
            checked={usePresidio}
            disabled={modelStatus?.lexicon_policy?.presidio_available === false}
            onChange={(event) => setUsePresidio(event.target.checked)}
            type="checkbox"
          />
          <span>Filtered Presidio</span>
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

        <ModelPanel
          result={result}
          runModel={runModel}
          setRunModel={setRunModel}
          status={modelStatus}
        />

        <GuidancePanel result={result} status={modelStatus} />
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
