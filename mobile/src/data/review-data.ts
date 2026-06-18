import { staticAdminCaseItems, staticFrozenBatch } from './static-demo-data';

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

export const frozenBatch: BatchSummary = staticFrozenBatch;

export const restatementModels = [
  'local-llm-selected-by-admin',
  'qwen/qwen3-4b',
  'openai/gpt-oss-20b',
  'manual-restatement-only',
] as const;

export const adminCaseItems: AdminCaseItem[] = staticAdminCaseItems;

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
