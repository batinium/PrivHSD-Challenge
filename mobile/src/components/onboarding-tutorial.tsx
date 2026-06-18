import { Image } from 'expo-image';
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { AppColors } from '@/constants/theme';
import { TutorialTarget, useOnboarding } from '@/state/onboarding';

export type TutorialSpotlightLayout = {
  borderRadius?: number;
  height: number;
  width: number;
  x: number;
  y: number;
};

type OnboardingTutorialProps = {
  targets: Partial<Record<TutorialTarget, TutorialSpotlightLayout>>;
};

const SPOTLIGHT_PADDING = 8;
const BUBBLE_HEIGHT = 228;

export function OnboardingTutorial({ targets }: OnboardingTutorialProps) {
  const {
    finishTutorial,
    nextTutorialStep,
    skipTutorial,
    tutorialStep,
    tutorialStepCount,
    tutorialStepIndex,
  } = useOnboarding();
  const { height, width } = useWindowDimensions();
  const target = targets[tutorialStep.target] ?? fallbackTarget(width, height);
  const spotlight = paddedTarget(target, width, height);
  const bubbleWidth = Math.min(width - 32, 430);
  const bubbleLeft = clamp(
    spotlight.x + spotlight.width / 2 - bubbleWidth / 2,
    16,
    width - bubbleWidth - 16,
  );
  const bubbleBelow = spotlight.y + spotlight.height + 18;
  const hasRoomBelow = bubbleBelow + BUBBLE_HEIGHT < height - 20;
  const bubbleTop = hasRoomBelow
    ? bubbleBelow
    : clamp(spotlight.y - BUBBLE_HEIGHT - 18, 16, height - BUBBLE_HEIGHT - 16);
  const isFinalStep = tutorialStepIndex === tutorialStepCount - 1;

  function handlePrimaryPress() {
    if (isFinalStep) {
      finishTutorial();
    } else {
      nextTutorialStep();
    }
  }

  return (
    <View pointerEvents="box-none" style={styles.overlay}>
      <View
        pointerEvents="auto"
        style={[styles.scrim, { height: spotlight.y, left: 0, right: 0, top: 0 }]}
      />
      <View
        pointerEvents="auto"
        style={[
          styles.scrim,
          {
            bottom: 0,
            left: 0,
            right: 0,
            top: spotlight.y + spotlight.height,
          },
        ]}
      />
      <View
        pointerEvents="auto"
        style={[
          styles.scrim,
          {
            height: spotlight.height,
            left: 0,
            top: spotlight.y,
            width: spotlight.x,
          },
        ]}
      />
      <View
        pointerEvents="auto"
        style={[
          styles.scrim,
          {
            height: spotlight.height,
            left: spotlight.x + spotlight.width,
            right: 0,
            top: spotlight.y,
          },
        ]}
      />

      <View
        pointerEvents="none"
        style={[
          styles.spotlight,
          {
            borderRadius: target.borderRadius ?? 24,
            height: spotlight.height,
            left: spotlight.x,
            top: spotlight.y,
            width: spotlight.width,
          },
        ]}
      />

      <View
        pointerEvents="auto"
        style={[
          styles.bubbleCluster,
          {
            left: bubbleLeft,
            top: bubbleTop,
            width: bubbleWidth,
          },
        ]}>
        <Image
          source={require('@/assets/glimo_mascot.png')}
          style={styles.mascot}
          contentFit="contain"
        />
        <View style={styles.bubble}>
          <View style={styles.bubbleHeader}>
            <Text style={styles.stepCount}>
              {tutorialStepIndex + 1}/{tutorialStepCount}
            </Text>
            <Pressable onPress={skipTutorial} style={styles.skipButton}>
              <Text style={styles.skipText}>Skip</Text>
            </Pressable>
          </View>
          <Text style={styles.title}>{tutorialStep.title}</Text>
          <Text style={styles.body}>{tutorialStep.body}</Text>
          <View style={styles.buttonRow}>
            {!isFinalStep && (
              <Pressable onPress={finishTutorial} style={styles.secondaryButton}>
                <Text style={styles.secondaryButtonText}>Finish now</Text>
              </Pressable>
            )}
            <Pressable onPress={handlePrimaryPress} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>{tutorialStep.primaryLabel}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </View>
  );
}

function fallbackTarget(width: number, height: number): TutorialSpotlightLayout {
  return {
    borderRadius: 24,
    height: Math.min(260, height * 0.38),
    width: width - 44,
    x: 22,
    y: Math.max(96, height * 0.24),
  };
}

function paddedTarget(
  target: TutorialSpotlightLayout,
  screenWidth: number,
  screenHeight: number,
): TutorialSpotlightLayout {
  const x = clamp(target.x - SPOTLIGHT_PADDING, 8, screenWidth - 16);
  const y = clamp(target.y - SPOTLIGHT_PADDING, 8, screenHeight - 16);
  const maxWidth = screenWidth - x - 8;
  const maxHeight = screenHeight - y - 8;

  return {
    ...target,
    height: Math.min(target.height + SPOTLIGHT_PADDING * 2, maxHeight),
    width: Math.min(target.width + SPOTLIGHT_PADDING * 2, maxWidth),
    x,
    y,
  };
}

function clamp(value: number, min: number, max: number) {
  if (max < min) {
    return min;
  }
  return Math.min(Math.max(value, min), max);
}

const styles = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  scrim: {
    position: 'absolute',
    backgroundColor: 'rgba(16, 32, 68, 0.58)',
  },
  spotlight: {
    position: 'absolute',
    borderWidth: 4,
    borderColor: AppColors.gold,
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    shadowColor: AppColors.gold,
    shadowOpacity: 0.42,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 0 },
    elevation: 12,
  },
  bubbleCluster: {
    position: 'absolute',
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
  },
  mascot: {
    width: 64,
    height: 74,
  },
  bubble: {
    flex: 1,
    minHeight: 190,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#C7D7F0',
    backgroundColor: 'rgba(255, 255, 255, 0.98)',
    padding: 14,
    gap: 8,
    shadowColor: '#111827',
    shadowOpacity: 0.2,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 10 },
    elevation: 8,
  },
  bubbleHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  stepCount: {
    color: AppColors.blue,
    fontSize: 12,
    fontWeight: '900',
  },
  skipButton: {
    minHeight: 32,
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  skipText: {
    color: AppColors.muted,
    fontSize: 13,
    fontWeight: '900',
  },
  title: {
    color: AppColors.ink,
    fontSize: 19,
    lineHeight: 24,
    fontWeight: '900',
  },
  body: {
    color: AppColors.slate,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
  buttonRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 4,
  },
  secondaryButton: {
    minHeight: 40,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  secondaryButtonText: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '900',
  },
  primaryButton: {
    minHeight: 40,
    borderRadius: 8,
    backgroundColor: AppColors.ink,
    justifyContent: 'center',
    paddingHorizontal: 14,
  },
  primaryButtonText: {
    color: AppColors.panel,
    fontSize: 13,
    fontWeight: '900',
  },
});
