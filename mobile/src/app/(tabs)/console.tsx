import { useEffect, useMemo, useState } from 'react';
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';

import { GlimoShieldBackground } from '@/components/glimo-shield-background';
import { AppColors } from '@/constants/theme';
import {
  AdminDisposition,
  AdminCaseItem,
  adminCaseItems,
  frozenBatch,
  restatementModels,
} from '@/data/review-data';
import { guardRestatement, summarizeGuard } from '@/utils/privacy';

const API_BASE_URL = 'http://127.0.0.1:8765';

const pipelineSteps = [
  {
    label: 'CSV intake',
    detail: 'Admin upload or API batch accepted',
  },
  {
    label: 'DeHateBERT tokens',
    detail: 'Token importance CSV loaded or generated',
  },
  {
    label: 'PII scrub',
    detail: 'Original text preserved for admin-only lookup',
  },
  {
    label: 'HS classification',
    detail: 'Sidecar label and confidence attached',
  },
  {
    label: 'LLM restatement',
    detail: 'Qwen descriptive restatements written',
  },
  {
    label: 'Deviation audit',
    detail: 'Source-to-restatement drift scored',
  },
  {
    label: 'Citizen review',
    detail: 'Only guarded restatements enter the deck',
  },
  {
    label: 'Admin triage',
    detail: 'Approve, lookup, hold, or route to training',
  },
];

const dispositionOptions: AdminDisposition[] = ['approved', 'lookup', 'train', 'hold'];

type UploadedCsv = {
  id: string;
  filename: string;
  originalFilename: string;
  rowCount: number;
  columns: string[];
  updatedAt: string;
};

type AdminJob = {
  id: string;
  uploadId: string;
  filename: string;
  status: 'created' | 'queued' | 'running' | 'complete' | 'failed';
  stage: string;
  error?: string;
  updatedAt: string;
  progress?: {
    processed?: number;
    total?: number;
    detail?: string;
  };
  options?: {
    textCol?: string;
    idCol?: string;
    labelCol?: string;
    restatementModel?: string;
  };
};

export default function AdminDashboard() {
  const [selectedModel, setSelectedModel] =
    useState<(typeof restatementModels)[number]>(restatementModels[0]);
  const [guardStrict, setGuardStrict] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState(adminCaseItems[0]?.id ?? '');
  const [caseItems, setCaseItems] = useState<AdminCaseItem[]>(adminCaseItems);
  const [dispositions, setDispositions] = useState<Record<string, AdminDisposition>>(() =>
    Object.fromEntries(adminCaseItems.map((item) => [item.id, item.adminDisposition])),
  );
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [activeUpload, setActiveUpload] = useState<UploadedCsv | null>(null);
  const [uploads, setUploads] = useState<UploadedCsv[]>([]);
  const [jobs, setJobs] = useState<AdminJob[]>([]);
  const [activeJob, setActiveJob] = useState<AdminJob | null>(null);
  const [activeBundle, setActiveBundle] = useState<Record<string, any> | null>(null);
  const [apiMessage, setApiMessage] = useState('Connect the local API on port 8765.');
  const [isUploading, setIsUploading] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [textCol, setTextCol] = useState('text');
  const [idCol, setIdCol] = useState('ID');
  const [labelCol, setLabelCol] = useState('hs');
  const { width } = useWindowDimensions();
  const isWide = width >= 900;

  const selectedCase =
    caseItems.find((item) => item.id === selectedCaseId) ?? caseItems[0];

  const guardSummary = useMemo(() => {
    return caseItems.reduce(
      (summary, item) => {
        const result = guardRestatement(item.restatement);
        return {
          clean: summary.clean + (result.findings.length === 0 ? 1 : 0),
          flagged: summary.flagged + (result.findings.length > 0 ? 1 : 0),
        };
      },
      { clean: 0, flagged: 0 },
    );
  }, [caseItems]);

  const riskSummary = useMemo(() => {
    return caseItems.reduce(
      (summary, item) => {
        const risk = item.deviationRisk;
        return {
          ...summary,
          [risk]: (summary[risk] ?? 0) + 1,
        };
      },
      {} as Record<string, number>,
    );
  }, [caseItems]);

  const hateRows = caseItems.filter((item) => item.classifierLabel === 'hate').length;
  const selectedGuard = selectedCase ? guardRestatement(selectedCase.restatement) : undefined;
  const currentDisposition = selectedCase
    ? dispositions[selectedCase.id] ?? selectedCase.adminDisposition
    : 'review';
  const activeOutputs = activeBundle?.bundle?.outputs ?? {};
  const rowCount = activeUpload?.rowCount ?? activeBundle?.protectedCsv?.row_count ?? frozenBatch.rows;
  const liveDataLoaded = caseItems !== adminCaseItems;

  useEffect(() => {
    refreshPersistentState();
    // The initial refresh intentionally runs once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!activeJob || !['queued', 'running'].includes(activeJob.status)) {
      return;
    }
    const timer = setInterval(() => {
      refreshJob(activeJob.id);
    }, 2500);
    return () => clearInterval(timer);
    // Polling should follow the active job identity/status only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJob?.id, activeJob?.status]);

  function setDisposition(value: AdminDisposition) {
    if (!selectedCase) {
      return;
    }
    setDispositions((current) => ({ ...current, [selectedCase.id]: value }));
  }

  async function refreshPersistentState() {
    try {
      const [uploadPayload, jobPayload] = await Promise.all([
        requestJson<{ uploads: UploadedCsv[] }>('/api/admin/uploads'),
        requestJson<{ jobs: AdminJob[] }>('/api/admin/jobs'),
      ]);
      setUploads(uploadPayload.uploads);
      setJobs(jobPayload.jobs);
      setApiMessage('Local API connected.');
      const latestComplete = jobPayload.jobs.find((job) => job.status === 'complete');
      if (latestComplete && !activeJob) {
        await loadJob(latestComplete);
      }
    } catch (error) {
      setApiMessage(errorMessage(error));
    }
  }

  function chooseCsvFile() {
    if (Platform.OS !== 'web' || typeof document === 'undefined') {
      setApiMessage('CSV file picker is currently available in the web console.');
      return;
    }
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv,text/csv';
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) {
        return;
      }
      setSelectedFile(file);
      setActiveUpload(null);
      setApiMessage(`Selected ${file.name}.`);
    };
    input.click();
  }

  async function uploadSelectedCsv(): Promise<UploadedCsv | null> {
    if (!selectedFile) {
      setApiMessage('Choose a CSV file first.');
      return null;
    }
    setIsUploading(true);
    try {
      const content = await selectedFile.text();
      const payload = await requestJson<{ upload: UploadedCsv }>('/api/admin/uploads', {
        method: 'POST',
        body: JSON.stringify({
          filename: selectedFile.name,
          content,
        }),
      });
      setActiveUpload(payload.upload);
      setUploads((current) => upsertById(current, payload.upload));
      applyDetectedColumns(payload.upload.columns);
      setApiMessage(`Uploaded ${payload.upload.filename}.`);
      return payload.upload;
    } catch (error) {
      setApiMessage(errorMessage(error));
      return null;
    } finally {
      setIsUploading(false);
    }
  }

  async function startProcessing() {
    setIsStarting(true);
    try {
      const upload = activeUpload ?? (await uploadSelectedCsv());
      if (!upload) {
        return;
      }
      const payload = await requestJson<{ job: AdminJob }>('/api/admin/jobs', {
        method: 'POST',
        body: JSON.stringify({
          uploadId: upload.id,
          textCol,
          idCol,
          labelCol,
          restatementModel: backendRestatementModel(selectedModel),
          finalScrub: guardStrict,
        }),
      });
      setActiveJob(payload.job);
      setJobs((current) => upsertById(current, payload.job));
      setApiMessage(`Processing ${payload.job.status}: ${payload.job.stage}.`);
      if (payload.job.status === 'complete') {
        await loadJob(payload.job);
      }
    } catch (error) {
      setApiMessage(errorMessage(error));
    } finally {
      setIsStarting(false);
    }
  }

  async function refreshJob(jobId: string) {
    try {
      const payload = await requestJson<{ job: AdminJob }>(`/api/admin/jobs/${jobId}`);
      setActiveJob(payload.job);
      setJobs((current) => upsertById(current, payload.job));
      setApiMessage(`Processing ${payload.job.status}: ${payload.job.stage}.`);
      if (payload.job.status === 'complete') {
        await loadJob(payload.job);
      }
      if (payload.job.status === 'failed') {
        setApiMessage(payload.job.error || 'Processing failed.');
      }
    } catch (error) {
      setApiMessage(errorMessage(error));
    }
  }

  async function loadJob(job: AdminJob) {
    try {
      const [casesPayload, bundlePayload] = await Promise.all([
        requestJson<{ items: any[] }>(`/api/admin/jobs/${job.id}/cases`),
        requestJson<Record<string, any>>(`/api/admin/jobs/${job.id}/bundle`),
      ]);
      const normalizedCases = casesPayload.items.map(normalizeAdminCase);
      setCaseItems(normalizedCases.length > 0 ? normalizedCases : adminCaseItems);
      setActiveBundle(bundlePayload);
      setActiveJob(job);
      setDispositions(
        Object.fromEntries(
          normalizedCases.map((item) => [item.id, item.adminDisposition]),
        ),
      );
      setApiMessage(`Loaded ${job.filename}.`);
    } catch (error) {
      setApiMessage(errorMessage(error));
    }
  }

  function applyDetectedColumns(columns: string[]) {
    setTextCol(preferredColumn(columns, ['text', 'comment', 'body', 'content'], textCol));
    setIdCol(preferredColumn(columns, ['ID', 'id', 'row_id'], idCol));
    setLabelCol(preferredColumn(columns, ['hs', 'label', 'hate', 'class'], labelCol));
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <GlimoShieldBackground />
      <ScrollView contentContainerStyle={styles.page} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <View style={styles.brandLockup}>
            <Image
              source={require('@/assets/glimo_mascot_text_below.png')}
              style={styles.brandMark}
              contentFit="contain"
            />
            <View style={styles.headerText}>
              <Text style={styles.eyebrow}>Backend MVP</Text>
              <Text style={styles.title}>Admin review console</Text>
            </View>
          </View>
          <View style={styles.statusPill}>
            <View style={styles.statusDot} />
            <Text style={styles.statusText}>{frozenBatch.validationStatus}</Text>
          </View>
        </View>

        <View style={[styles.metricsGrid, isWide && styles.metricsGridWide]}>
          <Metric label="Rows" value={String(rowCount)} tone="blue" />
          <Metric label="Changed text" value={String(frozenBatch.changedTextCells)} tone="mint" />
          <Metric
            label="Deviation queue"
            value={`${(riskSummary.high ?? 0) + (riskSummary.medium ?? 0)} flagged`}
            tone="amber"
          />
          <Metric
            label="Citizen queue"
            value={`${caseItems.length} ${liveDataLoaded ? 'loaded' : 'seeded'}`}
            tone="coral"
          />
        </View>

        <View style={styles.panel}>
          <View style={styles.uploadHeader}>
            <View style={styles.uploadHeaderText}>
              <Text style={styles.panelTitle}>CSV intake</Text>
              <Text style={styles.panelCopy}>
                Upload a labeled CSV, confirm columns, start processing, then reload completed
                runs from disk.
              </Text>
            </View>
            <Text style={styles.apiStatus}>{apiMessage}</Text>
          </View>

          <View style={styles.uploadControls}>
            <Pressable onPress={chooseCsvFile} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Choose CSV</Text>
            </Pressable>
            <Pressable
              onPress={uploadSelectedCsv}
              disabled={!selectedFile || isUploading}
              style={[styles.secondaryButton, (!selectedFile || isUploading) && styles.buttonDisabled]}>
              <Text style={styles.secondaryButtonText}>
                {isUploading ? 'Uploading' : 'Upload'}
              </Text>
            </Pressable>
            <Pressable
              onPress={startProcessing}
              disabled={(!selectedFile && !activeUpload) || isStarting}
              style={[
                styles.primaryButton,
                ((!selectedFile && !activeUpload) || isStarting) && styles.buttonDisabled,
              ]}>
              <Text style={styles.primaryButtonText}>
                {isStarting ? 'Starting' : 'Start processing'}
              </Text>
            </Pressable>
            <Pressable onPress={refreshPersistentState} style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>Refresh runs</Text>
            </Pressable>
          </View>

          <View style={styles.uploadMetaGrid}>
            <View style={styles.uploadMetaBox}>
              <Text style={styles.pathLabel}>Selected file</Text>
              <Text style={styles.pathText}>
                {selectedFile?.name ?? activeUpload?.filename ?? 'No CSV selected'}
              </Text>
            </View>
            <View style={styles.uploadMetaBox}>
              <Text style={styles.pathLabel}>Cached upload</Text>
              <Text style={styles.pathText}>
                {activeUpload
                  ? `${activeUpload.id} / ${activeUpload.rowCount} rows`
                  : `${uploads.length} cached upload${uploads.length === 1 ? '' : 's'}`}
              </Text>
            </View>
            <View style={styles.uploadMetaBox}>
              <Text style={styles.pathLabel}>Active job</Text>
              <Text style={styles.pathText}>
                {activeJob ? `${activeJob.status} / ${activeJob.stage}` : 'No active job'}
              </Text>
            </View>
          </View>

          <View style={styles.columnGrid}>
            <ColumnInput label="Text column" value={textCol} onChangeText={setTextCol} />
            <ColumnInput label="ID column" value={idCol} onChangeText={setIdCol} />
            <ColumnInput label="Label column" value={labelCol} onChangeText={setLabelCol} />
          </View>

          {activeJob?.progress?.detail ? (
            <Text style={styles.progressText}>
              {activeJob.progress.detail} {activeJob.progress.processed ?? 0}/
              {activeJob.progress.total ?? 0}
            </Text>
          ) : null}

          <View style={styles.runList}>
            {jobs.slice(0, 6).map((job) => (
              <Pressable key={job.id} onPress={() => loadJob(job)} style={styles.runRow}>
                <View style={styles.caseRowMain}>
                  <Text style={styles.caseTitle}>{job.filename}</Text>
                  <Text style={styles.caseMeta}>
                    {job.id} / {job.options?.textCol ?? 'text'} / {job.options?.labelCol ?? 'hs'}
                  </Text>
                </View>
                <Text style={[styles.riskBadge, jobStatusStyle(job.status)]}>{job.status}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View style={[styles.contentGrid, isWide && styles.contentGridWide]}>
          <View style={styles.panel}>
            <Text style={styles.panelTitle}>Backend bundle</Text>
            <Text style={styles.panelCopy}>{frozenBatch.currentStage}</Text>
            <View style={styles.pathGrid}>
              <PathBox label="Input" value={activeUpload?.filename ?? frozenBatch.sourceCsv} />
              <PathBox
                label="Token importances"
                value={activeOutputs.importance_csv ?? frozenBatch.tokenImportanceCsv}
              />
              <PathBox
                label="Scrubbed CSV"
                value={activeOutputs.scrubbed_csv ?? frozenBatch.protectedCsv}
              />
              <PathBox
                label="Restated CSV"
                value={activeOutputs.restated_csv ?? frozenBatch.restatedCsv}
              />
              <PathBox
                label="Admin annotated"
                value={activeOutputs.restatement_annotated_csv ?? frozenBatch.annotatedCsv}
              />
              <PathBox
                label="Deviation audit"
                value={activeOutputs.deviation_audit_csv ?? frozenBatch.deviationAuditCsv}
              />
            </View>
            <View style={styles.stepList}>
              {pipelineSteps.map((step, index) => (
                <View key={step.label} style={styles.stepRow}>
                  <Text style={styles.stepNumber}>{index + 1}</Text>
                  <View style={styles.stepCopy}>
                    <Text style={styles.stepText}>{step.label}</Text>
                    <Text style={styles.stepDetail}>{step.detail}</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>

          <View style={styles.panel}>
            <Text style={styles.panelTitle}>Restatement gate</Text>
            <View style={styles.modelList}>
              {restatementModels.map((model) => {
                const selected = model === selectedModel;
                return (
                  <Pressable
                    key={model}
                    onPress={() => setSelectedModel(model)}
                    style={[styles.modelButton, selected && styles.modelButtonSelected]}>
                    <Text style={[styles.modelText, selected && styles.modelTextSelected]}>
                      {model}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <Pressable
              onPress={() => setGuardStrict((value) => !value)}
              style={[styles.toggleRow, guardStrict && styles.toggleRowActive]}>
              <View style={[styles.toggleKnob, guardStrict && styles.toggleKnobActive]} />
              <Text style={styles.toggleText}>
                Final restatement scrub {guardStrict ? 'on' : 'off'}
              </Text>
            </Pressable>
            <View style={styles.guardStats}>
              <SignalPill label="Clean" value={String(guardSummary.clean)} tone="mint" />
              <SignalPill label="Guarded" value={String(guardSummary.flagged)} tone="amber" />
              <SignalPill label="HS positive" value={String(hateRows)} tone="coral" />
            </View>
          </View>
        </View>

        <View style={styles.panel}>
          <View style={styles.triageHeader}>
            <View>
              <Text style={styles.panelTitle}>Admin triage</Text>
              <Text style={styles.panelCopy}>
                Source, scrubbed text, restatement, classifier, deviation, and citizen signals.
              </Text>
            </View>
            <Image
              source={require('@/assets/glimo_mascot.png')}
              style={styles.guardMascot}
              contentFit="contain"
            />
          </View>

          <View style={[styles.triageGrid, isWide && styles.triageGridWide]}>
            <View style={styles.caseList}>
              {caseItems.map((item) => {
                const selected = item.id === selectedCase?.id;
                const disposition = dispositions[item.id] ?? item.adminDisposition;
                return (
                  <Pressable
                    key={item.id}
                    onPress={() => setSelectedCaseId(item.id)}
                    style={[styles.caseRow, selected && styles.caseRowSelected]}>
                    <View style={styles.caseRowMain}>
                      <Text style={styles.caseTitle}>{item.source}</Text>
                      <Text style={styles.caseMeta}>
                        {item.classifierLabel} / score {formatScore(item.classifierScore)}
                      </Text>
                    </View>
                    <View style={styles.caseTags}>
                      <Text style={[styles.riskBadge, riskStyle(item.deviationRisk)]}>
                        {item.deviationRisk}
                      </Text>
                      <Text style={styles.dispositionBadge}>{disposition}</Text>
                    </View>
                  </Pressable>
                );
              })}
            </View>

            {selectedCase && (
              <View style={styles.caseDetail}>
                <View style={styles.caseDetailHeader}>
                  <View>
                    <Text style={styles.caseDetailTitle}>{selectedCase.source}</Text>
                    <Text style={styles.caseDetailMeta}>
                      {selectedCase.classifierLabel} / {formatScore(selectedCase.classifierScore)}
                    </Text>
                  </View>
                  <Text style={[styles.riskBadgeLarge, riskStyle(selectedCase.deviationRisk)]}>
                    {selectedCase.deviationRisk}
                  </Text>
                </View>

                <View style={styles.compareGrid}>
                  <TextBlock label="Original" value={selectedCase.originalText} tone="source" />
                  <TextBlock label="Scrubbed" value={selectedCase.scrubbedText} tone="scrubbed" />
                  <TextBlock
                    label="Restatement"
                    value={selectedGuard?.text ?? selectedCase.restatement}
                    tone="restated"
                  />
                </View>

                <View style={styles.signalGrid}>
                  <SignalPanel
                    label="Deviation"
                    value={`score ${selectedCase.deviationScore}`}
                    details={
                      selectedCase.deviationReasons.length
                        ? selectedCase.deviationReasons
                        : ['no heuristic drift']
                    }
                  />
                  <SignalPanel
                    label="Token importances"
                    value={`${selectedCase.tokenHighlights.length} tokens`}
                    details={selectedCase.tokenHighlights}
                  />
                  <SignalPanel
                    label="Citizen votes"
                    value={`${voteTotal(selectedCase.reviewerVotes)} reviews`}
                    details={[
                      `hate ${selectedCase.reviewerVotes.confirmedHatred}`,
                      `not hate ${selectedCase.reviewerVotes.notHatred}`,
                      `uncertain ${selectedCase.reviewerVotes.uncertain}`,
                    ]}
                  />
                  <SignalPanel
                    label="PII guard"
                    value={summarizeGuard(selectedGuard?.findings ?? [])}
                    details={selectedGuard?.findings ?? []}
                  />
                </View>

                {(selectedCase.missingTargetTerms.length > 0 ||
                  selectedCase.missingContextTerms.length > 0) && (
                  <View style={styles.missingPanel}>
                    <Text style={styles.missingTitle}>Deviation details</Text>
                    <View style={styles.chipWrap}>
                      {[...selectedCase.missingTargetTerms, ...selectedCase.missingContextTerms].map(
                        (term) => (
                          <Text key={term} style={styles.warningChip}>
                            {term}
                          </Text>
                        ),
                      )}
                    </View>
                  </View>
                )}

                <View style={styles.actionRow}>
                  {dispositionOptions.map((option) => {
                    const selected = currentDisposition === option;
                    return (
                      <Pressable
                        key={option}
                        onPress={() => setDisposition(option)}
                        style={[styles.actionButton, selected && styles.actionButtonSelected]}>
                        <Text
                          style={[
                            styles.actionButtonText,
                            selected && styles.actionButtonTextSelected,
                          ]}>
                          {option}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>
            )}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

type MetricProps = {
  label: string;
  value: string;
  tone: 'blue' | 'mint' | 'amber' | 'coral';
};

function Metric({ label, value, tone }: MetricProps) {
  return (
    <View style={[styles.metric, metricTone[tone]]}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function PathBox({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.pathBox}>
      <Text style={styles.pathLabel}>{label}</Text>
      <Text style={styles.pathText}>{value}</Text>
    </View>
  );
}

function ColumnInput({
  label,
  value,
  onChangeText,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
}) {
  return (
    <View style={styles.columnInputBox}>
      <Text style={styles.pathLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        autoCapitalize="none"
        autoCorrect={false}
        style={styles.columnInput}
      />
    </View>
  );
}

function TextBlock({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: 'source' | 'scrubbed' | 'restated';
}) {
  return (
    <View style={[styles.textBlock, textBlockTone[tone]]}>
      <Text style={styles.textBlockLabel}>{label}</Text>
      <Text style={styles.textBlockValue}>{value}</Text>
    </View>
  );
}

function SignalPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: 'mint' | 'amber' | 'coral';
}) {
  return (
    <View style={[styles.signalPill, signalTone[tone]]}>
      <Text style={styles.signalPillValue}>{value}</Text>
      <Text style={styles.signalPillLabel}>{label}</Text>
    </View>
  );
}

function SignalPanel({
  label,
  value,
  details,
}: {
  label: string;
  value: string;
  details: string[];
}) {
  return (
    <View style={styles.signalPanel}>
      <Text style={styles.signalLabel}>{label}</Text>
      <Text style={styles.signalValue}>{value}</Text>
      <View style={styles.chipWrap}>
        {details.length > 0 ? (
          details.map((detail) => (
            <Text key={detail} style={styles.signalChip}>
              {detail}
            </Text>
          ))
        ) : (
          <Text style={styles.signalChip}>clear</Text>
        )}
      </View>
    </View>
  );
}

function voteTotal(votes: { confirmedHatred: number; notHatred: number; uncertain: number }) {
  return votes.confirmedHatred + votes.notHatred + votes.uncertain;
}

function riskStyle(risk: string) {
  if (risk === 'high') {
    return styles.riskHigh;
  }
  if (risk === 'medium') {
    return styles.riskMedium;
  }
  if (risk === 'low') {
    return styles.riskLow;
  }
  return styles.riskOk;
}

function jobStatusStyle(status: string) {
  if (status === 'failed') {
    return styles.riskHigh;
  }
  if (status === 'running' || status === 'queued') {
    return styles.riskMedium;
  }
  if (status === 'complete') {
    return styles.riskOk;
  }
  return styles.riskLow;
}

function formatScore(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : 'n/a';
}

function backendRestatementModel(model: (typeof restatementModels)[number]) {
  if (model === 'local-llm-selected-by-admin') {
    return '';
  }
  if (model === 'qwen/qwen3-4b') {
    return 'qwen3.5-4b';
  }
  return model;
}

function preferredColumn(columns: string[], candidates: string[], fallback: string) {
  const lowerToActual = new Map(columns.map((column) => [column.toLowerCase(), column]));
  for (const candidate of candidates) {
    const exact = columns.find((column) => column === candidate);
    if (exact) {
      return exact;
    }
    const lower = lowerToActual.get(candidate.toLowerCase());
    if (lower) {
      return lower;
    }
  }
  return fallback;
}

function upsertById<T extends { id: string }>(items: T[], next: T) {
  const rest = items.filter((item) => item.id !== next.id);
  return [next, ...rest];
}

async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message =
      typeof payload?.message === 'string'
        ? payload.message
        : `Request failed with ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Unknown error';
}

function normalizeAdminCase(row: any): AdminCaseItem {
  return {
    id: String(row.id ?? row.source ?? 'case'),
    source: String(row.source ?? ''),
    originalText: String(row.originalText ?? ''),
    scrubbedText: String(row.scrubbedText ?? row.protectedText ?? ''),
    protectedText: String(row.protectedText ?? row.scrubbedText ?? ''),
    restatement: String(row.restatement ?? ''),
    classifierLabel: row.classifierLabel === 'hate' ? 'hate' : 'not_hate',
    classifierScore: typeof row.classifierScore === 'number' ? row.classifierScore : 0,
    riskLevel: normalizeRisk(row.riskLevel),
    guardFindings: Array.isArray(row.guardFindings) ? row.guardFindings : [],
    decision: 'pending',
    deviationRisk: normalizeDeviationRisk(row.deviationRisk),
    deviationScore: typeof row.deviationScore === 'number' ? row.deviationScore : 0,
    deviationReasons: Array.isArray(row.deviationReasons) ? row.deviationReasons : [],
    missingTargetTerms: Array.isArray(row.missingTargetTerms) ? row.missingTargetTerms : [],
    missingContextTerms: Array.isArray(row.missingContextTerms) ? row.missingContextTerms : [],
    tokenHighlights: Array.isArray(row.tokenHighlights) ? row.tokenHighlights : [],
    reviewerVotes: row.reviewerVotes ?? {
      confirmedHatred: 0,
      notHatred: 0,
      uncertain: 0,
    },
    adminDisposition: normalizeDisposition(row.adminDisposition),
  };
}

function normalizeRisk(value: unknown): AdminCaseItem['riskLevel'] {
  return value === 'low' || value === 'medium' || value === 'high' ? value : 'medium';
}

function normalizeDeviationRisk(value: unknown): AdminCaseItem['deviationRisk'] {
  return value === 'ok' ||
    value === 'low' ||
    value === 'medium' ||
    value === 'high' ||
    value === 'unknown'
    ? value
    : 'unknown';
}

function normalizeDisposition(value: unknown): AdminDisposition {
  return value === 'approved' || value === 'lookup' || value === 'train' || value === 'hold'
    ? value
    : 'review';
}

const metricTone = StyleSheet.create({
  blue: { backgroundColor: AppColors.blueSoft },
  mint: { backgroundColor: AppColors.mintSoft },
  amber: { backgroundColor: AppColors.amberSoft },
  coral: { backgroundColor: AppColors.coralSoft },
});

const signalTone = StyleSheet.create({
  mint: { backgroundColor: AppColors.mintSoft },
  amber: { backgroundColor: AppColors.amberSoft },
  coral: { backgroundColor: AppColors.coralSoft },
});

const textBlockTone = StyleSheet.create({
  source: { backgroundColor: '#FFF7D7' },
  scrubbed: { backgroundColor: '#F9FAFB' },
  restated: { backgroundColor: '#DFF4EF' },
});

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: AppColors.paper,
    overflow: 'hidden',
  },
  page: {
    padding: 20,
    gap: 16,
    paddingBottom: 96,
    alignSelf: 'center',
    width: '100%',
    maxWidth: 1180,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  brandLockup: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  brandMark: {
    width: 82,
    height: 82,
  },
  headerText: {
    flex: 1,
  },
  eyebrow: {
    color: AppColors.coral,
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0,
  },
  title: {
    color: AppColors.ink,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '800',
    marginTop: 4,
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: AppColors.panel,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: AppColors.mint,
  },
  statusText: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  metricsGrid: {
    gap: 12,
  },
  metricsGridWide: {
    flexDirection: 'row',
  },
  metric: {
    flex: 1,
    borderRadius: 8,
    padding: 16,
    minHeight: 88,
    justifyContent: 'space-between',
  },
  metricLabel: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '700',
  },
  metricValue: {
    color: AppColors.ink,
    fontSize: 24,
    lineHeight: 30,
    fontWeight: '900',
    marginTop: 12,
  },
  contentGrid: {
    gap: 16,
  },
  contentGridWide: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  panel: {
    flex: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.94)',
    borderRadius: 8,
    padding: 18,
    borderWidth: 1,
    borderColor: AppColors.line,
    gap: 14,
  },
  panelTitle: {
    color: AppColors.ink,
    fontSize: 18,
    fontWeight: '900',
  },
  panelCopy: {
    color: AppColors.muted,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '500',
  },
  uploadHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 14,
  },
  uploadHeaderText: {
    flex: 1,
    gap: 4,
  },
  apiStatus: {
    color: AppColors.slate,
    backgroundColor: AppColors.blueSoft,
    borderRadius: 8,
    overflow: 'hidden',
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
    maxWidth: 340,
  },
  uploadControls: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  primaryButton: {
    backgroundColor: AppColors.ink,
    borderColor: AppColors.ink,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  primaryButtonText: {
    color: AppColors.panel,
    fontSize: 13,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  secondaryButton: {
    backgroundColor: '#F9FAFB',
    borderColor: AppColors.line,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  secondaryButtonText: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  buttonDisabled: {
    opacity: 0.42,
  },
  uploadMetaGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  uploadMetaBox: {
    flexGrow: 1,
    flexBasis: 220,
    backgroundColor: '#F9FAFB',
    borderRadius: 8,
    padding: 12,
    borderWidth: 1,
    borderColor: AppColors.line,
    gap: 4,
  },
  columnGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  columnInputBox: {
    flexGrow: 1,
    flexBasis: 160,
    backgroundColor: AppColors.panel,
    borderRadius: 8,
    padding: 10,
    borderWidth: 1,
    borderColor: AppColors.line,
    gap: 5,
  },
  columnInput: {
    color: AppColors.ink,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '800',
    paddingVertical: 4,
    paddingHorizontal: 0,
  },
  progressText: {
    color: AppColors.slate,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '800',
  },
  runList: {
    gap: 8,
  },
  runRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    padding: 12,
    backgroundColor: '#F9FAFB',
  },
  pathGrid: {
    gap: 8,
  },
  pathBox: {
    backgroundColor: '#F9FAFB',
    borderRadius: 8,
    padding: 12,
    borderWidth: 1,
    borderColor: AppColors.line,
    gap: 4,
  },
  pathLabel: {
    color: AppColors.muted,
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  pathText: {
    color: AppColors.ink,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  stepList: {
    gap: 10,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  stepNumber: {
    width: 24,
    height: 24,
    borderRadius: 12,
    textAlign: 'center',
    lineHeight: 24,
    color: AppColors.panel,
    backgroundColor: AppColors.ink,
    fontSize: 12,
    fontWeight: '900',
  },
  stepCopy: {
    flex: 1,
    gap: 2,
  },
  stepText: {
    color: AppColors.slate,
    fontSize: 14,
    fontWeight: '800',
  },
  stepDetail: {
    color: AppColors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '600',
  },
  modelList: {
    gap: 8,
  },
  modelButton: {
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: '#F9FAFB',
  },
  modelButtonSelected: {
    borderColor: AppColors.mint,
    backgroundColor: AppColors.mintSoft,
  },
  modelText: {
    color: AppColors.slate,
    fontWeight: '700',
    fontSize: 14,
  },
  modelTextSelected: {
    color: AppColors.ink,
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    padding: 12,
  },
  toggleRowActive: {
    borderColor: AppColors.mint,
  },
  toggleKnob: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: AppColors.line,
  },
  toggleKnobActive: {
    backgroundColor: AppColors.mint,
  },
  toggleText: {
    color: AppColors.slate,
    fontWeight: '800',
    fontSize: 14,
    flex: 1,
  },
  guardStats: {
    gap: 10,
  },
  signalPill: {
    borderRadius: 8,
    padding: 14,
  },
  signalPillValue: {
    color: AppColors.ink,
    fontSize: 24,
    lineHeight: 30,
    fontWeight: '900',
  },
  signalPillLabel: {
    color: AppColors.slate,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
    textTransform: 'uppercase',
    marginTop: 2,
  },
  triageHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 14,
  },
  guardMascot: {
    width: 62,
    height: 70,
  },
  triageGrid: {
    gap: 16,
  },
  triageGridWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  caseList: {
    gap: 8,
    flex: 0.86,
  },
  caseRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    padding: 12,
    backgroundColor: '#F9FAFB',
  },
  caseRowSelected: {
    borderColor: AppColors.blue,
    backgroundColor: AppColors.blueSoft,
  },
  caseRowMain: {
    flex: 1,
  },
  caseTitle: {
    color: AppColors.ink,
    fontSize: 14,
    fontWeight: '900',
  },
  caseMeta: {
    color: AppColors.muted,
    fontSize: 12,
    fontWeight: '700',
    marginTop: 3,
  },
  caseTags: {
    alignItems: 'flex-end',
    gap: 6,
  },
  riskBadge: {
    overflow: 'hidden',
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 5,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  riskBadgeLarge: {
    overflow: 'hidden',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 7,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  riskHigh: {
    color: AppColors.panel,
    backgroundColor: AppColors.coral,
  },
  riskMedium: {
    color: AppColors.ink,
    backgroundColor: AppColors.amber,
  },
  riskLow: {
    color: AppColors.ink,
    backgroundColor: AppColors.amberSoft,
  },
  riskOk: {
    color: AppColors.ink,
    backgroundColor: AppColors.mintSoft,
  },
  dispositionBadge: {
    color: AppColors.slate,
    backgroundColor: AppColors.panel,
    borderRadius: 999,
    overflow: 'hidden',
    paddingHorizontal: 9,
    paddingVertical: 5,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  caseDetail: {
    flex: 1.4,
    gap: 14,
  },
  caseDetailHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  caseDetailTitle: {
    color: AppColors.ink,
    fontSize: 20,
    lineHeight: 25,
    fontWeight: '900',
  },
  caseDetailMeta: {
    color: AppColors.muted,
    fontSize: 13,
    fontWeight: '800',
    marginTop: 3,
  },
  compareGrid: {
    gap: 10,
  },
  textBlock: {
    borderRadius: 8,
    padding: 12,
    borderWidth: 1,
    borderColor: AppColors.line,
    gap: 6,
  },
  textBlockLabel: {
    color: AppColors.muted,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  textBlockValue: {
    color: AppColors.ink,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
  },
  signalGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  signalPanel: {
    minWidth: 160,
    flexGrow: 1,
    flexBasis: '47%',
    backgroundColor: '#F9FAFB',
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    padding: 12,
    gap: 6,
  },
  signalLabel: {
    color: AppColors.muted,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  signalValue: {
    color: AppColors.ink,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '900',
  },
  chipWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  signalChip: {
    color: AppColors.slate,
    backgroundColor: AppColors.panel,
    borderRadius: 999,
    overflow: 'hidden',
    paddingHorizontal: 9,
    paddingVertical: 5,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '800',
  },
  missingPanel: {
    borderWidth: 1,
    borderColor: AppColors.amber,
    backgroundColor: AppColors.amberSoft,
    borderRadius: 8,
    padding: 12,
    gap: 8,
  },
  missingTitle: {
    color: AppColors.ink,
    fontSize: 13,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  warningChip: {
    color: AppColors.ink,
    backgroundColor: AppColors.panel,
    borderRadius: 999,
    overflow: 'hidden',
    paddingHorizontal: 10,
    paddingVertical: 6,
    fontSize: 12,
    lineHeight: 15,
    fontWeight: '900',
  },
  actionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  actionButton: {
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: '#F9FAFB',
  },
  actionButtonSelected: {
    backgroundColor: AppColors.ink,
    borderColor: AppColors.ink,
  },
  actionButtonText: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  actionButtonTextSelected: {
    color: AppColors.panel,
  },
});
