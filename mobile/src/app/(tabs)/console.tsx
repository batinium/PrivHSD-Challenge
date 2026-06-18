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
import { isStaticReviewMode } from '@/config/runtime';
import { AppColors } from '@/constants/theme';
import {
  AdminDisposition,
  AdminCaseItem,
  adminCaseItems,
  frozenBatch,
} from '@/data/review-data';
import { makePublicCaseId } from '@/utils/case-id';
import { guardRestatement } from '@/utils/privacy';

const API_BASE_URL = 'http://127.0.0.1:8765';

const pipelineSteps = [
  {
    label: 'CSV intake',
    detail: 'Uploaded CSV is cached and parsed with the selected text, ID, and label columns.',
  },
  {
    label: 'DeHateBERT tokens',
    detail: 'Token-importance and sidecar prediction CSVs are loaded or generated.',
  },
  {
    label: 'PII scrub',
    detail: 'Privacy and style spans are scrubbed while source text stays admin-only.',
  },
  {
    label: 'HS classification',
    detail: 'Predicted hate-speech labels and confidence scores are attached when needed.',
  },
  {
    label: 'LLM restatement',
    detail: 'The configured backend restatement model writes descriptive review text.',
  },
  {
    label: 'Final scrub',
    detail: 'High-confidence direct identifiers are removed from generated restatements.',
  },
  {
    label: 'Deviation audit',
    detail: 'Source-to-restatement drift is scored for admin triage.',
  },
  {
    label: 'Admin triage',
    detail: 'Annotated rows, audit scores, and reviewer-facing restatements feed this console.',
  },
];

const dispositionOptions: AdminDisposition[] = ['approved', 'lookup', 'train', 'hold'];
const triageFilterOptions = ['all', 'hate', 'not_hate', 'flagged'] as const;
type TriageFilter = (typeof triageFilterOptions)[number];

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
  status:
    | 'created'
    | 'queued'
    | 'running'
    | 'stopping'
    | 'complete'
    | 'failed'
    | 'interrupted'
    | 'stopped';
  stage: string;
  error?: string;
  canResume?: boolean;
  isActive?: boolean;
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
  return <AdminDashboardLive />;
}

function AdminDashboardLive() {
  const [bundleStepsOpen, setBundleStepsOpen] = useState(false);
  const [triageFilter, setTriageFilter] = useState<TriageFilter>('all');
  const [triageSearch, setTriageSearch] = useState('');
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
  const [resumingJobId, setResumingJobId] = useState('');
  const [stoppingJobId, setStoppingJobId] = useState('');
  const [textCol, setTextCol] = useState('text');
  const [idCol, setIdCol] = useState('ID');
  const [labelCol, setLabelCol] = useState('hs');
  const { width } = useWindowDimensions();
  const isWide = width >= 900;

  const filteredCaseItems = useMemo(
    () =>
      caseItems.filter(
        (item) =>
          matchesTriageFilter(item, triageFilter) &&
          matchesTriageSearch(caseItems, item, triageSearch),
      ),
    [caseItems, triageFilter, triageSearch],
  );
  const selectedCase =
    filteredCaseItems.find((item) => item.id === selectedCaseId) ?? filteredCaseItems[0];

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

  const selectedGuard = selectedCase ? guardRestatement(selectedCase.restatement) : undefined;
  const currentDisposition = selectedCase
    ? dispositions[selectedCase.id] ?? selectedCase.adminDisposition
    : 'review';
  const activeOutputs = activeBundle?.bundle?.outputs ?? {};
  const activeInputPath =
    activeBundle?.bundle?.input?.path ?? activeUpload?.filename ?? frozenBatch.sourceCsv;
  const rowCount = activeUpload?.rowCount ?? activeBundle?.protectedCsv?.row_count ?? frozenBatch.rows;
  const liveDataLoaded = caseItems !== adminCaseItems;

  function setDisposition(value: AdminDisposition) {
    if (!selectedCase) {
      return;
    }
    setDispositions((current) => ({ ...current, [selectedCase.id]: value }));
  }

  async function refreshPersistentState() {
    if (isStaticReviewMode) {
      setApiMessage('Static review package. Backend API disabled.');
      return;
    }
    try {
      const [uploadPayload, jobPayload] = await Promise.all([
        requestJson<{ uploads: UploadedCsv[] }>('/api/admin/uploads'),
        requestJson<{ jobs: AdminJob[] }>('/api/admin/jobs'),
      ]);
      setUploads(uploadPayload.uploads);
      setJobs(jobPayload.jobs);
      setApiMessage('Local API connected.');
      const latestResumable = jobPayload.jobs.find((job) => canResumeJob(job) || isJobActive(job));
      const latestComplete = jobPayload.jobs.find((job) => job.status === 'complete');
      if (latestResumable && !activeJob) {
        selectIncompleteJob(latestResumable);
      } else if (latestComplete && !activeJob) {
        await loadJob(latestComplete);
      }
    } catch (error) {
      setApiMessage(errorMessage(error));
    }
  }

  function chooseCsvFile() {
    if (isStaticReviewMode) {
      setApiMessage('Static review package. Backend API disabled.');
      return;
    }
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
    if (isStaticReviewMode) {
      setApiMessage('Static review package. Backend API disabled.');
      return null;
    }
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
    if (isStaticReviewMode) {
      setApiMessage('Static review package. Backend API disabled.');
      return;
    }
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
          restatementModel: '',
          finalScrub: true,
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

  async function resumeJob(job: AdminJob) {
    setResumingJobId(job.id);
    try {
      const payload = await requestJson<{ job: AdminJob }>(
        `/api/admin/jobs/${job.id}/resume`,
        {
          method: 'POST',
          body: JSON.stringify({}),
        },
      );
      setActiveJob(payload.job);
      setJobs((current) => upsertById(current, payload.job));
      setApiMessage(`Processing ${payload.job.status}: ${payload.job.stage}.`);
      if (payload.job.status === 'complete') {
        await loadJob(payload.job);
      }
    } catch (error) {
      setApiMessage(errorMessage(error));
    } finally {
      setResumingJobId('');
    }
  }

  async function stopJob(job: AdminJob) {
    setStoppingJobId(job.id);
    try {
      const payload = await requestJson<{ job: AdminJob }>(
        `/api/admin/jobs/${job.id}/stop`,
        {
          method: 'POST',
          body: JSON.stringify({}),
        },
      );
      setActiveJob(payload.job);
      setJobs((current) => upsertById(current, payload.job));
      setApiMessage(`Processing ${payload.job.status}: ${payload.job.stage}.`);
    } catch (error) {
      setApiMessage(errorMessage(error));
    } finally {
      setStoppingJobId('');
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
      if (payload.job.status === 'interrupted') {
        setApiMessage('Processing was interrupted. Resume to continue from cached artifacts.');
      }
      if (payload.job.status === 'stopped') {
        setApiMessage('Processing is stopped. Resume to continue from cached artifacts.');
      }
    } catch (error) {
      setApiMessage(errorMessage(error));
    }
  }

  function selectJob(job: AdminJob) {
    if (job.status === 'complete') {
      loadJob(job);
      return;
    }
    selectIncompleteJob(job);
  }

  function selectIncompleteJob(job: AdminJob) {
    setActiveJob(job);
    setJobs((current) => upsertById(current, job));
    if (job.status === 'interrupted') {
      setApiMessage('Processing was interrupted. Resume to continue from cached artifacts.');
      return;
    }
    if (job.status === 'failed') {
      setApiMessage(job.error || 'Processing failed. Resume to retry from cached artifacts.');
      return;
    }
    setApiMessage(`Processing ${job.status}: ${job.stage}.`);
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

  useEffect(() => {
    const timer = setTimeout(() => {
      refreshPersistentState();
    }, 0);
    return () => clearTimeout(timer);
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
                Upload a CSV, confirm columns, start processing, then reload completed runs from
                disk. If the label column is missing, DeHateBERT predictions feed restatement.
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
              <View key={job.id} style={styles.runRow}>
                <Pressable onPress={() => selectJob(job)} style={styles.runRowSelect}>
                  <View style={styles.caseRowMain}>
                    <Text style={styles.caseTitle}>{job.filename}</Text>
                    <Text style={styles.caseMeta}>
                      {job.id} / {job.options?.textCol ?? 'text'} / {job.options?.labelCol ?? 'hs'}
                    </Text>
                  </View>
                </Pressable>
                <View style={styles.runActions}>
                  <Text style={[styles.riskBadge, jobStatusStyle(job.status)]}>{job.status}</Text>
                  {canStopJob(job) ? (
                    <Pressable
                      onPress={() => stopJob(job)}
                      disabled={Boolean(stoppingJobId)}
                      style={[
                        styles.stopButton,
                        Boolean(stoppingJobId) && styles.buttonDisabled,
                      ]}>
                      <Text style={styles.stopButtonText}>
                        {stoppingJobId === job.id ? 'Stopping' : 'Stop'}
                      </Text>
                    </Pressable>
                  ) : null}
                  {canResumeJob(job) ? (
                    <Pressable
                      onPress={() => resumeJob(job)}
                      disabled={Boolean(resumingJobId) || isStarting || Boolean(stoppingJobId)}
                      style={[
                        styles.resumeButton,
                        (Boolean(resumingJobId) || isStarting || Boolean(stoppingJobId)) &&
                          styles.buttonDisabled,
                      ]}>
                      <Text style={styles.resumeButtonText}>
                        {resumingJobId === job.id ? 'Resuming' : 'Resume'}
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
              </View>
            ))}
          </View>
        </View>

        <View style={styles.panel}>
          <Text style={styles.panelTitle}>Backend bundle</Text>
          <Text style={styles.panelCopy}>
            {activeBundle
              ? 'Artifact paths from the loaded run. The annotated CSV keeps admin/debug context; the restated CSV and deviation audit support review and triage.'
              : `${frozenBatch.currentStage}. Load a completed run to replace these frozen demo paths with uploaded CSV outputs.`}
          </Text>
          <View style={styles.pathGrid}>
            <PathBox label="Input" value={activeInputPath} />
            <PathBox
              label="Token importances"
              value={activeOutputs.importance_csv ?? frozenBatch.tokenImportanceCsv}
            />
            {activeOutputs.prediction_csv ? (
              <PathBox label="HS predictions" value={activeOutputs.prediction_csv} />
            ) : null}
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
          <Pressable
            onPress={() => setBundleStepsOpen((open) => !open)}
            style={styles.accordionToggle}>
            <Text style={styles.accordionTitle}>Bundle steps</Text>
            <Text style={styles.accordionState}>{bundleStepsOpen ? '-' : '+'}</Text>
          </Pressable>
          {bundleStepsOpen ? (
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
          ) : null}
        </View>

        <View style={styles.panel}>
          <View style={styles.triageHeader}>
            <View>
              <Text style={styles.panelTitle}>Admin triage</Text>
              <Text style={styles.panelCopy}>
                Scrubbed text, restatement, classifier signal, token highlights, and citizen votes.
              </Text>
            </View>
            <Image
              source={require('@/assets/glimo_mascot.png')}
              style={styles.guardMascot}
              contentFit="contain"
            />
          </View>
          <View style={styles.filterRow}>
            <TextInput
              value={triageSearch}
              onChangeText={setTriageSearch}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="Search case ID"
              placeholderTextColor={AppColors.muted}
              style={styles.caseSearchInput}
            />
            {triageFilterOptions.map((option) => {
              const selected = option === triageFilter;
              return (
                <Pressable
                  key={option}
                  onPress={() => setTriageFilter(option)}
                  style={[styles.filterButton, selected && styles.filterButtonSelected]}>
                  <Text style={[styles.filterText, selected && styles.filterTextSelected]}>
                    {filterLabel(option)}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <View style={[styles.triageGrid, isWide && styles.triageGridWide]}>
            <ScrollView
              style={[styles.caseListScroll, isWide && styles.caseListScrollWide]}
              contentContainerStyle={styles.caseList}>
              {filteredCaseItems.map((item) => {
                const selected = item.id === selectedCase?.id;
                const disposition = dispositions[item.id] ?? item.adminDisposition;
                return (
                  <Pressable
                    key={item.id}
                    onPress={() => setSelectedCaseId(item.id)}
                    style={[styles.caseRow, selected && styles.caseRowSelected]}>
                    <View style={styles.caseRowMain}>
                      <Text style={styles.caseTitle}>{caseLabel(caseItems, item)}</Text>
                      <Text style={styles.caseMeta}>
                        {publicCaseId(item)} / {labelText(item.classifierLabel)}
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
              {filteredCaseItems.length === 0 ? (
                <View style={styles.emptyCaseList}>
                  <Text style={styles.caseMeta}>No cases match this filter.</Text>
                </View>
              ) : null}
            </ScrollView>

            {selectedCase && (
              <View style={styles.caseDetail}>
                <View style={styles.caseDetailHeader}>
                  <View>
                    <Text style={styles.caseDetailTitle}>{caseLabel(caseItems, selectedCase)}</Text>
                    <Text style={styles.caseDetailMeta}>
                      {publicCaseId(selectedCase)} / {labelText(selectedCase.classifierLabel)}
                    </Text>
                  </View>
                  <Text style={[styles.riskBadgeLarge, riskStyle(selectedCase.deviationRisk)]}>
                    {selectedCase.deviationRisk}
                  </Text>
                </View>

                <View style={styles.compareGrid}>
                  <TextBlock label="Scrubbed" value={selectedCase.scrubbedText} tone="scrubbed" />
                  <TextBlock
                    label="Restatement"
                    value={selectedGuard?.text ?? selectedCase.restatement}
                    tone="restated"
                  />
                </View>

                <View style={styles.signalGrid}>
                  <SignalPanel
                    label="Token importances"
                    value={`${selectedCase.tokenHighlights.length} tokens`}
                    details={selectedCase.tokenHighlights}
                  />
                  <SignalPanel
                    label="Citizen votes"
                    value={`${voteTotal(selectedCase.reviewerVotes)} reviews`}
                    details={voteDetails(selectedCase.reviewerVotes)}
                  />
                </View>

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
  tone: 'scrubbed' | 'restated';
}) {
  return (
    <View style={[styles.textBlock, textBlockTone[tone]]}>
      <Text style={styles.textBlockLabel}>{label}</Text>
      <Text style={styles.textBlockValue}>{value}</Text>
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

function voteDetails(votes: {
  confirmedHatred: number;
  notHatred: number;
  uncertain: number;
}) {
  const total = voteTotal(votes);
  return [
    `hate ${votes.confirmedHatred} (${votePercent(votes.confirmedHatred, total)})`,
    `not hate ${votes.notHatred} (${votePercent(votes.notHatred, total)})`,
    `uncertain ${votes.uncertain} (${votePercent(votes.uncertain, total)})`,
  ];
}

function votePercent(value: number, total: number) {
  if (total <= 0) {
    return '0%';
  }
  return `${Math.round((value / total) * 100)}%`;
}

function caseLabel(items: AdminCaseItem[], item: AdminCaseItem) {
  const index = items.findIndex((candidate) => candidate.id === item.id);
  return `Case ${index >= 0 ? index + 1 : 1}`;
}

function publicCaseId(item: AdminCaseItem) {
  return makePublicCaseId(item.source, item.protectedText);
}

function matchesTriageSearch(items: AdminCaseItem[], item: AdminCaseItem, query: string) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return true;
  }
  return [
    caseLabel(items, item),
    publicCaseId(item),
    labelText(item.classifierLabel),
    item.scrubbedText,
    item.restatement,
  ].some((value) => value.toLowerCase().includes(normalizedQuery));
}

function filterLabel(filter: TriageFilter) {
  if (filter === 'not_hate') {
    return 'Not hate';
  }
  if (filter === 'flagged') {
    return 'Flagged';
  }
  if (filter === 'hate') {
    return 'Hate';
  }
  return 'All';
}

function labelText(label: AdminCaseItem['classifierLabel']) {
  return label === 'hate' ? 'Hate' : 'Not hate';
}

function matchesTriageFilter(item: AdminCaseItem, filter: TriageFilter) {
  if (filter === 'all') {
    return true;
  }
  if (filter === 'flagged') {
    return item.deviationRisk === 'high' || item.deviationRisk === 'medium';
  }
  return item.classifierLabel === filter;
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
  if (status === 'interrupted') {
    return styles.riskMedium;
  }
  if (status === 'stopping') {
    return styles.riskMedium;
  }
  if (status === 'running' || status === 'queued') {
    return styles.riskMedium;
  }
  if (status === 'complete') {
    return styles.riskOk;
  }
  return styles.riskLow;
}

function canResumeJob(job: AdminJob) {
  return (
    Boolean(job.canResume) ||
    job.status === 'created' ||
    job.status === 'failed' ||
    job.status === 'interrupted' ||
    job.status === 'stopped'
  );
}

function canStopJob(job: AdminJob) {
  return isJobActive(job) && job.status !== 'stopping';
}

function isJobActive(job: AdminJob) {
  return Boolean(job.isActive) || (
    (job.status === 'queued' || job.status === 'running' || job.status === 'stopping') &&
    !job.canResume
  );
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

const textBlockTone = StyleSheet.create({
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
  panel: {
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
  runRowSelect: {
    flex: 1,
  },
  runActions: {
    alignItems: 'flex-end',
    gap: 6,
  },
  resumeButton: {
    backgroundColor: AppColors.ink,
    borderColor: AppColors.ink,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  resumeButtonText: {
    color: AppColors.panel,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  stopButton: {
    backgroundColor: AppColors.coral,
    borderColor: AppColors.coral,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  stopButtonText: {
    color: AppColors.panel,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '900',
    textTransform: 'uppercase',
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
  accordionToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 11,
    backgroundColor: '#F9FAFB',
  },
  accordionTitle: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  accordionState: {
    width: 24,
    height: 24,
    borderRadius: 12,
    textAlign: 'center',
    lineHeight: 22,
    color: AppColors.panel,
    backgroundColor: AppColors.ink,
    fontSize: 16,
    fontWeight: '900',
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
  triageHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 14,
  },
  filterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  caseSearchInput: {
    minWidth: 180,
    flexGrow: 1,
    flexBasis: 220,
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#F9FAFB',
    color: AppColors.ink,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '800',
  },
  filterButton: {
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#F9FAFB',
  },
  filterButtonSelected: {
    backgroundColor: AppColors.ink,
    borderColor: AppColors.ink,
  },
  filterText: {
    color: AppColors.slate,
    fontSize: 12,
    lineHeight: 15,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  filterTextSelected: {
    color: AppColors.panel,
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
  caseListScroll: {
    maxHeight: 280,
  },
  caseListScrollWide: {
    flex: 0.86,
    maxHeight: 520,
  },
  caseList: {
    gap: 8,
    paddingBottom: 2,
  },
  emptyCaseList: {
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    padding: 12,
    backgroundColor: '#F9FAFB',
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
