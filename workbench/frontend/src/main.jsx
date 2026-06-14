import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  Database,
  Download,
  FileCheck2,
  FileText,
  LayoutDashboard,
  LockKeyhole,
  Play,
  ShieldAlert,
  ShieldCheck,
  Target,
  UploadCloud,
} from "lucide-react";
import "./styles.css";

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

function formatPercentRate(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return `${Math.round(value * 100)}%`;
}

function formatCount(value) {
  if (typeof value !== "number") {
    return "0";
  }
  return value.toLocaleString();
}

function formatScoreValue(value) {
  if (typeof value !== "number") {
    return "n/a";
  }
  return value.toFixed(2);
}

const CATEGORY_LABELS = {
  disability: "Disability",
  gender: "Gender",
  historical_victim_group: "Historical victim group",
  nationality_or_origin: "Nationality / origin",
  race_or_ethnicity: "Race / ethnicity",
  religion: "Religion",
  slur_or_profanity: "Slur / profanity",
  sexual_orientation: "Sexual orientation"
};
const AUTO_DASHBOARD_DISABLED_MODELS = ["semantic", "local_llm"];
const AUTO_PROVIDER_ORDER = ["deterministic", "presidio", "scrubadub", "gliner"];
const AUTO_MODEL_ORDER = ["token_policy_ensemble", "hsd_advisory"];
const PROCESSING_STAGES = [
  {
    after: 0,
    value: 12,
    label: "Checking saved result",
    detail: "Matching this CSV and option set against the local demo cache."
  },
  {
    after: 1.4,
    value: 30,
    label: "Privacy detection",
    detail: "Scanning protected output for identifiers and residual PII."
  },
  {
    after: 4,
    value: 52,
    label: "Candidate selection",
    detail: "Selecting the least destructive masked candidate for each row."
  },
  {
    after: 7,
    value: 74,
    label: "Context checks",
    detail: "Checking HSD cues, target references, and safeguard metrics."
  },
  {
    after: 10,
    value: 90,
    label: "Preparing dashboard",
    detail: "Building review queue, target statistics, and export artifacts."
  }
];
const NAV_ITEMS = [
  {
    id: "dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
    title: "NGO Admin Dashboard",
    eyebrow: "Privacy-preserving review operations"
  },
  {
    id: "review",
    label: "Review queue",
    icon: ShieldAlert,
    title: "Review Queue",
    eyebrow: "Protected human review"
  },
  {
    id: "targets",
    label: "Target groups",
    icon: Target,
    title: "Target Groups",
    eyebrow: "Aggregate platform impact"
  },
  {
    id: "reports",
    label: "Reports",
    icon: Archive,
    title: "Reports",
    eyebrow: "Export and technical audit"
  }
];

function categoryLabel(value) {
  return CATEGORY_LABELS[value] || value.replaceAll("_", " ");
}

function PortalMetric({ icon: Icon, label, value, meta, tone = "default" }) {
  return (
    <section className={`portal-metric ${tone}`}>
      <div className="portal-metric-icon" aria-hidden="true">
        <Icon size={21} />
      </div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <p>{meta}</p>
      </div>
    </section>
  );
}

function TargetImpactPanel({ targetGroups }) {
  const categories = Object.entries(targetGroups?.categories || {})
    .sort(([, left], [, right]) => (right.hatred_rows || 0) - (left.hatred_rows || 0) || (right.rows || 0) - (left.rows || 0))
    .slice(0, 7);
  return (
    <section className="portal-panel">
      <div className="portal-panel-head">
        <div>
          <h2>Target Group Impact</h2>
          <p>Aggregate exposure by protected category.</p>
        </div>
        <Target size={20} />
      </div>
      <div className="impact-list">
        {categories.length ? categories.map(([name, item]) => (
          <div className="impact-row" key={name}>
            <div>
              <strong>{categoryLabel(name)}</strong>
              <span>{formatCount(item.rows)} mentions</span>
            </div>
            <div className="impact-meter" aria-hidden="true">
              <div style={{ width: formatPercentRate(item.hatred_rate || 0) }} />
            </div>
            <div className="impact-rate">
              <strong>{formatPercentRate(item.hatred_rate || 0)}</strong>
              <span>{formatCount(item.hatred_rows)} flagged</span>
            </div>
          </div>
        )) : (
          <div className="empty-state">No target-group statistics yet.</div>
        )}
      </div>
    </section>
  );
}

function ReviewQueuePanel({ ngoReview }) {
  const queue = ngoReview?.queue_preview || [];
  return (
    <section className="portal-panel">
      <div className="portal-panel-head">
        <div>
          <h2>Review Queue</h2>
          <p>Protected cases routed for NGO assessment.</p>
        </div>
        <ShieldAlert size={20} />
      </div>
      {queue.length ? (
        <div className="queue-list">
          {queue.slice(0, 6).map((item) => (
            <article className="queue-item" key={item.row_id}>
              <div className="queue-topline">
                <strong>{item.row_id}</strong>
                <span>{formatScoreValue(item.score)}</span>
              </div>
              <p>{item.protected_preview}</p>
              <Tags values={(item.target_categories || []).map(categoryLabel)} />
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-state">No protected cases are currently queued for NGO review.</div>
      )}
    </section>
  );
}

function PortalViewHeading({ description, icon: Icon, title }) {
  return (
    <section className="view-heading">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <Icon size={22} />
    </section>
  );
}

function countValue(counts, key) {
  return typeof counts?.[key] === "number" ? counts[key] : 0;
}

function percentFromCounts(part, total) {
  if (!total) return "0%";
  return `${Math.round((part / total) * 100)}%`;
}

function statusText(value) {
  return String(value || "unknown").replaceAll("_", " ");
}

function SafeguardOverviewPanel({ result }) {
  const safeguards = result?.platform_insights?.safeguards || {};
  const privacy = result?.platform_insights?.privacy_posture || {};
  const harmCounts = safeguards.harm_risk_counts || {};
  const privacyCounts = safeguards.privacy_status_counts || {};
  const contextCounts = safeguards.context_status_counts || {};
  const reviewRows = safeguards.human_review_required_rows || 0;
  const rowCount = result?.platform_insights?.row_count || result?.manifest?.row_count || 0;
  return (
    <section className="portal-panel safeguard-overview">
      <div className="portal-panel-head">
        <div>
          <h2>Human-Rights Safeguard</h2>
          <p>Derived review controls for harm, privacy, context, and proportionate response.</p>
        </div>
        <ShieldCheck size={20} />
      </div>
      <div className="safeguard-grid">
        <div>
          <span>High harm risk</span>
          <strong>{formatCount(countValue(harmCounts, "high"))}</strong>
          <small>{formatCount(reviewRows)} cases routed to human review</small>
        </div>
        <div>
          <span>Privacy clear</span>
          <strong>{formatCount(countValue(privacyCounts, "clear"))}</strong>
          <small>{formatCount(privacy.rows_with_privacy_warnings || 0)} rows with leakage warnings</small>
        </div>
        <div>
          <span>Context preserved</span>
          <strong>{formatCount(countValue(contextCounts, "preserved"))}</strong>
          <small>{formatCount(rowCount)} rows analyzed</small>
        </div>
        <div>
          <span>Response policy</span>
          <strong>Human</strong>
          <small>No automatic moderation decision</small>
        </div>
      </div>
    </section>
  );
}

function ContextPreservationMeter({ result }) {
  const context = result?.platform_insights?.context_preservation || {};
  const components = context.component_status_counts || {};
  const rows = [
    ["target_group_reference", "Target-group reference"],
    ["harm_signal", "Threat / insult signal"],
    ["quotation_or_counterspeech_context", "Quote / counterspeech context"]
  ];
  return (
    <section className="portal-panel">
      <div className="portal-panel-head">
        <div>
          <h2>Context Preservation Meter</h2>
          <p>Checks whether HSD-relevant context survived masking.</p>
        </div>
        <Target size={20} />
      </div>
      <div className="meter-list">
        {rows.map(([key, label]) => {
          const counts = components[key] || {};
          const preserved = countValue(counts, "preserved");
          const atRisk = countValue(counts, "at_risk");
          const total = preserved + atRisk;
          return (
            <div className="meter-row" key={key}>
              <div>
                <strong>{label}</strong>
                <span>{formatCount(preserved)} preserved / {formatCount(total)} applicable</span>
              </div>
              <div className="impact-meter" aria-hidden="true">
                <div style={{ width: percentFromCounts(preserved, total) }} />
              </div>
              <small>{formatCount(atRisk)} at risk</small>
            </div>
          );
        })}
      </div>
      <div className="context-retention-strip">
        <span><strong>{formatPercentRate(context.target_cue_retention_mean ?? null)}</strong> target cues</span>
        <span><strong>{formatPercentRate(context.utility_cue_retention_mean ?? null)}</strong> HSD signals</span>
        <span><strong>{formatPercentRate(context.character_utility_retention_mean ?? null)}</strong> similarity</span>
      </div>
    </section>
  );
}

function PrivacyLeakagePanel({ result }) {
  if (!result) {
    return (
      <section className="portal-panel leakage-panel">
        <div className="portal-panel-head">
          <div>
            <h2>Privacy Leakage Warning Layer</h2>
            <p>Final scan over protected output before review/export.</p>
          </div>
          <AlertTriangle size={20} />
        </div>
        <div className="empty-state">No CSV processed yet.</div>
      </section>
    );
  }
  const privacy = result?.platform_insights?.privacy_posture || {};
  const statusCounts = privacy.leakage_status_counts || {};
  const entityCounts = privacy.residual_identifier_counts_by_entity_type || {};
  const warningCounts = privacy.privacy_warning_counts || {};
  const status = countValue(statusCounts, "review_required")
    ? "review_required"
    : countValue(statusCounts, "warning")
      ? "warning"
      : "clear";
  return (
    <section className={`portal-panel leakage-panel ${status}`}>
      <div className="portal-panel-head">
        <div>
          <h2>Privacy Leakage Warning Layer</h2>
          <p>Final scan over protected output before review/export.</p>
        </div>
        <AlertTriangle size={20} />
      </div>
      <div className="leakage-status">
        <strong>{status === "clear" ? "Clear" : status === "warning" ? "Warnings" : "Review required"}</strong>
        <span>{formatCount(privacy.residual_identifier_count || 0)} residual identifier signals</span>
      </div>
      <div className="detail-grid compact">
        <div>
          <span>Clear rows</span>
          <strong>{formatCount(countValue(statusCounts, "clear"))}</strong>
        </div>
        <div>
          <span>Warning rows</span>
          <strong>{formatCount(countValue(statusCounts, "warning"))}</strong>
        </div>
        <div>
          <span>Review rows</span>
          <strong>{formatCount(countValue(statusCounts, "review_required"))}</strong>
        </div>
      </div>
      <Tags values={[
        ...Object.entries(entityCounts).map(([name, value]) => `${name}: ${value}`),
        ...Object.entries(warningCounts).map(([name, value]) => `${name}: ${value}`)
      ]} />
    </section>
  );
}

function SafeguardCard({ item }) {
  const safeguard = item?.safeguard || {};
  const context = item?.context_preservation || {};
  const privacy = item?.privacy_leakage || {};
  const rows = [
    ["Harm risk", safeguard.harm_risk?.label || "Not assessed"],
    ["Privacy", privacy.label || safeguard.privacy_status?.label || "Not assessed"],
    ["Context", context.label || safeguard.context_preservation?.label || "Not assessed"],
    ["Human review", safeguard.human_review?.label || "Not routed"],
    ["Response", safeguard.proportionate_response?.label || "Human assessment only"]
  ];
  return (
    <div className="safeguard-card">
      {rows.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function ReviewQueueDetailPanel({ ngoReview }) {
  const queue = ngoReview?.queue_preview || [];
  return (
    <section className="review-detail-list">
      {queue.length ? queue.map((item) => (
        <article className="review-case" key={item.row_id}>
          <div className="review-case-main">
            <div className="queue-topline">
              <strong>{item.row_id}</strong>
              <span>{formatScoreValue(item.score)}</span>
            </div>
            <p>{item.protected_preview}</p>
            <Tags values={[
              ...(item.target_categories || []).map(categoryLabel),
              ...(item.context_tags || []).map(statusText)
            ]} />
            <div className="context-retention-strip">
              <span><strong>{formatPercentRate(item.context_preservation?.retention?.target_cue ?? null)}</strong> target refs</span>
              <span><strong>{formatPercentRate(item.context_preservation?.retention?.utility_cue ?? null)}</strong> HSD signals</span>
              <span><strong>{formatPercentRate(item.context_preservation?.retention?.character ?? null)}</strong> similarity</span>
            </div>
          </div>
          <SafeguardCard item={item} />
        </article>
      )) : (
        <section className="portal-panel">
          <div className="empty-state">No protected cases are currently queued for NGO review.</div>
        </section>
      )}
    </section>
  );
}

function TargetGroupsDetailPanel({ targetGroups }) {
  const categories = Object.entries(targetGroups?.categories || {})
    .sort(([, left], [, right]) => (right.hatred_rows || 0) - (left.hatred_rows || 0) || (right.rows || 0) - (left.rows || 0));
  return (
    <section className="portal-panel">
      <div className="portal-panel-head">
        <div>
          <h2>Target Category Analytics</h2>
          <p>Post-classification hatred by protected target group.</p>
        </div>
        <Target size={20} />
      </div>
      <div className="table-wrap detail-table">
        <table>
          <thead>
            <tr>
              <th>Target category</th>
              <th>Mentions</th>
              <th>Flagged</th>
              <th>Hatred rate</th>
              <th>Cue preservation</th>
              <th>Mean score</th>
            </tr>
          </thead>
          <tbody>
            {categories.map(([name, item]) => (
              <tr key={name}>
                <td>{categoryLabel(name)}</td>
                <td>{formatCount(item.rows)}</td>
                <td>{formatCount(item.hatred_rows)}</td>
                <td>{formatPercentRate(item.hatred_rate || 0)}</td>
                <td>{formatCount(item.target_cue_count_after)} / {formatCount(item.target_cue_count_before)}</td>
                <td>{formatScoreValue(item.mean_hatred_score)}</td>
              </tr>
            ))}
            {!categories.length ? (
              <tr><td className="muted-cell" colSpan="6">No target-group statistics yet.</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ReportSummaryPanel({ result, onDownloadAudit, onDownloadCsv, onDownloadManifest }) {
  const summary = result?.audit?.summary || {};
  const validation = summary.validation || {};
  const manifest = result?.manifest || {};
  return (
    <section className="portal-panel report-summary">
      <div className="portal-panel-head">
        <div>
          <h2>Report Center</h2>
          <p>Export protected artifacts and verify run metadata.</p>
        </div>
        <Archive size={20} />
      </div>
      <div className="report-actions">
        <button className="ghost" disabled={!result} onClick={onDownloadCsv} type="button">
          <Download size={17} />
          Protected CSV
        </button>
        <button className="ghost" disabled={!result} onClick={onDownloadAudit} type="button">
          <Archive size={17} />
          Audit JSON
        </button>
        <button className="ghost" disabled={!result} onClick={onDownloadManifest} type="button">
          <Archive size={17} />
          Manifest
        </button>
      </div>
      <div className="detail-grid">
        <div>
          <span>Rows</span>
          <strong>{formatCount(manifest.row_count || 0)}</strong>
        </div>
        <div>
          <span>Validation</span>
          <strong>{validation.valid ? "Valid" : result ? "Check" : "Waiting"}</strong>
        </div>
        <div>
          <span>Mode</span>
          <strong>{manifest.mode || "auto"}</strong>
        </div>
        <div>
          <span>Cache</span>
          <strong>{result?.cache?.hit ? "Loaded" : result ? "Saved" : "None"}</strong>
        </div>
      </div>
    </section>
  );
}

function NgoDashboard({ result }) {
  const insight = result?.platform_insights || {};
  const classification = insight.classification || {};
  const targetGroups = insight.target_groups || {};
  const ngoReview = insight.ngo_review || {};
  const rowCount = insight.row_count || result?.manifest?.row_count || 0;
  const sourceLabel = classification.source === "pipeline_hsd_advisory"
    ? "HSD advisory model flags"
    : classification.source === "csv_post_classification_columns"
      ? "CSV classification labels"
      : "Awaiting CSV run";

  return (
    <>
      <section className="portal-hero">
        <div>
          <span className="eyebrow">NGO operations portal</span>
          <h1>Platform Review Desk</h1>
          <p>Aggregate hate-speech monitoring, protected case intake, and privacy-preserving review evidence.</p>
        </div>
        <div className="hero-badge">
          <LockKeyhole size={18} />
          <span>Aggregate-only report</span>
        </div>
      </section>

      <section className="portal-metrics" aria-label="NGO review summary">
        <PortalMetric
          icon={FileCheck2}
          label="Cases analyzed"
          meta={`${formatCount(classification.classified_rows || 0)} assessed by ${sourceLabel}`}
          value={formatCount(rowCount)}
        />
        <PortalMetric
          icon={ShieldAlert}
          label="Needs review"
          meta={`${formatPercentRate(ngoReview.queue_rate || 0)} of analyzed cases`}
          tone="attention"
          value={formatCount(ngoReview.queue_rows || 0)}
        />
        <PortalMetric
          icon={Target}
          label="Target-group mentions"
          meta={`${formatPercentRate(targetGroups.target_group_row_rate || 0)} of analyzed cases`}
          tone="neutral"
          value={formatCount(targetGroups.rows_with_target_group || 0)}
        />
        <PortalMetric
          icon={Database}
          label="Raw text retained"
          meta="Insight report stores aggregate counts and protected previews only."
          tone="safe"
          value="0"
        />
      </section>

      <section className="portal-insight-grid">
        <SafeguardOverviewPanel result={result} />
        <ContextPreservationMeter result={result} />
      </section>
    </>
  );
}

function ProcessingProgress({ progress }) {
  if (!progress) return null;
  return (
    <div className="processing-progress" aria-live="polite">
      <div className="progress-topline">
        <strong>{progress.label}</strong>
        <span>{progress.value}%</span>
      </div>
      <div className="progress-track" aria-hidden="true">
        <div style={{ width: `${progress.value}%` }} />
      </div>
      <p>{progress.detail}</p>
    </div>
  );
}

function DataIntakePanel({
  busy,
  cacheBusy,
  cacheNotice,
  csvName,
  csvText,
  headers,
  idCol,
  onFile,
  onIdCol,
  onReplaceText,
  onRunCsv,
  onTextCol,
  progress,
  replaceText,
  textCol
}) {
  return (
    <section className="portal-panel intake-panel">
      <div className="panel-heading">
        <div>
          <h2>Data Intake</h2>
          <p>Upload a platform export for privacy-safe review preparation.</p>
        </div>
        <UploadCloud size={20} />
      </div>
      <label className="file-drop">
        <input accept=".csv,text/csv" onChange={onFile} type="file" />
        <FileText size={20} />
        <span>{csvText ? csvName : "Choose a CSV"}</span>
      </label>
      {cacheNotice || cacheBusy ? (
        <div className={`cache-note ${cacheBusy ? "pending" : ""}`}>
          <Archive size={17} />
          <span>{cacheBusy ? "Checking saved results" : cacheNotice}</span>
        </div>
      ) : null}
      <div className="form-grid">
        <label>
          <span>Text Column</span>
          <select value={textCol} onChange={(event) => onTextCol(event.target.value)}>
            {headers.map((header) => <option key={header} value={header}>{header}</option>)}
          </select>
        </label>
        <label>
          <span>ID Column</span>
          <select value={idCol} onChange={(event) => onIdCol(event.target.value)}>
            <option value="">None</option>
            {headers.map((header) => <option key={header} value={header}>{header}</option>)}
          </select>
        </label>
      </div>
      <div className="auto-mode-note">
        <ShieldCheck size={18} />
        <div>
          <strong>Protected processing</strong>
          <span>PII masking, meaning checks, and HSD preservation run automatically.</span>
        </div>
      </div>
      <label className="check">
        <input checked={replaceText} onChange={(event) => onReplaceText(event.target.checked)} type="checkbox" />
        <span>Replace text column</span>
      </label>
      <button className="primary full-width" disabled={busy || cacheBusy || !csvText || !textCol} onClick={onRunCsv} type="button">
        <Play size={18} />
        {busy ? "Running" : cacheBusy ? "Checking cache" : "Run CSV"}
      </button>
      <ProcessingProgress progress={busy ? progress : null} />
    </section>
  );
}

function ProtectedCasePreviewPanel({ csvGauges, result }) {
  return (
    <section className="portal-panel preview-panel">
      <div className="panel-heading">
        <div>
          <h2>Protected Case Preview</h2>
          <p>Sanitized text for review and export.</p>
        </div>
        <FileCheck2 size={20} />
      </div>
      <div className="quality-strip">
        <span><strong>{csvGauges.privacy}%</strong> privacy gain</span>
        <span><strong>{csvGauges.cue}%</strong> cue retention</span>
        <span><strong>{csvGauges.similarity}%</strong> similarity</span>
        <span><strong>{csvGauges.residual}%</strong> residual risk</span>
      </div>
      <div className="table-wrap csv-preview">
        <table>
          <thead>
            <tr>
              <th>Case</th>
              <th>Protected Preview</th>
            </tr>
          </thead>
          <tbody>
            {(result?.preview_rows || []).map((row) => (
              <tr key={row.row_id}>
                <td>{row.row_id}</td>
                <td>{row.output}</td>
              </tr>
            ))}
            {!result?.preview_rows?.length ? (
              <tr><td className="muted-cell" colSpan="2">No CSV processed</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function orderedStatusItems(items, order, options = {}) {
  const source = items || {};
  const includeDisabled = options.includeDisabled || false;
  return order
    .filter((name) => {
      const status = source[name];
      if (!status) return false;
      const statusText = String(status.status || "");
      if (
        name === "gliner"
        && (statusText.startsWith("disabled") || status.pipeline_role === "explicit_research_only")
      ) {
        return false;
      }
      if (!includeDisabled && statusText.startsWith("disabled")) return false;
      return true;
    })
    .map((name) => [name, source[name]]);
}

function modelStatusFromSummary(modelStatus) {
  const hsd = modelStatus?.hsd_advisory;
  const tokenPolicy = modelStatus?.token_policy_ensemble;
  return {
    token_policy_ensemble: tokenPolicy
      ? {
          status: tokenPolicy.available ? "available" : "missing_artifact",
          ...tokenPolicy
        }
      : undefined,
    hsd_advisory: hsd
      ? {
          status: hsd.available ? "available" : "missing_dependency",
          ...hsd
        }
      : undefined
  };
}

function providerStatusFromSummary(modelStatus) {
  const providers = modelStatus?.span_providers || {};
  return Object.fromEntries(
    AUTO_PROVIDER_ORDER
      .filter((name) => providers[name])
      .map((name) => [
        name,
        {
          status: providers[name].available ? "available" : providers[name].status || "missing_dependency",
          ...providers[name]
        }
      ])
  );
}

function TechnicalAuditStrip({ result, modelStatus, metrics, csvGauges, onDownloadCsv, onDownloadAudit, onDownloadManifest }) {
  const verification = result?.audit?.summary?.stages?.verification || {};
  const providers = result?.manifest?.providers || providerStatusFromSummary(modelStatus);
  const models = result?.manifest?.models || modelStatusFromSummary(modelStatus);
  const providerItems = orderedStatusItems(providers, AUTO_PROVIDER_ORDER);
  const modelItems = orderedStatusItems(models, AUTO_MODEL_ORDER, { includeDisabled: true });
  return (
    <section className="audit-strip" aria-label="Technical audit">
      <div className="audit-summary">
        <div>
          <span>Residual identifiers</span>
          <strong>{formatCount(metrics.residual_identifier_count || 0)}</strong>
        </div>
        <div>
          <span>Cue retention</span>
          <strong>{csvGauges.cue}%</strong>
        </div>
        <div>
          <span>HSD preservation</span>
          <strong>{verification.hsd_advisory_status || "waiting"}</strong>
        </div>
      </div>
      <div className="audit-tags">
        <Tags values={[
          ...providerItems.map(([name, item]) => `${name}: ${item.status || "unknown"}`),
          ...modelItems.map(([name, item]) => `${name}: ${item.status || "unknown"}`)
        ]} />
      </div>
      <div className="audit-actions">
        <button className="ghost" disabled={!result} onClick={onDownloadCsv} type="button">
          <Download size={17} />
          CSV
        </button>
        <button className="ghost" disabled={!result} onClick={onDownloadAudit} type="button">
          <Archive size={17} />
          Audit
        </button>
        <button className="ghost" disabled={!result} onClick={onDownloadManifest} type="button">
          <Archive size={17} />
          Manifest
        </button>
      </div>
    </section>
  );
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

function csvRequestPayload({ csvText, idCol, replaceText, textCol }) {
  return {
    csv_text: csvText,
    text_col: textCol,
    id_col: idCol || null,
    output_col: "privatized_text",
    replace_text: replaceText,
    mode: "auto",
    style_scrub: false,
    disabled_providers: [],
    disabled_models: AUTO_DASHBOARD_DISABLED_MODELS,
    metric_depth: "fast"
  };
}

function CsvWorkbench({ activeView, modelStatus }) {
  const [csvText, setCsvText] = useState("");
  const [csvName, setCsvName] = useState("contextsafe-hsd.csv");
  const [headers, setHeaders] = useState([]);
  const [textCol, setTextCol] = useState("");
  const [idCol, setIdCol] = useState("");
  const [replaceText, setReplaceText] = useState(true);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [cacheBusy, setCacheBusy] = useState(false);
  const [cacheNotice, setCacheNotice] = useState("");
  const [processingProgress, setProcessingProgress] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!busy) {
      return undefined;
    }
    const startedAt = Date.now();
    setProcessingProgress(PROCESSING_STAGES[0]);
    const timer = window.setInterval(() => {
      const elapsed = (Date.now() - startedAt) / 1000;
      const stage = [...PROCESSING_STAGES]
        .reverse()
        .find((item) => elapsed >= item.after) || PROCESSING_STAGES[0];
      const drift = Math.min(8, Math.floor(Math.max(0, elapsed - stage.after) * 2));
      setProcessingProgress({
        ...stage,
        value: Math.min(96, stage.value + drift)
      });
    }, 400);
    return () => window.clearInterval(timer);
  }, [busy]);

  const metrics = result?.audit?.summary?.metrics || {};
  const csvGauges = {
    privacy: Math.round((metrics.privacy_gain_mean || 0) * 100),
    cue: Math.round((metrics.target_cue_retention_mean ?? 1) * 100),
    similarity: Math.round((metrics.character_utility_retention_mean ?? 1) * 100),
    residual: Math.min(100, (metrics.residual_identifier_count || 0) * 10)
  };
  const insight = result?.platform_insights || {};
  const targetGroups = insight.target_groups || {};
  const ngoReview = insight.ngo_review || {};

  const intakePanel = (
    <DataIntakePanel
      busy={busy}
      cacheBusy={cacheBusy}
      cacheNotice={cacheNotice}
      csvName={csvName}
      csvText={csvText}
      headers={headers}
      idCol={idCol}
      onFile={handleFile}
      onIdCol={handleIdColChange}
      onReplaceText={handleReplaceTextChange}
      onRunCsv={runCsv}
      onTextCol={handleTextColChange}
      progress={processingProgress}
      replaceText={replaceText}
      textCol={textCol}
    />
  );
  const previewPanel = <ProtectedCasePreviewPanel csvGauges={csvGauges} result={result} />;
  const downloadCsv = () => {
    if (!result) return;
    downloadTextFile(`masked-${csvName}`, result.output_csv, "text/csv");
  };
  const downloadAudit = () => {
    if (!result) return;
    downloadTextFile("contextsafe-hsd-audit.json", JSON.stringify(result.audit, null, 2), "application/json");
  };
  const downloadManifest = () => {
    if (!result) return;
    downloadTextFile("contextsafe-hsd-manifest.json", JSON.stringify(result.manifest, null, 2), "application/json");
  };

  async function handleFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    event.target.value = "";
    const detected = detectCsvHeaders(text);
    const nextTextCol = preferredColumn(detected, ["text", "tweet", "content", "comment"]);
    const nextIdCol = preferredColumn(detected, ["id", "case_id", "source_id", "author_id", "user_id"], "");
    setCsvText(text);
    setCsvName(file.name || "contextsafe-hsd.csv");
    setHeaders(detected);
    setTextCol(nextTextCol);
    setIdCol(nextIdCol);
    setResult(null);
    setError("");
    if (nextTextCol) {
      await lookupCachedCsv({
        csvTextValue: text,
        idColValue: nextIdCol,
        replaceTextValue: replaceText,
        textColValue: nextTextCol
      });
    } else {
      setCacheNotice("No text column detected. Select a column and run CSV.");
    }
  }

  function handleTextColChange(value) {
    setTextCol(value);
    setResult(null);
    if (csvText && value) {
      void lookupCachedCsv({
        csvTextValue: csvText,
        idColValue: idCol,
        replaceTextValue: replaceText,
        textColValue: value
      });
    } else {
      setCacheNotice("Text column changed. Run CSV to process with these settings.");
    }
  }

  function handleIdColChange(value) {
    setIdCol(value);
    setResult(null);
    if (csvText && textCol) {
      void lookupCachedCsv({
        csvTextValue: csvText,
        idColValue: value,
        replaceTextValue: replaceText,
        textColValue: textCol
      });
    } else {
      setCacheNotice("ID column changed. Run CSV to process with these settings.");
    }
  }

  function handleReplaceTextChange(value) {
    setReplaceText(value);
    setResult(null);
    if (csvText && textCol) {
      void lookupCachedCsv({
        csvTextValue: csvText,
        idColValue: idCol,
        replaceTextValue: value,
        textColValue: textCol
      });
    } else {
      setCacheNotice("Output setting changed. Run CSV to process with these settings.");
    }
  }

  async function lookupCachedCsv({ csvTextValue, idColValue, replaceTextValue, textColValue }) {
    setCacheBusy(true);
    setCacheNotice("");
    try {
      const response = await fetch("/api/csv/cache", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(csvRequestPayload({
          csvText: csvTextValue,
          idCol: idColValue,
          replaceText: replaceTextValue,
          textCol: textColValue
        }))
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Cache lookup failed with ${response.status}`);
      }
      const body = await response.json();
      if (body.cache_hit && body.result) {
        setResult(body.result);
        setCacheNotice("Loaded existing processed result from local demo cache.");
      } else {
        setCacheNotice("No saved result for this CSV and option set yet.");
      }
    } catch (err) {
      setCacheNotice(err.message || "Cache lookup unavailable. Run CSV to process.");
    } finally {
      setCacheBusy(false);
    }
  }

  async function runCsv() {
    setBusy(true);
    setError("");
    setCacheNotice("");
    try {
      const response = await fetch("/api/csv/privatize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(csvRequestPayload({
          csvText,
          idCol,
          replaceText,
          textCol
        }))
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed with ${response.status}`);
      }
      const body = await response.json();
      setProcessingProgress({
        value: 100,
        label: body.cache?.hit ? "Loaded saved result" : "Processing complete",
        detail: body.cache?.hit
          ? "A matching local result was restored without rerunning the pipeline."
          : "The processed result was saved to the local demo cache."
      });
      setResult(body);
      setCacheNotice(
        body.cache?.hit
          ? "Loaded existing processed result from local demo cache."
          : "Processed and saved result to local demo cache."
      );
    } catch (err) {
      setError(err.message || "CSV processing failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {activeView === "dashboard" ? (
        <>
          <NgoDashboard result={result} />
          <section className="portal-workflow">
            {intakePanel}
            {previewPanel}
          </section>
          <TechnicalAuditStrip
            csvGauges={csvGauges}
            metrics={metrics}
            modelStatus={modelStatus}
            onDownloadAudit={downloadAudit}
            onDownloadCsv={downloadCsv}
            onDownloadManifest={downloadManifest}
            result={result}
          />
        </>
      ) : null}

      {activeView === "review" ? (
        <>
          <PortalViewHeading
            description="Case-level safeguard cards for NGO assessment. Protected previews only; no automatic moderation decision."
            icon={ShieldAlert}
            title="Review Queue"
          />
          <section className="portal-focus-grid review-layout">
            <ReviewQueueDetailPanel ngoReview={ngoReview} />
            <div className="side-stack">
              <SafeguardOverviewPanel result={result} />
              <PrivacyLeakagePanel result={result} />
            </div>
          </section>
        </>
      ) : null}

      {activeView === "targets" ? (
        <>
          <PortalViewHeading
            description="Aggregate target-group exposure by protected category, calculated after classification."
            icon={Target}
            title="Target Groups"
          />
          <section className="portal-focus-grid target-layout">
            <TargetGroupsDetailPanel targetGroups={targetGroups} />
            <ContextPreservationMeter result={result} />
          </section>
        </>
      ) : null}

      {activeView === "reports" ? (
        <>
          <PortalViewHeading
            description="Download the protected CSV, audit JSON, and run manifest for the current platform export."
            icon={Archive}
            title="Reports"
          />
          <ReportSummaryPanel
            onDownloadAudit={downloadAudit}
            onDownloadCsv={downloadCsv}
            onDownloadManifest={downloadManifest}
            result={result}
          />
          <TechnicalAuditStrip
            csvGauges={csvGauges}
            metrics={metrics}
            modelStatus={modelStatus}
            onDownloadAudit={downloadAudit}
            onDownloadCsv={downloadCsv}
            onDownloadManifest={downloadManifest}
            result={result}
          />
          <section className="portal-focus-grid">
            <PrivacyLeakagePanel result={result} />
            <ContextPreservationMeter result={result} />
          </section>
        </>
      ) : null}
      {error ? (
        <section className="error-line">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </section>
      ) : null}
    </>
  );
}

function PortalNav({ activeView, className, onSelect }) {
  return (
    <nav className={className}>
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        return (
          <button
            aria-current={activeView === item.id ? "page" : undefined}
            className={activeView === item.id ? "active" : ""}
            key={item.id}
            onClick={() => onSelect(item.id)}
            type="button"
          >
            <Icon size={17} />
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}

function App() {
  const [modelStatus, setModelStatus] = useState(null);
  const [activeView, setActiveView] = useState("dashboard");
  const activeNav = NAV_ITEMS.find((item) => item.id === activeView) || NAV_ITEMS[0];

  useEffect(() => {
    fetch("/api/model-status")
      .then((response) => response.json())
      .then(setModelStatus)
      .catch(() => setModelStatus(null));
  }, []);

  return (
    <main className="app-frame">
      <aside className="portal-sidebar" aria-label="Portal navigation">
        <div className="sidebar-brand">
          <ShieldCheck size={24} />
          <div>
            <strong>ContextSafe-HSD</strong>
            <span>NGO Portal</span>
          </div>
        </div>
        <PortalNav activeView={activeView} className="sidebar-nav" onSelect={setActiveView} />
        <div className="sidebar-status">
          <CheckCircle2 size={17} />
          <span>Local auto pipeline</span>
        </div>
      </aside>
      <section className="portal-shell">
        <header className="portal-topbar">
          <div>
            <span className="eyebrow">{activeNav.eyebrow}</span>
            <h1>{activeNav.title}</h1>
          </div>
          <div className="status-pill">Auto pipeline</div>
        </header>
        <PortalNav activeView={activeView} className="mobile-nav" onSelect={setActiveView} />

        <CsvWorkbench activeView={activeView} modelStatus={modelStatus} />
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
