import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Brain,
  Clipboard,
  Copy,
  Download,
  FileText,
  Info,
  Play,
  RotateCcw,
  ShieldCheck,
  Upload
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

function formatScore(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return value.toFixed(3);
}

function detectCsvHeaders(csvText) {
  const firstLine = (csvText || "").split(/\r?\n/, 1)[0] || "";
  return firstLine
    .split(",")
    .map((value) => value.trim().replace(/^"|"$/g, ""))
    .filter(Boolean);
}

function preferredColumn(headers, names, fallback) {
  const lowered = headers.map((value) => value.toLowerCase());
  for (const name of names) {
    const index = lowered.indexOf(name);
    if (index >= 0) return headers[index];
  }
  return fallback !== undefined ? fallback : headers[0] || "";
}

function downloadTextFile(name, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function CsvWorkbench({ modelStatus }) {
  const [csvText, setCsvText] = useState("");
  const [csvName, setCsvName] = useState("contextsafe-hsd.csv");
  const [headers, setHeaders] = useState([]);
  const [textCol, setTextCol] = useState("");
  const [idCol, setIdCol] = useState("");
  const [mode, setMode] = useState("auto");
  const [replaceText, setReplaceText] = useState(true);
  const [providers, setProviders] = useState({ presidio: true, gliner: true, scrubadub: true });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selectedProviders = Object.entries(providers)
    .filter(([, enabled]) => enabled)
    .map(([name]) => name);
  const disabledProviders = Object.entries(providers)
    .filter(([, enabled]) => !enabled)
    .map(([name]) => name);
  const metrics = result?.audit?.summary?.metrics || {};
  const providerItems = result?.manifest?.providers || {};
  const modelItems = result?.manifest?.models || {};
  const csvGauges = {
    privacy: Math.round((metrics.privacy_gain_mean || 0) * 100),
    cue: Math.round((metrics.target_cue_retention_mean ?? 1) * 100),
    similarity: Math.round((metrics.character_utility_retention_mean ?? 1) * 100),
    residual: Math.min(100, (metrics.residual_identifier_count || 0) * 10)
  };

  async function handleFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const detected = detectCsvHeaders(text);
    setCsvText(text);
    setCsvName(file.name || "contextsafe-hsd.csv");
    setHeaders(detected);
    setTextCol(preferredColumn(detected, ["text", "tweet", "content", "comment"]));
    setIdCol(preferredColumn(detected, ["id", "source_id", "case_id"], ""));
    setResult(null);
    setError("");
  }

  async function runCsv() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/csv/privatize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          csv_text: csvText,
          text_col: textCol,
          id_col: idCol || null,
          output_col: "privatized_text",
          replace_text: replaceText,
          mode,
          style_scrub: false,
          providers: mode === "auto" ? [] : selectedProviders,
          disabled_providers: mode === "auto" ? disabledProviders : [],
          metric_depth: "fast"
        })
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed with ${response.status}`);
      }
      setResult(await response.json());
    } catch (err) {
      setError(err.message || "CSV processing failed");
    } finally {
      setBusy(false);
    }
  }

  function toggleProvider(name) {
    setProviders((current) => ({ ...current, [name]: !current[name] }));
  }

  return (
    <>
      <section className="csv-grid">
        <section className="panel csv-panel">
          <div className="panel-heading">
            <h2>CSV Input</h2>
            <Upload size={18} />
          </div>
          <label className="file-drop">
            <input accept=".csv,text/csv" onChange={handleFile} type="file" />
            <FileText size={20} />
            <span>{csvText ? csvName : "Choose a CSV"}</span>
          </label>
          <div className="form-grid">
            <label>
              <span>Text Column</span>
              <select value={textCol} onChange={(event) => setTextCol(event.target.value)}>
                {headers.map((header) => <option key={header} value={header}>{header}</option>)}
              </select>
            </label>
            <label>
              <span>ID Column</span>
              <select value={idCol} onChange={(event) => setIdCol(event.target.value)}>
                <option value="">None</option>
                {headers.map((header) => <option key={header} value={header}>{header}</option>)}
              </select>
            </label>
          </div>
          <div className="segmented wide-segment" role="group" aria-label="CSV mode">
            {["auto", "balanced", "privacy", "rerank"].map((option) => (
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
          <div className="provider-row">
            {["presidio", "gliner", "scrubadub"].map((name) => (
              <label className="check" key={name}>
                <input
                  checked={providers[name]}
                  disabled={modelStatus?.span_providers?.[name]?.available === false}
                  onChange={() => toggleProvider(name)}
                  type="checkbox"
                />
                <span>{name}</span>
              </label>
            ))}
          </div>
          <label className="check">
            <input checked={replaceText} onChange={(event) => setReplaceText(event.target.checked)} type="checkbox" />
            <span>Replace text column</span>
          </label>
          <button className="primary full-width" disabled={busy || !csvText || !textCol} onClick={runCsv} type="button">
            <Play size={18} />
            {busy ? "Running" : "Run CSV"}
          </button>
        </section>

        <section className="panel csv-panel">
          <div className="panel-heading">
            <h2>CSV Output</h2>
            <Download size={18} />
          </div>
          <div className="gauge-grid compact">
            <Gauge label="Privacy gain" value={csvGauges.privacy} />
            <Gauge label="Cue retention" value={csvGauges.cue} />
            <Gauge label="Similarity" value={csvGauges.similarity} tone="neutral" />
            <Gauge label="Residual risk" value={csvGauges.residual} tone="risk" />
          </div>
          <div className="download-row">
            <button
              className="ghost"
              disabled={!result}
              onClick={() => downloadTextFile(`masked-${csvName}`, result.output_csv, "text/csv")}
              type="button"
            >
              <Download size={17} />
              CSV
            </button>
            <button
              className="ghost"
              disabled={!result}
              onClick={() => downloadTextFile("contextsafe-hsd-audit.json", JSON.stringify(result.audit, null, 2), "application/json")}
              type="button"
            >
              <Download size={17} />
              Audit
            </button>
            <button
              className="ghost"
              disabled={!result}
              onClick={() => downloadTextFile("contextsafe-hsd-manifest.json", JSON.stringify(result.manifest, null, 2), "application/json")}
              type="button"
            >
              <Download size={17} />
              Manifest
            </button>
          </div>
          <div className="status-grid">
            <div>
              <strong>Providers</strong>
              <Tags values={Object.entries(providerItems).map(([name, item]) => `${name}: ${item.status}`)} />
            </div>
            <div>
              <strong>Models</strong>
              <Tags values={Object.entries(modelItems).map(([name, item]) => `${name}: ${item.status}`)} />
            </div>
          </div>
          <div className="table-wrap csv-preview">
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Length</th>
                  <th>Output Preview</th>
                </tr>
              </thead>
              <tbody>
                {(result?.preview_rows || []).map((row) => (
                  <tr key={row.row_id}>
                    <td>{row.row_id}</td>
                    <td>{row.text_length}</td>
                    <td>{row.output}</td>
                  </tr>
                ))}
                {!result?.preview_rows?.length ? (
                  <tr><td className="muted-cell" colSpan="3">No CSV processed</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </section>
      {error ? (
        <section className="error-line">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </section>
      ) : null}
    </>
  );
}

function ModelPanel({ status, result, runModel, setRunModel, runHsdClassifier, setRunHsdClassifier }) {
  const ensemble = status?.token_policy_ensemble || {};
  const hsdPrimary = status?.hsd_classifiers?.primary || {};
  const hsdRegistered = status?.hsd_classifiers || {};
  const advisory = result?.model_advisory;
  const hsd = result?.hsd_classifier;
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
      <div className={`layer-row ${hsdPrimary.available ? "ready" : "inactive"}`}>
        <strong>HSD classifier</strong>
        <span>{runHsdClassifier ? "Requested" : hsdPrimary.available ? "Available" : "Missing"}</span>
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
      <label className="check model-toggle">
        <input
          checked={runHsdClassifier}
          disabled={!hsdPrimary.available}
          onChange={(event) => setRunHsdClassifier(event.target.checked)}
          type="checkbox"
        />
        <span>Run HSD classifier</span>
      </label>
      <Tags
        values={[
          `primary: ${hsdPrimary.model_id || "not configured"}`,
          `cardiff: ${hsdRegistered.cardiff_hate_latest?.status || "registered"}`,
          `local baseline: ${hsdRegistered.local_tfidf_logreg?.status || "unknown"}`
        ]}
      />
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
      {hsd ? (
        <div className="advisory-box">
          <strong>HSD status: {hsd.status}</strong>
          <p>{hsd.message || hsd.model_id || "Classifier drift scores are available below."}</p>
          {hsd.active ? (
            <div className="metric-strip">
              <span>Original {formatScore(hsd.original_score)}</span>
              <span>Protected {formatScore(hsd.candidate_score)}</span>
              <span>Delta {formatScore(hsd.score_delta)}</span>
              <span>{hsd.original_decision} to {hsd.candidate_decision}</span>
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
  const [activeTool, setActiveTool] = useState("csv");
  const [text, setText] = useState("");
  const [mode, setMode] = useState("balanced");
  const [styleScrub, setStyleScrub] = useState(false);
  const [generalizeTargets, setGeneralizeTargets] = useState(false);
  const [textProviders, setTextProviders] = useState({ presidio: false, gliner: false, scrubadub: false });
  const [runModel, setRunModel] = useState(false);
  const [runHsdClassifier, setRunHsdClassifier] = useState(false);
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
  const selectedTextProviders = Object.entries(textProviders)
    .filter(([, enabled]) => enabled)
    .map(([name]) => name);

  function toggleTextProvider(name) {
    setTextProviders((current) => ({ ...current, [name]: !current[name] }));
  }

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
          providers: selectedTextProviders,
          use_presidio: false,
          run_model_ensemble: runModel,
          run_hsd_classifier: runHsdClassifier
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
        <div className="top-actions">
          <div className="segmented" role="group" aria-label="Workbench view">
            <button className={activeTool === "csv" ? "active" : ""} onClick={() => setActiveTool("csv")} type="button">CSV</button>
            <button className={activeTool === "text" ? "active" : ""} onClick={() => setActiveTool("text")} type="button">Text</button>
          </div>
          <div className="status-pill">FastAPI + React</div>
        </div>
      </header>

      {activeTool === "csv" ? <CsvWorkbench modelStatus={modelStatus} /> : (
      <>
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
            checked={textProviders.presidio}
            disabled={modelStatus?.span_providers?.presidio?.available === false}
            onChange={() => toggleTextProvider("presidio")}
            type="checkbox"
          />
          <span>presidio</span>
        </label>
        {["gliner", "scrubadub"].map((name) => (
          <label className="check" key={name}>
            <input
              checked={textProviders[name]}
              disabled={modelStatus?.span_providers?.[name]?.available === false}
              onChange={() => toggleTextProvider(name)}
              type="checkbox"
            />
            <span>{name}</span>
          </label>
        ))}
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
          runHsdClassifier={runHsdClassifier}
          runModel={runModel}
          setRunHsdClassifier={setRunHsdClassifier}
          setRunModel={setRunModel}
          status={modelStatus}
        />

        <GuidancePanel result={result} status={modelStatus} />
      </section>
      </>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
