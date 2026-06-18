import {
  createContext,
  useCallback,
  useContext,
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
  items: ReviewItem[];
  leaderboard: ReviewerStanding[];
  remainingCount: number;
  recordDecision: (itemId: string, decision: ClassifiedDecision) => void;
  resetReviewQueue: () => void;
  unlockedAchievements: Achievement[];
};

const ReviewProgressContext = createContext<ReviewProgressContextValue | undefined>(undefined);

export function ReviewProgressProvider({ children }: { children: ReactNode }) {
  const {
    clearTutorialFeedback,
    completeTrainingCards,
    isTutorialActive,
    nextTutorialStep,
  } = useOnboarding();
  const [items, setItems] = useState<ReviewItem[]>(reviewSeedItems);
  const [tutorialItems, setTutorialItems] = useState<ReviewItem[]>(tutorialReviewItems);
  const [activeIndex, setActiveIndex] = useState(0);
  const [activeTutorialIndex, setActiveTutorialIndex] = useState(0);
  const [sessionStats, setSessionStats] = useState<ReviewerStats>({
    ...currentReviewerBase,
    totalClassified: 0,
    confirmedHatred: 0,
    protectedSpeech: 0,
    uncertain: 0,
    streak: 0,
  });

  const visibleItems = isTutorialActive ? tutorialItems : items;
  const visibleActiveIndex = isTutorialActive ? activeTutorialIndex : activeIndex;

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

    setItems(reviewSeedItems);
    setActiveIndex(0);
  }, [isTutorialActive]);

  const value = useMemo(
    () => ({
      activeIndex: visibleActiveIndex,
      activeItem: visibleItems[visibleActiveIndex],
      currentReviewer,
      items: visibleItems,
      leaderboard,
      remainingCount: Math.max(visibleItems.length - visibleActiveIndex, 0),
      recordDecision,
      resetReviewQueue,
      unlockedAchievements,
    }),
    [
      currentReviewer,
      leaderboard,
      recordDecision,
      resetReviewQueue,
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
