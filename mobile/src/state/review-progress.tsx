import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type { ReactNode } from 'react';

import {
  ReviewDecision,
  ReviewItem,
  reviewSeedItems,
  tutorialReviewItems,
} from '@/data/review-data';
import { useOnboarding } from '@/state/onboarding';

export type ClassifiedDecision = Exclude<ReviewDecision, 'pending'>;
const API_BASE_URL = 'http://127.0.0.1:8765';
const REVIEW_BATCH_SIZE = 5;
const REVIEW_POOL_LIMIT = 100;

export type ReviewerStats = {
  id: string;
  displayName: string;
  handle: string;
  totalClassified: number;
  confirmedHatred: number;
  protectedSpeech: number;
  uncertain: number;
  streak: number;
};

export type ReviewerStanding = ReviewerStats & {
  rank: number;
  points: number;
  title: string;
  badges: string[];
  isCurrentUser?: boolean;
};

export type Achievement = {
  id: string;
  badge: string;
  name: string;
  titleReward: string;
  requirement: string;
  isUnlocked: (stats: ReviewerStats) => boolean;
};

const currentReviewerBase: ReviewerStats = {
  id: 'current-reviewer',
  displayName: 'You',
  handle: '@glimo.reviewer',
  totalClassified: 8,
  confirmedHatred: 3,
  protectedSpeech: 4,
  uncertain: 1,
  streak: 2,
};

const leaderboardSeed: ReviewerStats[] = [
  {
    id: 'maya',
    displayName: 'Maya K.',
    handle: '@maya.guard',
    totalClassified: 46,
    confirmedHatred: 18,
    protectedSpeech: 23,
    uncertain: 5,
    streak: 9,
  },
  {
    id: 'noah',
    displayName: 'Noah R.',
    handle: '@noah.context',
    totalClassified: 31,
    confirmedHatred: 11,
    protectedSpeech: 17,
    uncertain: 3,
    streak: 6,
  },
  {
    id: 'amina',
    displayName: 'Amina S.',
    handle: '@amina.audit',
    totalClassified: 22,
    confirmedHatred: 9,
    protectedSpeech: 10,
    uncertain: 3,
    streak: 4,
  },
  {
    id: 'leo',
    displayName: 'Leo P.',
    handle: '@leo.queue',
    totalClassified: 13,
    confirmedHatred: 5,
    protectedSpeech: 6,
    uncertain: 2,
    streak: 3,
  },
];

export const achievements: Achievement[] = [
  {
    id: 'context-scout',
    badge: 'CS',
    name: 'Context Scout',
    titleReward: 'Context Scout',
    requirement: '5 classified reviews',
    isUnlocked: (stats) => stats.totalClassified >= 5,
  },
  {
    id: 'review-sentinel',
    badge: 'RS',
    name: 'Review Sentinel',
    titleReward: 'Review Sentinel',
    requirement: '10 classified reviews',
    isUnlocked: (stats) => stats.totalClassified >= 10,
  },
  {
    id: 'protector-of-speech',
    badge: 'PS',
    name: 'Protector of Speech',
    titleReward: 'Protector of Speech',
    requirement: '5 protected-speech decisions',
    isUnlocked: (stats) => stats.protectedSpeech >= 5,
  },
  {
    id: 'hate-basher',
    badge: 'HB',
    name: 'Hate Basher',
    titleReward: 'Hate Basher',
    requirement: '5 confirmed-hate decisions',
    isUnlocked: (stats) => stats.confirmedHatred >= 5,
  },
  {
    id: 'queue-champion',
    badge: 'QC',
    name: 'Queue Champion',
    titleReward: 'Queue Champion',
    requirement: '25 classified reviews',
    isUnlocked: (stats) => stats.totalClassified >= 25,
  },
  {
    id: 'speech-guardian',
    badge: 'SG',
    name: 'Speech Guardian',
    titleReward: 'Speech Guardian',
    requirement: '50 classified reviews',
    isUnlocked: (stats) => stats.totalClassified >= 50,
  },
];

type ReviewProgressContextValue = {
  activeIndex: number;
  activeItem?: ReviewItem;
  currentReviewer: ReviewerStats;
  isLoadingReviewBatch: boolean;
  items: ReviewItem[];
  leaderboard: ReviewerStanding[];
  remainingCount: number;
  recordDecision: (itemId: string, decision: ClassifiedDecision) => void;
  redrawReviewBatch: () => Promise<void>;
  resetReviewQueue: () => void;
  reviewQueueMessage: string;
  unlockedAchievements: Achievement[];
};

const ReviewProgressContext = createContext<ReviewProgressContextValue | undefined>(undefined);

export function ReviewProgressProvider({ children }: { children: ReactNode }) {
  const {
    clearTutorialFeedback,
    completeTrainingCards,
    isTutorialActive,
    isTutorialVisible,
    nextTutorialStep,
  } = useOnboarding();
  const [reviewPool, setReviewPool] = useState<ReviewItem[]>(reviewSeedItems);
  const [items, setItems] = useState<ReviewItem[]>(() => drawReviewBatch(reviewSeedItems));
  const [tutorialItems, setTutorialItems] = useState<ReviewItem[]>(tutorialReviewItems);
  const [activeIndex, setActiveIndex] = useState(0);
  const [activeTutorialIndex, setActiveTutorialIndex] = useState(0);
  const [isLoadingReviewBatch, setIsLoadingReviewBatch] = useState(false);
  const [reviewQueueMessage, setReviewQueueMessage] = useState('Demo batch');
  const [sessionStats, setSessionStats] = useState<ReviewerStats>({
    ...currentReviewerBase,
    totalClassified: 0,
    confirmedHatred: 0,
    protectedSpeech: 0,
    uncertain: 0,
    streak: 0,
  });

  const visibleItems = isTutorialVisible ? tutorialItems : items;
  const visibleActiveIndex = isTutorialVisible ? activeTutorialIndex : activeIndex;

  const currentReviewer = useMemo(() => {
    return mergeReviewerStats(currentReviewerBase, sessionStats);
  }, [sessionStats]);

  const leaderboard = useMemo(() => {
    return [currentReviewer, ...leaderboardSeed]
      .map(toStanding)
      .sort((left, right) => right.points - left.points)
      .map((standing, index) => ({
        ...standing,
        rank: index + 1,
        isCurrentUser: standing.id === currentReviewer.id,
      }));
  }, [currentReviewer]);

  const unlockedAchievements = useMemo(() => {
    return achievements.filter((achievement) => achievement.isUnlocked(currentReviewer));
  }, [currentReviewer]);

  const redrawReviewBatch = useCallback(async () => {
    if (isTutorialVisible) {
      setTutorialItems(tutorialReviewItems);
      setActiveTutorialIndex(0);
      return;
    }

    setIsLoadingReviewBatch(true);
    try {
      const livePool = await fetchReviewPool();
      const nextPool = livePool.length > 0 ? livePool : reviewSeedItems;
      setReviewPool(nextPool);
      setItems(drawReviewBatch(nextPool));
      setActiveIndex(0);
      setReviewQueueMessage(livePool.length > 0 ? 'Live batch' : 'Demo batch');
    } catch {
      const fallbackPool = reviewPool.length > 0 ? reviewPool : reviewSeedItems;
      setItems(drawReviewBatch(fallbackPool));
      setActiveIndex(0);
      setReviewQueueMessage('Demo batch');
    } finally {
      setIsLoadingReviewBatch(false);
    }
  }, [isTutorialVisible, reviewPool]);

  useEffect(() => {
    if (isTutorialVisible) {
      return;
    }

    // Load the live queue when the user leaves tutorial mode.
    const timeout = setTimeout(() => {
      void redrawReviewBatch();
    }, 0);

    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTutorialVisible]);

  const recordDecision = useCallback(
    (itemId: string, decision: ClassifiedDecision) => {
      if (isTutorialActive) {
        setTutorialItems((current) =>
          current.map((item) => (item.id === itemId ? { ...item, decision } : item)),
        );
        setActiveTutorialIndex((current) => current + 1);
        clearTutorialFeedback();
        if (activeTutorialIndex >= tutorialReviewItems.length - 1) {
          completeTrainingCards();
        } else {
          nextTutorialStep();
        }
        return;
      }

      setItems((current) =>
        current.map((item) => (item.id === itemId ? { ...item, decision } : item)),
      );
      setActiveIndex((current) => current + 1);
      setSessionStats((current) => addDecisionToStats(current, decision));
    },
    [
      activeTutorialIndex,
      clearTutorialFeedback,
      completeTrainingCards,
      isTutorialActive,
      nextTutorialStep,
    ],
  );

  const resetReviewQueue = useCallback(() => {
    if (isTutorialActive) {
      setTutorialItems(tutorialReviewItems);
      setActiveTutorialIndex(0);
      return;
    }

    setItems((current) => current.map((item) => ({ ...item, decision: 'pending' })));
    setActiveIndex(0);
  }, [isTutorialActive]);

  const value = useMemo(
    () => ({
      activeIndex: visibleActiveIndex,
      activeItem: visibleItems[visibleActiveIndex],
      currentReviewer,
      isLoadingReviewBatch,
      items: visibleItems,
      leaderboard,
      remainingCount: Math.max(visibleItems.length - visibleActiveIndex, 0),
      recordDecision,
      redrawReviewBatch,
      resetReviewQueue,
      reviewQueueMessage: isTutorialVisible ? 'Practice batch' : reviewQueueMessage,
      unlockedAchievements,
    }),
    [
      currentReviewer,
      isLoadingReviewBatch,
      isTutorialVisible,
      leaderboard,
      recordDecision,
      redrawReviewBatch,
      resetReviewQueue,
      reviewQueueMessage,
      unlockedAchievements,
      visibleActiveIndex,
      visibleItems,
    ],
  );

  return (
    <ReviewProgressContext.Provider value={value}>{children}</ReviewProgressContext.Provider>
  );
}

export function useReviewProgress() {
  const context = useContext(ReviewProgressContext);

  if (!context) {
    throw new Error('useReviewProgress must be used inside ReviewProgressProvider');
  }

  return context;
}

export function getReviewerTitle(stats: ReviewerStats): string {
  const unlocked = achievements.filter((achievement) => achievement.isUnlocked(stats));
  return unlocked[unlocked.length - 1]?.titleReward ?? 'New Reviewer';
}

export function getReviewerPoints(stats: ReviewerStats): number {
  return (
    stats.totalClassified * 10 +
    stats.confirmedHatred * 4 +
    stats.protectedSpeech * 3 +
    stats.uncertain * 2 +
    stats.streak * 5
  );
}

function addDecisionToStats(stats: ReviewerStats, decision: ClassifiedDecision): ReviewerStats {
  return {
    ...stats,
    totalClassified: stats.totalClassified + 1,
    confirmedHatred: stats.confirmedHatred + (decision === 'confirmed_hatred' ? 1 : 0),
    protectedSpeech: stats.protectedSpeech + (decision === 'not_hatred' ? 1 : 0),
    uncertain: stats.uncertain + (decision === 'uncertain' ? 1 : 0),
    streak: stats.streak + 1,
  };
}

function mergeReviewerStats(base: ReviewerStats, session: ReviewerStats): ReviewerStats {
  return {
    ...base,
    totalClassified: base.totalClassified + session.totalClassified,
    confirmedHatred: base.confirmedHatred + session.confirmedHatred,
    protectedSpeech: base.protectedSpeech + session.protectedSpeech,
    uncertain: base.uncertain + session.uncertain,
    streak: base.streak + session.streak,
  };
}

function toStanding(stats: ReviewerStats): ReviewerStanding {
  const unlocked = achievements.filter((achievement) => achievement.isUnlocked(stats));

  return {
    ...stats,
    rank: 0,
    points: getReviewerPoints(stats),
    title: getReviewerTitle(stats),
    badges: unlocked.map((achievement) => achievement.badge),
  };
}

async function fetchReviewPool(): Promise<ReviewItem[]> {
  const response = await fetch(`${API_BASE_URL}/api/review-seed?limit=${REVIEW_POOL_LIMIT}`);
  if (!response.ok) {
    throw new Error(`Review queue request failed with ${response.status}`);
  }
  const payload = await response.json();
  const rows = Array.isArray(payload?.items) ? payload.items : [];
  return rows.map(normalizeReviewItem);
}

function normalizeReviewItem(row: any, index: number): ReviewItem {
  return {
    id: String(row.id ?? `case-${index + 1}`),
    source: String(row.source ?? row.id ?? `case-${index + 1}`),
    protectedText: String(row.protectedText ?? row.scrubbedText ?? row.text ?? ''),
    restatement: String(row.restatement ?? row.protectedText ?? row.text ?? ''),
    classifierLabel: row.classifierLabel === 'hate' ? 'hate' : 'not_hate',
    classifierScore: typeof row.classifierScore === 'number' ? row.classifierScore : 0,
    riskLevel: normalizeRiskLevel(row.riskLevel),
    guardFindings: Array.isArray(row.guardFindings) ? row.guardFindings : [],
    decision: 'pending',
  };
}

function normalizeRiskLevel(value: unknown): ReviewItem['riskLevel'] {
  return value === 'low' || value === 'medium' || value === 'high' ? value : 'medium';
}

function drawReviewBatch(pool: ReviewItem[]) {
  const hateItems = shuffle(pool.filter((item) => item.classifierLabel === 'hate'));
  const notHateItems = shuffle(pool.filter((item) => item.classifierLabel === 'not_hate'));
  const selected: ReviewItem[] =
    hateItems.length > 0 && notHateItems.length > 0
      ? [hateItems[0], notHateItems[0]]
      : [];
  const selectedIds = new Set(selected.map((item) => item.id));
  const remaining = shuffle(pool.filter((item) => !selectedIds.has(item.id)));
  const batch = selected.length > 0 ? [...selected, ...remaining] : remaining;

  return batch.slice(0, REVIEW_BATCH_SIZE).map((item) => ({
    ...item,
    decision: 'pending' as const,
  }));
}

function shuffle<T>(items: T[]) {
  const shuffled = [...items];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled;
}
