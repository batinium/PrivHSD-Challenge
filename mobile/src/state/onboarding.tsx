import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

export type TutorialTarget = 'header' | 'deck' | 'actions';

export type TutorialStep = {
  body: string;
  primaryLabel: string;
  target: TutorialTarget;
  title: string;
};

export const tutorialSteps: TutorialStep[] = [
  {
    title: 'Welcome to Glimo',
    body:
      'I loaded a practice queue first. These cards show how the system protects source text before citizen review.',
    primaryLabel: 'Next',
    target: 'header',
  },
  {
    title: 'Read the protected card',
    body:
      'Review the restatement, not the raw post. Glimo keeps sensitive text out of the public voting flow.',
    primaryLabel: 'Next',
    target: 'deck',
  },
  {
    title: 'Choose a decision',
    body:
      'Tap X for not hate, ? for unsure, or YES when the protected restatement still describes hate speech.',
    primaryLabel: 'Next',
    target: 'actions',
  },
  {
    title: 'Switch to real data',
    body:
      'Finish the tutorial when you are ready. I will clear the practice cards and load the real review queue.',
    primaryLabel: 'Finish tutorial',
    target: 'deck',
  },
];

type TutorialStatus = 'idle' | 'active' | 'complete' | 'skipped';

type OnboardingContextValue = {
  finishTutorial: () => void;
  isTutorialActive: boolean;
  nextTutorialStep: () => void;
  skipTutorial: () => void;
  startTutorial: () => void;
  tutorialStep: TutorialStep;
  tutorialStepCount: number;
  tutorialStepIndex: number;
};

const OnboardingContext = createContext<OnboardingContextValue | undefined>(undefined);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<TutorialStatus>('idle');
  const [tutorialStepIndex, setTutorialStepIndex] = useState(0);

  const startTutorial = useCallback(() => {
    setTutorialStepIndex(0);
    setStatus('active');
  }, []);

  const finishTutorial = useCallback(() => {
    setTutorialStepIndex(0);
    setStatus('complete');
  }, []);

  const skipTutorial = useCallback(() => {
    setTutorialStepIndex(0);
    setStatus('skipped');
  }, []);

  const nextTutorialStep = useCallback(() => {
    setTutorialStepIndex((current) => {
      const next = current + 1;
      if (next >= tutorialSteps.length) {
        setStatus('complete');
        return 0;
      }
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({
      finishTutorial,
      isTutorialActive: status === 'active',
      nextTutorialStep,
      skipTutorial,
      startTutorial,
      tutorialStep: tutorialSteps[tutorialStepIndex] ?? tutorialSteps[0],
      tutorialStepCount: tutorialSteps.length,
      tutorialStepIndex,
    }),
    [
      finishTutorial,
      nextTutorialStep,
      skipTutorial,
      startTutorial,
      status,
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
