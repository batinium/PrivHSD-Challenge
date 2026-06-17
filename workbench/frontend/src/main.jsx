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
const AUTO_PROVIDER_ORDER = ["deterministic", "presidio", "scrubadub"];
const AUTO_MODEL_ORDER = ["local_llm"];
const DEFAULT_LOCAL_LLM_ENDPOINT = "http://localhost:1234/v1/chat/completions";
const DEFAULT_LOCAL_LLM_MODEL = "openai/gpt-oss-20b";
const DEFAULT_RESTATEMENT_MODEL = "openai/gpt-oss-20b";
const DEFAULT_SEMANTIC_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2";
const RISK_FILTERS = [
  { id: "all", label: "All" },
  { id: "high", label: "High" },
  { id: "medium", label: "Moderate" },
  { id: "low", label: "Low" }
];
const REVIEW_ACTIONS = [
  { id: "open", label: "Open", icon: FileCheck2 },
  { id: "reviewing", label: "In review", icon: ShieldAlert },
  { id: "escalated", label: "Escalate", icon: AlertTriangle },
  { id: "cleared", label: "Clear", icon: CheckCircle2 }
];
const REVIEW_STATUS_LABELS = {
  open: "Open",
  reviewing: "In review",
  escalated: "Escalated",
  cleared: "Cleared"
};
const EMPTY_REVIEW_LABELS = {
  final_hsd_label: "",
  harm_risk: "",
  masking_quality: "",
  pii_feedback: [],
  context_feedback: [],
  target_categories: []
};
const FINAL_HSD_OPTIONS = [
  ["", "No vote"],
  ["confirmed_hatred", "Hate speech"],
  ["not_hatred", "Not hate speech"],
  ["uncertain", "Unsure"]
];
const HARM_RISK_OPTIONS = [
  ["", "No override"],
  ["high", "High"],
  ["medium", "Moderate"],
  ["low", "Low"]
];
const MASKING_QUALITY_OPTIONS = [
  ["", "Not assessed"],
  ["acceptable", "Acceptable"],
  ["too_much_masking", "Too much masking"],
  ["too_little_masking", "Too little masking"],
  ["uncertain", "Uncertain"]
];
const PII_FEEDBACK_OPTIONS = [
  ["missed_person", "Missed person"],
  ["missed_location", "Missed location"],
  ["missed_contact", "Missed contact"],
  ["missed_identifier", "Missed ID"],
  ["missed_organization", "Missed org"],
  ["overmasked_target_group", "Overmasked target"],
  ["overmasked_context", "Overmasked context"],
  ["placeholder_too_specific", "Placeholder too specific"],
  ["none", "No PII issue"]
];
const CONTEXT_FEEDBACK_OPTIONS = [
  ["target_reference_preserved", "Target preserved"],
  ["target_reference_lost", "Target lost"],
  ["threat_signal_preserved", "Harm signal preserved"],
  ["threat_signal_lost", "Harm signal lost"],
  ["quotation_context_preserved", "Quote context preserved"],
  ["quotation_context_lost", "Quote context lost"],
  ["counterspeech_context_preserved", "Counterspeech preserved"],
  ["counterspeech_context_lost", "Counterspeech lost"],
  ["none", "No context issue"]
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
              <p>{item.citizen_restatement || item.protected_preview}</p>
              <Tags values={[
                ...(item.target_categories || []).map(categoryLabel),
                ...(item.hsd_reasons || []).map(statusText),
                item.pii_suggestion_count ? `${item.pii_suggestion_count} PII cues` : null
              ].filter(Boolean)} />
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

function itemRiskLevel(item) {
  return item?.safeguard?.harm_risk?.level || "low";
}

function reviewStatusFor(decisions, rowId) {
  return decisions?.[rowId]?.status || "open";
}

function reviewLabelsFor(decisions, rowId) {
  return {
    ...EMPTY_REVIEW_LABELS,
    ...(decisions?.[rowId]?.labels || {})
  };
}

function toggleListValue(values, value) {
  const current = Array.isArray(values) ? values : [];
  if (current.includes(value)) {
    return current.filter((item) => item !== value);
  }
  return [...current, value];
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

function PillToggleGroup({ label, onToggle, options, values }) {
  const current = Array.isArray(values) ? values : [];
  return (
    <div className="pill-toggle-group">
      <span>{label}</span>
      <div>
        {options.map(([value, text]) => (
          <button
            className={current.includes(value) ? "active" : ""}
            key={value}
            onClick={() => onToggle(value)}
            type="button"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

function ReviewFeedbackPanel({ labels, onChange }) {
  const targetOptions = Object.entries(CATEGORY_LABELS);
  return (
    <div className="review-feedback">
      <div className="review-feedback-grid">
        <label>
          <span>Citizen vote</span>
          <select
            value={labels.final_hsd_label || ""}
            onChange={(event) => onChange({ final_hsd_label: event.target.value })}
          >
            {FINAL_HSD_OPTIONS.map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Risk override</span>
          <select
            value={labels.harm_risk || ""}
            onChange={(event) => onChange({ harm_risk: event.target.value })}
          >
            {HARM_RISK_OPTIONS.map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Masking quality</span>
          <select
            value={labels.masking_quality || ""}
            onChange={(event) => onChange({ masking_quality: event.target.value })}
          >
            {MASKING_QUALITY_OPTIONS.map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
        </label>
      </div>
      <PillToggleGroup
        label="PII feedback"
        onToggle={(value) => onChange({
          pii_feedback: toggleListValue(labels.pii_feedback, value)
        })}
        options={PII_FEEDBACK_OPTIONS}
        values={labels.pii_feedback}
      />
      <PillToggleGroup
        label="Context feedback"
        onToggle={(value) => onChange({
          context_feedback: toggleListValue(labels.context_feedback, value)
        })}
        options={CONTEXT_FEEDBACK_OPTIONS}
        values={labels.context_feedback}
      />
      <PillToggleGroup
        label="Target correction"
        onToggle={(value) => onChange({
          target_categories: toggleListValue(labels.target_categories, value)
        })}
        options={targetOptions}
        values={labels.target_categories}
      />
    </div>
  );
}

function ReviewQueueDetailPanel({ ngoReview, onReviewCaseChange, reviewDecisions, reviewSaving }) {
  const [riskFilter, setRiskFilter] = useState("all");
  const queue = ngoReview?.queue_items || ngoReview?.queue_preview || [];
  const riskCounts = queue.reduce(
    (counts, item) => {
      const level = itemRiskLevel(item);
      counts.all += 1;
      counts[level] = (counts[level] || 0) + 1;
      return counts;
    },
    { all: 0, high: 0, medium: 0, low: 0 }
  );
  const filteredQueue = riskFilter === "all"
    ? queue
    : queue.filter((item) => itemRiskLevel(item) === riskFilter);
  const reviewCounts = queue.reduce(
    (counts, item) => {
      const status = reviewStatusFor(reviewDecisions, item.row_id);
      counts[status] = (counts[status] || 0) + 1;
      return counts;
    },
    { open: 0, reviewing: 0, escalated: 0, cleared: 0 }
  );
  return (
    <div className="review-detail-column">
      <section className="portal-panel review-controls">
        <div className="review-control-topline">
          <div>
            <h2>Human Review</h2>
            <p>{formatCount(filteredQueue.length)} of {formatCount(queue.length)} routed cases shown.</p>
          </div>
          <div className="review-summary-strip">
            <span><strong>{formatCount(reviewCounts.open || 0)}</strong> open</span>
            <span><strong>{formatCount(reviewCounts.reviewing || 0)}</strong> in review</span>
            <span><strong>{formatCount(reviewCounts.escalated || 0)}</strong> escalated</span>
            <span><strong>{formatCount(reviewCounts.cleared || 0)}</strong> cleared</span>
          </div>
        </div>
        <div className="segmented-control risk-filter" aria-label="Harm risk filter">
          {RISK_FILTERS.map((filter) => (
            <button
              className={riskFilter === filter.id ? "active" : ""}
              key={filter.id}
              onClick={() => setRiskFilter(filter.id)}
              type="button"
            >
              {filter.label}
              <span>{formatCount(riskCounts[filter.id] || 0)}</span>
            </button>
          ))}
        </div>
      </section>
      <section className="review-detail-list">
        {queue.length && filteredQueue.length ? filteredQueue.map((item) => {
          const decision = reviewStatusFor(reviewDecisions, item.row_id);
          const labels = reviewLabelsFor(reviewDecisions, item.row_id);
          return (
            <article className="review-case" key={item.row_id}>
              <div className="review-case-main">
                <div className="queue-topline">
                  <strong>{item.row_id}</strong>
                  <span>{formatScoreValue(item.score)}</span>
                </div>
                <div className="review-meta">
                  <span className={`review-decision ${decision}`}>
                    {REVIEW_STATUS_LABELS[decision] || statusText(decision)}
                  </span>
                  <span>{item.safeguard?.harm_risk?.label || "Low harm signal"}</span>
                </div>
                <div className="citizen-evidence">
                  <span>Citizen Restatement</span>
                  <p>{item.citizen_restatement || item.protected_preview}</p>
                </div>
                {item.protected_preview && item.citizen_restatement ? (
                  <details className="protected-evidence">
                    <summary>Protected text</summary>
                    <p>{item.protected_preview}</p>
                  </details>
                ) : null}
                <Tags values={[
                  ...(item.target_categories || []).map(categoryLabel),
                  ...(item.context_tags || []).map(statusText),
                  ...(item.hsd_reasons || []).map(statusText),
                  item.hsd_backend ? `backend: ${statusText(item.hsd_backend)}` : null,
                  item.pii_suggestion_count ? `${item.pii_suggestion_count} PII suggestions` : null,
                  item.accepted_pii_suggestion_count ? `${item.accepted_pii_suggestion_count} review cues` : null
                ].filter(Boolean)} />
                {item.pii_suggestion_status_counts && Object.keys(item.pii_suggestion_status_counts).length ? (
                  <div className="suggestion-status-strip">
                    {Object.entries(item.pii_suggestion_status_counts).map(([status, count]) => (
                      <span key={status}><strong>{formatCount(count)}</strong> {statusText(status)}</span>
                    ))}
                  </div>
                ) : null}
                <div className="context-retention-strip">
                  <span><strong>{formatPercentRate(item.context_preservation?.retention?.target_cue ?? null)}</strong> target refs</span>
                  <span><strong>{formatPercentRate(item.context_preservation?.retention?.utility_cue ?? null)}</strong> HSD signals</span>
                  <span><strong>{formatPercentRate(item.context_preservation?.retention?.character ?? null)}</strong> similarity</span>
                </div>
                <div className="review-actions" aria-label={`Review actions for ${item.row_id}`}>
                  {REVIEW_ACTIONS.map((action) => {
                    const Icon = action.icon;
                    return (
                      <button
                        className={decision === action.id ? "active" : ""}
                        key={action.id}
                        onClick={() => onReviewCaseChange(item.row_id, { status: action.id })}
                        type="button"
                      >
                        <Icon size={15} />
                        {action.label}
                      </button>
                    );
                  })}
                </div>
                {reviewSaving === item.row_id ? (
                  <div className="review-save-state">Saving review labels...</div>
                ) : null}
                <ReviewFeedbackPanel
                  labels={labels}
                  onChange={(labelPatch) => onReviewCaseChange(item.row_id, {
                    labels: {
                      ...labels,
                      ...labelPatch
                    }
                  })}
                />
              </div>
              <SafeguardCard item={item} />
            </article>
          );
        }) : queue.length ? (
          <section className="portal-panel">
            <div className="empty-state">No routed cases match this risk filter.</div>
          </section>
        ) : (
          <section className="portal-panel">
            <div className="empty-state">No protected cases are currently queued for NGO review.</div>
          </section>
        )}
      </section>
    </div>
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

function ReportSummaryPanel({ result, onDownloadAudit, onDownloadCsv, onDownloadManifest, onDownloadReview }) {
  const summary = result?.audit?.summary || {};
  const validation = summary.validation || {};
  const manifest = result?.manifest || {};
  const classification = manifest.classification || summary.classification || {};
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
          Review CSV
        </button>
        <button className="ghost" disabled={!result} onClick={onDownloadAudit} type="button">
          <Archive size={17} />
          Audit JSON
        </button>
        <button className="ghost" disabled={!result} onClick={onDownloadManifest} type="button">
          <Archive size={17} />
          Manifest
        </button>
        <button className="ghost" disabled={!result} onClick={onDownloadReview} type="button">
          <FileCheck2 size={17} />
          Review Labels
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
      <div className="detail-grid classification-grid">
        <div>
          <span>HSD backend</span>
          <strong>{statusText(classification.backend || "none")}</strong>
        </div>
        <div>
          <span>Parse</span>
          <strong>{classification.parse_count ?? "n/a"}</strong>
        </div>
        <div>
          <span>Fallback</span>
          <strong>{classification.fallback_count ?? 0}</strong>
        </div>
        <div>
          <span>PII cues</span>
          <strong>{Object.values(classification.pii_suggestion_status_counts || {}).reduce((total, value) => total + Number(value || 0), 0)}</strong>
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
  const sourceLabel = classification.source === "csv_post_classification_columns"
      ? "CSV classification labels"
      : classification.source === "local_llm_hsd_review"
        ? "local LLM review"
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
  const value = Math.max(0, Math.min(100, Number(progress.value) || 0));
  const processedRows = Math.max(0, Number(progress.processed_rows) || 0);
  const totalRows = Math.max(0, Number(progress.total_rows) || 0);
  return (
    <div className="processing-progress" aria-live="polite">
      <div className="progress-topline">
        <strong>{progress.label}</strong>
        <span>{value}%</span>
      </div>
      <div className="progress-track" aria-hidden="true">
        <div style={{ width: `${value}%` }} />
      </div>
      <div className="progress-detail">
        <p>{progress.detail}</p>
        {totalRows > 0 ? (
          <span>{processedRows} / {totalRows} rows</span>
        ) : null}
      </div>
      {progress.row_id ? (
        <div className="progress-row">Current case: {progress.row_id}</div>
      ) : null}
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
  hsdBackend,
  idCol,
  savedResults,
  savedResultsBusy,
  localLlmBatchSize,
  localLlmEnablePiiSuggestions,
  localLlmEndpoint,
  localLlmModel,
  localLlmTimeout,
  citizenRestatementEnabled,
  citizenRestatementModel,
  semanticSimilarityEnabled,
  semanticEmbeddingModel,
  onHsdBackend,
  onCitizenRestatementEnabled,
  onCitizenRestatementModel,
  onFile,
  onIdCol,
  onLoadSavedResult,
  onLocalLlmBatchSize,
  onLocalLlmEnablePiiSuggestions,
  onLocalLlmEndpoint,
  onLocalLlmModel,
  onLocalLlmTimeout,
  onSemanticSimilarityEnabled,
  onSemanticEmbeddingModel,
  onSavedResults,
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
      <div className="saved-results-control">
        <button className="ghost" disabled={savedResultsBusy} onClick={onSavedResults} type="button">
          <Archive size={17} />
          {savedResultsBusy ? "Loading saved" : "Saved results"}
        </button>
        {savedResults?.length ? (
          <div className="saved-results-list">
            {savedResults.slice(0, 5).map((item) => (
              <button
                className="saved-result-item"
                key={item.cache_key}
                onClick={() => onLoadSavedResult(item.cache_key)}
                type="button"
              >
                <span>{formatCount(item.row_count || 0)} rows</span>
                <strong>{item.local_llm_model || statusText(item.hsd_classification_backend || "none")}</strong>
                <small>{formatCount(item.review_queue_rows || 0)} review cases</small>
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <div className="form-grid">
        <label>
          <span>Text Column</span>
          <select value={textCol} onChange={(event) => onTextCol(event.target.value)}>
            {headers.map((header) => <option key={header} value={header}>{header}</option>)}
          </select>
        </label>
        <label>
          <span>Case Key</span>
          <select value={idCol} onChange={(event) => onIdCol(event.target.value)}>
            <option value="">None - generate private case IDs</option>
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
      <div className="backend-control">
        <span>HSD Review Backend</span>
        <div className="segmented-control backend-selector">
          <button className={hsdBackend === "local_llm" ? "active" : ""} onClick={() => onHsdBackend("local_llm")} type="button">
            Local LLM
          </button>
        </div>
      </div>
      {hsdBackend === "local_llm" ? (
        <div className="llm-options">
          <div className="form-grid">
            <label>
              <span>Endpoint</span>
              <input value={localLlmEndpoint} onChange={(event) => onLocalLlmEndpoint(event.target.value)} />
            </label>
            <label>
              <span>Model</span>
              <input value={localLlmModel} onChange={(event) => onLocalLlmModel(event.target.value)} />
            </label>
            <label>
              <span>Batch Size</span>
              <input min="1" type="number" value={localLlmBatchSize} onChange={(event) => onLocalLlmBatchSize(event.target.value)} />
            </label>
            <label>
              <span>Timeout Seconds</span>
              <input min="1" type="number" value={localLlmTimeout} onChange={(event) => onLocalLlmTimeout(event.target.value)} />
            </label>
          </div>
          <label className="check">
            <input checked={localLlmEnablePiiSuggestions} onChange={(event) => onLocalLlmEnablePiiSuggestions(event.target.checked)} type="checkbox" />
            <span>Capture residual PII suggestions for review metadata</span>
          </label>
          <label className="check">
            <input checked={citizenRestatementEnabled} onChange={(event) => onCitizenRestatementEnabled(event.target.checked)} type="checkbox" />
            <span>Generate LLM citizen restatements from protected text</span>
          </label>
          {citizenRestatementEnabled ? (
            <div className="form-grid">
              <label>
                <span>Restatement Model</span>
                <input value={citizenRestatementModel} onChange={(event) => onCitizenRestatementModel(event.target.value)} />
              </label>
              <label>
                <span>Embedding Model</span>
                <input value={semanticEmbeddingModel} onChange={(event) => onSemanticEmbeddingModel(event.target.value)} />
              </label>
            </div>
          ) : null}
          <label className="check">
            <input checked={semanticSimilarityEnabled} disabled={!citizenRestatementEnabled} onChange={(event) => onSemanticSimilarityEnabled(event.target.checked)} type="checkbox" />
            <span>Compare original and restatement with embeddings</span>
          </label>
        </div>
      ) : null}
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
      if (!includeDisabled && statusText.startsWith("disabled")) return false;
      return true;
    })
    .map((name) => [name, source[name]]);
}

function modelStatusFromSummary(modelStatus) {
  const localLlm = modelStatus?.local_llm;
  return {
    local_llm: localLlm
      ? {
          status: localLlm.status || "disabled_until_selected",
          ...localLlm
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
  const classification = result?.manifest?.classification || result?.audit?.summary?.classification || verification.hsd_classification || {};
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
          <span>HSD classification</span>
          <strong>{classification.status || verification.local_llm_hsd_review?.status || "waiting"}</strong>
        </div>
      </div>
      <div className="audit-tags">
        <Tags values={[
          classification.backend ? `classification: ${statusText(classification.backend)}` : null,
          classification.model_id ? `model: ${classification.model_id}` : null,
          classification.parse_count !== undefined ? `parsed: ${classification.parse_count}` : null,
          ...providerItems.map(([name, item]) => `${name}: ${item.status || "unknown"}`),
          ...modelItems.map(([name, item]) => `${name}: ${item.status || "unknown"}`)
        ].filter(Boolean)} />
      </div>
      <div className="audit-actions">
        <button className="ghost" disabled={!result} onClick={onDownloadCsv} type="button">
          <Download size={17} />
          Review CSV
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

const PRIVACY_SAFE_CASE_KEY_COLUMNS = [
  "case_fingerprint",
  "comment_fingerprint",
  "row_fingerprint",
  "fingerprint",
  "case_hash",
  "comment_hash",
  "row_hash",
  "hash",
  "digest",
  "case_key",
  "comment_key",
  "row_key",
  "review_key"
];

function downloadTextFile(name, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function csvRequestPayload({
  csvText,
  hsdBackend,
  idCol,
  localLlmBatchSize,
  localLlmEnablePiiSuggestions,
  localLlmEndpoint,
  localLlmModel,
  localLlmTimeout,
  citizenRestatementEnabled,
  citizenRestatementModel,
  semanticSimilarityEnabled,
  semanticEmbeddingModel,
  replaceText,
  textCol
}) {
  return {
    csv_text: csvText,
    text_col: textCol,
    id_col: idCol || null,
    output_col: "privatized_text",
    replace_text: replaceText,
    mode: "auto",
    style_scrub: false,
    disabled_providers: [],
    disabled_models: ["local_llm"],
    metric_depth: "fast",
    hsd_classification_backend: hsdBackend,
    local_llm_endpoint: localLlmEndpoint,
    local_llm_model: localLlmModel,
    local_llm_timeout_seconds: Number(localLlmTimeout) || 120,
    local_llm_batch_size: Number(localLlmBatchSize) || 10,
    local_llm_enable_pii_suggestions: Boolean(localLlmEnablePiiSuggestions),
    citizen_restatement_backend: citizenRestatementEnabled ? "local_llm" : "off",
    citizen_restatement_model: citizenRestatementModel || localLlmModel,
    citizen_restatement_batch_size: Number(localLlmBatchSize) || 10,
    citizen_restatement_timeout_seconds: Number(localLlmTimeout) || 120,
    semantic_similarity_backend: semanticSimilarityEnabled ? "sentence_transformers" : "off",
    semantic_embedding_model: semanticEmbeddingModel || DEFAULT_SEMANTIC_EMBEDDING_MODEL
  };
}

function CsvWorkbench({ activeView, modelStatus }) {
  const [csvText, setCsvText] = useState("");
  const [csvName, setCsvName] = useState("contextsafe-hsd.csv");
  const [headers, setHeaders] = useState([]);
  const [textCol, setTextCol] = useState("");
  const [idCol, setIdCol] = useState("");
  const [replaceText, setReplaceText] = useState(true);
  const [hsdBackend, setHsdBackend] = useState("local_llm");
  const [localLlmEndpoint, setLocalLlmEndpoint] = useState(DEFAULT_LOCAL_LLM_ENDPOINT);
  const [localLlmModel, setLocalLlmModel] = useState(DEFAULT_LOCAL_LLM_MODEL);
  const [localLlmBatchSize, setLocalLlmBatchSize] = useState("10");
  const [localLlmTimeout, setLocalLlmTimeout] = useState("120");
  const [localLlmEnablePiiSuggestions, setLocalLlmEnablePiiSuggestions] = useState(true);
  const [citizenRestatementEnabled, setCitizenRestatementEnabled] = useState(true);
  const [citizenRestatementModel, setCitizenRestatementModel] = useState(DEFAULT_RESTATEMENT_MODEL);
  const [semanticSimilarityEnabled, setSemanticSimilarityEnabled] = useState(true);
  const [semanticEmbeddingModel, setSemanticEmbeddingModel] = useState(DEFAULT_SEMANTIC_EMBEDDING_MODEL);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [cacheBusy, setCacheBusy] = useState(false);
  const [cacheNotice, setCacheNotice] = useState("");
  const [savedResults, setSavedResults] = useState([]);
  const [savedResultsBusy, setSavedResultsBusy] = useState(false);
  const [processingProgress, setProcessingProgress] = useState(null);
  const [error, setError] = useState("");
  const [reviewDecisions, setReviewDecisions] = useState({});
  const [reviewSaving, setReviewSaving] = useState("");
  const reviewCacheKey = result?.cache?.key || "";

  useEffect(() => {
    let cancelled = false;
    if (!reviewCacheKey) {
      setReviewDecisions({});
      return undefined;
    }
    fetch(`/api/reviews/${reviewCacheKey}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Review lookup failed with ${response.status}`);
        }
        return response.json();
      })
      .then((body) => {
        if (!cancelled) {
          setReviewDecisions(body.cases || {});
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setReviewDecisions({});
          setError(err.message || "Review annotations unavailable");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reviewCacheKey]);

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
      hsdBackend={hsdBackend}
      idCol={idCol}
      savedResults={savedResults}
      savedResultsBusy={savedResultsBusy}
      localLlmBatchSize={localLlmBatchSize}
      localLlmEnablePiiSuggestions={localLlmEnablePiiSuggestions}
      localLlmEndpoint={localLlmEndpoint}
      localLlmModel={localLlmModel}
      localLlmTimeout={localLlmTimeout}
      citizenRestatementEnabled={citizenRestatementEnabled}
      citizenRestatementModel={citizenRestatementModel}
      semanticSimilarityEnabled={semanticSimilarityEnabled}
      semanticEmbeddingModel={semanticEmbeddingModel}
      onHsdBackend={handleHsdBackendChange}
      onCitizenRestatementEnabled={handleCitizenRestatementEnabledChange}
      onCitizenRestatementModel={handleCitizenRestatementModelChange}
      onFile={handleFile}
      onIdCol={handleIdColChange}
      onLoadSavedResult={loadSavedResult}
      onLocalLlmBatchSize={handleLocalLlmBatchSizeChange}
      onLocalLlmEnablePiiSuggestions={handleLocalLlmPiiSuggestionChange}
      onLocalLlmEndpoint={handleLocalLlmEndpointChange}
      onLocalLlmModel={handleLocalLlmModelChange}
      onLocalLlmTimeout={handleLocalLlmTimeoutChange}
      onSemanticSimilarityEnabled={handleSemanticSimilarityEnabledChange}
      onSemanticEmbeddingModel={handleSemanticEmbeddingModelChange}
      onSavedResults={loadSavedResults}
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
    downloadTextFile(`review-${csvName}`, result.review_csv || result.output_csv, "text/csv");
  };
  const downloadAudit = () => {
    if (!result) return;
    downloadTextFile("contextsafe-hsd-audit.json", JSON.stringify(result.audit, null, 2), "application/json");
  };
  const downloadManifest = () => {
    if (!result) return;
    downloadTextFile("contextsafe-hsd-manifest.json", JSON.stringify(result.manifest, null, 2), "application/json");
  };
  const downloadReview = () => {
    if (!result) return;
    downloadTextFile(
      "contextsafe-hsd-review-labels.json",
      JSON.stringify({
        artifact_type: "workbench_review_export",
        cache_key: reviewCacheKey,
        exported_at: new Date().toISOString(),
        privacy: {
          raw_text_retained: false,
          structured_feedback_only: true
        },
        cases: reviewDecisions
      }, null, 2),
      "application/json"
    );
  };
  const updateReviewCase = async (rowId, patch) => {
    if (!reviewCacheKey) {
      setError("Run or load a processed CSV before saving review labels.");
      return;
    }
    const previousCase = reviewDecisions[rowId] || {
      status: "open",
      labels: EMPTY_REVIEW_LABELS
    };
    const nextCase = {
      ...previousCase,
      status: patch.status || previousCase.status || "open",
      labels: {
        ...EMPTY_REVIEW_LABELS,
        ...(previousCase.labels || {}),
        ...(patch.labels || {})
      }
    };
    setReviewDecisions((previous) => ({
      ...previous,
      [rowId]: {
        ...nextCase,
        row_id: rowId,
        updated_at: new Date().toISOString()
      }
    }));
    setReviewSaving(rowId);
    setError("");
    try {
      const response = await fetch(
        `/api/reviews/${reviewCacheKey}/cases/${encodeURIComponent(rowId)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            status: nextCase.status,
            labels: nextCase.labels,
            reviewer_id: "local-reviewer"
          })
        }
      );
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Review save failed with ${response.status}`);
      }
      const body = await response.json();
      setReviewDecisions(body.cases || {});
    } catch (err) {
      setReviewDecisions((previous) => ({
        ...previous,
        [rowId]: previousCase
      }));
      setError(err.message || "Review save failed");
    } finally {
      setReviewSaving("");
    }
  };

  function refreshCachedCsv(optionOverrides = {}) {
    setResult(null);
    setProcessingProgress(null);
    if (csvText && textCol) {
      void lookupCachedCsv({
        csvTextValue: csvText,
        idColValue: idCol,
        replaceTextValue: replaceText,
        textColValue: textCol,
        optionOverrides
      });
    } else {
      setCacheNotice("HSD backend setting changed. Run CSV to process with these settings.");
    }
  }

  function handleHsdBackendChange(value) {
    setHsdBackend(value);
    refreshCachedCsv({ hsdBackend: value });
  }

  function handleLocalLlmEndpointChange(value) {
    setLocalLlmEndpoint(value);
    refreshCachedCsv({ localLlmEndpoint: value });
  }

  function handleLocalLlmModelChange(value) {
    setLocalLlmModel(value);
    refreshCachedCsv({ localLlmModel: value });
  }

  function handleLocalLlmBatchSizeChange(value) {
    setLocalLlmBatchSize(value);
    refreshCachedCsv({ localLlmBatchSize: value });
  }

  function handleLocalLlmTimeoutChange(value) {
    setLocalLlmTimeout(value);
    refreshCachedCsv({ localLlmTimeout: value });
  }

  function handleLocalLlmPiiSuggestionChange(value) {
    setLocalLlmEnablePiiSuggestions(value);
    refreshCachedCsv({ localLlmEnablePiiSuggestions: value });
  }

  function handleCitizenRestatementEnabledChange(value) {
    setCitizenRestatementEnabled(value);
    refreshCachedCsv({ citizenRestatementEnabled: value });
  }

  function handleCitizenRestatementModelChange(value) {
    setCitizenRestatementModel(value);
    refreshCachedCsv({ citizenRestatementModel: value });
  }

  function handleSemanticSimilarityEnabledChange(value) {
    setSemanticSimilarityEnabled(value);
    refreshCachedCsv({ semanticSimilarityEnabled: value });
  }

  function handleSemanticEmbeddingModelChange(value) {
    setSemanticEmbeddingModel(value);
    refreshCachedCsv({ semanticEmbeddingModel: value });
  }

  async function handleFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    event.target.value = "";
    const detected = detectCsvHeaders(text);
    const nextTextCol = preferredColumn(detected, ["text", "tweet", "content", "comment"]);
    const nextIdCol = preferredColumn(detected, PRIVACY_SAFE_CASE_KEY_COLUMNS, "");
    setCsvText(text);
    setCsvName(file.name || "contextsafe-hsd.csv");
    setHeaders(detected);
    setTextCol(nextTextCol);
    setIdCol(nextIdCol);
    setResult(null);
    setProcessingProgress(null);
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
    setProcessingProgress(null);
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
    setProcessingProgress(null);
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
    setProcessingProgress(null);
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

  async function lookupCachedCsv({
    csvTextValue,
    idColValue,
    optionOverrides = {},
    replaceTextValue,
    textColValue
  }) {
    setCacheBusy(true);
    setCacheNotice("");
    const options = {
      hsdBackend,
      localLlmBatchSize,
      localLlmEnablePiiSuggestions,
      localLlmEndpoint,
      localLlmModel,
      localLlmTimeout,
      citizenRestatementEnabled,
      citizenRestatementModel,
      semanticSimilarityEnabled,
      semanticEmbeddingModel,
      ...optionOverrides
    };
    try {
      const response = await fetch("/api/csv/cache", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(csvRequestPayload({
          csvText: csvTextValue,
          hsdBackend: options.hsdBackend,
          idCol: idColValue,
          localLlmBatchSize: options.localLlmBatchSize,
          localLlmEnablePiiSuggestions: options.localLlmEnablePiiSuggestions,
          localLlmEndpoint: options.localLlmEndpoint,
          localLlmModel: options.localLlmModel,
          localLlmTimeout: options.localLlmTimeout,
          citizenRestatementEnabled: options.citizenRestatementEnabled,
          citizenRestatementModel: options.citizenRestatementModel,
          semanticSimilarityEnabled: options.semanticSimilarityEnabled,
          semanticEmbeddingModel: options.semanticEmbeddingModel,
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

  async function loadSavedResults() {
    setSavedResultsBusy(true);
    setError("");
    try {
      const response = await fetch("/api/csv/cache/recent?limit=25");
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Saved result lookup failed with ${response.status}`);
      }
      const body = await response.json();
      setSavedResults(body.items || []);
      setCacheNotice(
        body.items?.length
          ? "Saved results loaded from local demo cache."
          : "No saved processed results found yet."
      );
    } catch (err) {
      setSavedResults([]);
      setError(err.message || "Saved result lookup failed");
    } finally {
      setSavedResultsBusy(false);
    }
  }

  async function loadSavedResult(cacheKey) {
    if (!cacheKey) return;
    setSavedResultsBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/csv/cache/${encodeURIComponent(cacheKey)}`);
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Saved result load failed with ${response.status}`);
      }
      const body = await response.json();
      setResult(body);
      setProcessingProgress(null);
      setCacheNotice("Loaded processed result from local demo cache.");
    } catch (err) {
      setError(err.message || "Saved result load failed");
    } finally {
      setSavedResultsBusy(false);
    }
  }

  async function runCsv() {
    setBusy(true);
    setError("");
    setCacheNotice("");
    setProcessingProgress({
      value: 0,
      label: "Queued",
      detail: "Submitting CSV job to the local pipeline.",
      processed_rows: 0,
      total_rows: 0
    });
    try {
      const startResponse = await fetch("/api/csv/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(csvRequestPayload({
          csvText,
          hsdBackend,
          idCol,
          localLlmBatchSize,
          localLlmEnablePiiSuggestions,
          localLlmEndpoint,
          localLlmModel,
          localLlmTimeout,
          citizenRestatementEnabled,
          citizenRestatementModel,
          semanticSimilarityEnabled,
          semanticEmbeddingModel,
          replaceText,
          textCol
        }))
      });
      if (!startResponse.ok) {
        const body = await startResponse.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed with ${startResponse.status}`);
      }
      let job = await startResponse.json();
      if (job.progress) {
        setProcessingProgress(job.progress);
      }
      while (job.status !== "complete") {
        if (job.status === "failed") {
          throw new Error(job.error?.message || "CSV processing failed");
        }
        await delay(500);
        const statusResponse = await fetch(`/api/csv/jobs/${job.job_id}`);
        if (!statusResponse.ok) {
          const body = await statusResponse.json().catch(() => ({}));
          throw new Error(body.detail || `Progress lookup failed with ${statusResponse.status}`);
        }
        job = await statusResponse.json();
        if (job.progress) {
          setProcessingProgress(job.progress);
        }
      }
      const body = job.result;
      if (!body) {
        throw new Error("CSV job completed without returning a result.");
      }
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
            <ReviewQueueDetailPanel
              ngoReview={ngoReview}
              onReviewCaseChange={updateReviewCase}
              reviewDecisions={reviewDecisions}
              reviewSaving={reviewSaving}
            />
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
            onDownloadReview={downloadReview}
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
