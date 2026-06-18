import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

export type TutorialTarget = 'header' | 'deck' | 'actions';

export type TutorialStep = {
  body: string;
  decisionLabel?: string;
  primaryLabel?: string;
  requiresDecision?: boolean;
  target: TutorialTarget;
  title: string;
};

export const tutorialSteps: TutorialStep[] = [
  {
    title: 'Hi, reviewer',
    body:
      'I am Glimo. I loaded three training cards for you first, so you can practice before the real review deck starts.',
    primaryLabel: 'Start training',
    target: 'header',
  },
  {
    title: 'Example 1: choose YES',
    body:
      'This card describes an attack on a protected group. You should send YES when the protected restatement still describes hate speech.',
    decisionLabel: 'YES',
    requiresDecision: true,
    target: 'actions',
  },
  {
    title: 'Example 2: choose NO',
    body:
      'This one criticizes an idea without targeting a protected class. You should choose NO when it is not hate speech.',
    decisionLabel: 'NO',
    requiresDecision: true,
    target: 'actions',
  },
  {
    title: 'Example 3: send for review',
    body:
      'This card is too ambiguous to classify confidently. You should use REVIEW when a human second look is safer than guessing.',
    decisionLabel: 'REVIEW',
    requiresDecision: true,
    target: 'actions',
  },
];

const farewellStep: TutorialStep = {
  title: 'You are ready',
  body:
    'Nice work. I loaded the real deck for you now, so I will get out of your way. Bye for now.',
  primaryLabel: 'Start real deck',
  target: 'deck',
};

type TutorialStatus = 'idle' | 'active' | 'farewell' | 'complete' | 'skipped';

type OnboardingContextValue = {
  clearTutorialFeedback: () => void;
  completeTrainingCards: () => void;
  finishTutorial: () => void;
  isTutorialActive: boolean;
  isTutorialFarewell: boolean;
  isTutorialVisible: boolean;
  nextTutorialStep: () => void;
  setTutorialFeedback: (message: string) => void;
  skipTutorial: () => void;
  startTutorial: () => void;
  tutorialFeedback?: string;
  tutorialStep: TutorialStep;
  tutorialStepCount: number;
  tutorialStepIndex: number;
};

const OnboardingContext = createContext<OnboardingContextValue | undefined>(undefined);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<TutorialStatus>('idle');
  const [tutorialFeedback, setTutorialFeedbackState] = useState<string | undefined>();
  const [tutorialStepIndex, setTutorialStepIndex] = useState(0);

  const startTutorial = useCallback(() => {
    setTutorialFeedbackState(undefined);
    setTutorialStepIndex(0);
    setStatus('active');
  }, []);

  const finishTutorial = useCallback(() => {
    setTutorialFeedbackState(undefined);
    setTutorialStepIndex(0);
    setStatus('complete');
  }, []);

  const skipTutorial = useCallback(() => {
    setTutorialFeedbackState(undefined);
    setTutorialStepIndex(0);
    setStatus('skipped');
  }, []);

  const completeTrainingCards = useCallback(() => {
    setTutorialFeedbackState(undefined);
    setTutorialStepIndex(0);
    setStatus('farewell');
  }, []);

  const clearTutorialFeedback = useCallback(() => {
    setTutorialFeedbackState(undefined);
  }, []);

  const setTutorialFeedback = useCallback((message: string) => {
    setTutorialFeedbackState(message);
  }, []);

  const nextTutorialStep = useCallback(() => {
    setTutorialFeedbackState(undefined);
    setTutorialStepIndex((current) => {
      const next = current + 1;
      if (next >= tutorialSteps.length) {
        return current;
      }
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({
      clearTutorialFeedback,
      completeTrainingCards,
      finishTutorial,
      isTutorialActive: status === 'active',
      isTutorialFarewell: status === 'farewell',
      isTutorialVisible: status === 'active' || status === 'farewell',
      nextTutorialStep,
      setTutorialFeedback,
      skipTutorial,
      startTutorial,
      tutorialFeedback,
      tutorialStep: status === 'farewell'
        ? farewellStep
        : tutorialSteps[tutorialStepIndex] ?? tutorialSteps[0],
      tutorialStepCount: tutorialSteps.length,
      tutorialStepIndex,
    }),
    [
      clearTutorialFeedback,
      completeTrainingCards,
      finishTutorial,
      nextTutorialStep,
      setTutorialFeedback,
      skipTutorial,
      startTutorial,
      status,
      tutorialFeedback,
      tutorialStepIndex,
    ],
  );

  return <OnboardingContext.Provider value={value}>{children}</OnboardingContext.Provider>;
}

export function useOnboarding() {
  const context = useContext(OnboardingContext);

  if (!context) {
    throw new Error('useOnboarding must be used inside OnboardingProvider');
  }

  return context;
}
