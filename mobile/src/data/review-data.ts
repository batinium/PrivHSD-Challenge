export type ReviewDecision = 'pending' | 'confirmed_hatred' | 'not_hatred' | 'uncertain';
export type AdminDisposition = 'review' | 'approved' | 'lookup' | 'train' | 'hold';
export type TrainingDecision = Exclude<ReviewDecision, 'pending'>;

export type ReviewItem = {
  id: string;
  source: string;
  protectedText: string;
  restatement: string;
  classifierLabel: 'hate' | 'not_hate';
  classifierScore: number;
  riskLevel: 'low' | 'medium' | 'high';
  guardFindings: string[];
  decision: ReviewDecision;
};

export type ReviewerVoteSummary = {
  confirmedHatred: number;
  notHatred: number;
  uncertain: number;
};

export type AdminCaseItem = ReviewItem & {
  originalText: string;
  scrubbedText: string;
  deviationRisk: 'ok' | 'low' | 'medium' | 'high' | 'unknown';
  deviationScore: number;
  deviationReasons: string[];
  missingTargetTerms: string[];
  missingContextTerms: string[];
  tokenHighlights: string[];
  reviewerVotes: ReviewerVoteSummary;
  adminDisposition: AdminDisposition;
};

export type TutorialDecisionGuide = {
  expectedDecision: TrainingDecision;
  expectedLabel: string;
  wrongChoiceMessage: string;
};

export type BatchSummary = {
  id: string;
  sourceCsv: string;
  protectedCsv: string;
  annotatedCsv: string;
  restatedCsv: string;
  deviationAuditCsv: string;
  tokenImportanceCsv: string;
  rows: number;
  changedTextCells: number;
  validationStatus: 'valid' | 'blocked';
  baselineScore: string;
  currentStage: string;
};

export const frozenBatch: BatchSummary = {
  id: 'local-placeholder',
  sourceCsv: 'data/train/train_split.csv',
  protectedCsv: 'data/outputs/local/protected.csv',
  annotatedCsv: 'data/outputs/local/annotated.csv',
  restatedCsv: 'data/outputs/local/restated.csv',
  deviationAuditCsv: 'data/outputs/local/deviation_audit.csv',
  tokenImportanceCsv: 'data/outputs/local/token_importance.csv',
  rows: 0,
  changedTextCells: 0,
  validationStatus: 'valid',
  baselineScore: 'local data not bundled',
  currentStage: 'Connect the local API or build a private static review bundle',
};

export const restatementModels = [
  'local-llm-selected-by-admin',
  'qwen/qwen3-4b',
  'openai/gpt-oss-20b',
  'manual-restatement-only',
] as const;

export const adminCaseItems: AdminCaseItem[] = [
  {
    id: 'demo-admin-001',
    source: 'DEMO',
    originalText:
      'Synthetic example: a user attacks a protected group while mentioning a place name.',
    scrubbedText:
      'Synthetic example: a user attacks a protected group while mentioning [LOCATION].',
    protectedText:
      'Synthetic example: a user attacks a protected group while mentioning [LOCATION].',
    restatement:
      'The comment attacks a protected group and omits the local place name.',
    classifierLabel: 'hate',
    classifierScore: 0.91,
    riskLevel: 'medium',
    guardFindings: [],
    decision: 'pending',
    deviationRisk: 'ok',
    deviationScore: 0,
    deviationReasons: [],
    missingTargetTerms: [],
    missingContextTerms: [],
    tokenHighlights: ['protected group'],
    reviewerVotes: { confirmedHatred: 2, notHatred: 0, uncertain: 1 },
    adminDisposition: 'review',
  },
  {
    id: 'demo-admin-002',
    source: 'DEMO',
    originalText:
      'Synthetic example: a user criticizes a policy without targeting identity.',
    scrubbedText:
      'Synthetic example: a user criticizes a policy without targeting identity.',
    protectedText:
      'Synthetic example: a user criticizes a policy without targeting identity.',
    restatement:
      'The comment criticizes a policy decision without attacking a protected group.',
    classifierLabel: 'not_hate',
    classifierScore: 0.12,
    riskLevel: 'low',
    guardFindings: [],
    decision: 'pending',
    deviationRisk: 'ok',
    deviationScore: 0,
    deviationReasons: [],
    missingTargetTerms: [],
    missingContextTerms: [],
    tokenHighlights: ['policy'],
    reviewerVotes: { confirmedHatred: 0, notHatred: 3, uncertain: 0 },
    adminDisposition: 'approved',
  },
  {
    id: 'demo-admin-003',
    source: 'DEMO',
    originalText:
      'Synthetic example: a masked comment is too vague to classify confidently.',
    scrubbedText:
      'Synthetic example: a [STYLE] comment is too vague to classify confidently.',
    protectedText:
      'Synthetic example: a [STYLE] comment is too vague to classify confidently.',
    restatement:
      'The protected text is ambiguous and should be sent to admin review.',
    classifierLabel: 'not_hate',
    classifierScore: 0.49,
    riskLevel: 'medium',
    guardFindings: ['ambiguous_after_masking'],
    decision: 'pending',
    deviationRisk: 'low',
    deviationScore: 1,
    deviationReasons: ['context_reduced'],
    missingTargetTerms: [],
    missingContextTerms: ['masked context'],
    tokenHighlights: ['ambiguous'],
    reviewerVotes: { confirmedHatred: 0, notHatred: 1, uncertain: 2 },
    adminDisposition: 'lookup',
  },
];

export const reviewSeedItems: ReviewItem[] = adminCaseItems.map(
  ({
    originalText: _originalText,
    scrubbedText: _scrubbedText,
    deviationRisk: _deviationRisk,
    deviationScore: _deviationScore,
    deviationReasons: _deviationReasons,
    missingTargetTerms: _missingTargetTerms,
    missingContextTerms: _missingContextTerms,
    tokenHighlights: _tokenHighlights,
    reviewerVotes: _reviewerVotes,
    adminDisposition: _adminDisposition,
    ...item
  }) => item,
);

export const tutorialReviewItems: ReviewItem[] = [
  {
    id: 'tutorial-card-001',
    source: 'TRAINING_YES',
    protectedText:
      'Training example: the protected text describes a post attacking people because of a protected identity.',
    restatement:
      'Example YES: the comment attacks a protected group while leaving private details and direct identifiers out of view.',
    classifierLabel: 'hate',
    classifierScore: 0.91,
    riskLevel: 'low',
    guardFindings: [],
    decision: 'pending',
  },
  {
    id: 'tutorial-card-002',
    source: 'TRAINING_NO',
    protectedText:
      'Training example: the protected text describes a post criticizing a policy without targeting identity.',
    restatement:
      'Example NO: the comment criticizes a policy decision without targeting a protected group.',
    classifierLabel: 'not_hate',
    classifierScore: 0.11,
    riskLevel: 'low',
    guardFindings: [],
    decision: 'pending',
  },
  {
    id: 'tutorial-card-003',
    source: 'TRAINING_REVIEW',
    protectedText:
      'Training example: the protected text is ambiguous after privacy masking and needs a second look.',
    restatement:
      'Example REVIEW: the comment may be offensive, but the protected restatement is too ambiguous for a confident decision.',
    classifierLabel: 'not_hate',
    classifierScore: 0.48,
    riskLevel: 'medium',
    guardFindings: [],
    decision: 'pending',
  },
];

export const tutorialDecisionGuides: Record<string, TutorialDecisionGuide> = {
  'tutorial-card-001': {
    expectedDecision: 'confirmed_hatred',
    expectedLabel: 'YES',
    wrongChoiceMessage:
      'I stopped that send. This training card still describes hate speech against a protected group, so try YES.',
  },
  'tutorial-card-002': {
    expectedDecision: 'not_hatred',
    expectedLabel: 'NO',
    wrongChoiceMessage:
      'I stopped that send. This example criticizes a policy, not a protected group, so try NO.',
  },
  'tutorial-card-003': {
    expectedDecision: 'uncertain',
    expectedLabel: 'REVIEW',
    wrongChoiceMessage:
      'I stopped that send. This one is ambiguous after masking, so send it for REVIEW instead of guessing.',
  },
};
