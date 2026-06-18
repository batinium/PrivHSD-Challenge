import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';

import { GlimoShieldBackground } from '@/components/glimo-shield-background';
import {
  OnboardingTutorial,
  TutorialSpotlightLayout,
} from '@/components/onboarding-tutorial';
import { AppColors } from '@/constants/theme';
import { ReviewItem } from '@/data/review-data';
import { TutorialTarget, useOnboarding } from '@/state/onboarding';
import { ClassifiedDecision, useReviewProgress } from '@/state/review-progress';
import { guardRestatement } from '@/utils/privacy';

const SWIPE_THRESHOLD = 110;
const SWIPE_EXIT_DISTANCE = 420;
const HASH_OFFSET = 0x811c9dc5;
const HASH_PRIME = 0x01000193;

export default function CitizenReview() {
  const rootRef = useRef<View>(null);
  const headerRef = useRef<View>(null);
  const deckRef = useRef<View>(null);
  const actionsRef = useRef<View>(null);
  const [position] = useState(() => new Animated.ValueXY());
  const [isSubmittingDecision, setIsSubmittingDecision] = useState(false);
  const [tutorialTargets, setTutorialTargets] = useState<
    Partial<Record<TutorialTarget, TutorialSpotlightLayout>>
  >({});
  const { finishTutorial, isTutorialActive } = useOnboarding();
  const {
    activeIndex,
    activeItem,
    items,
    recordDecision,
    remainingCount,
    resetReviewQueue,
  } = useReviewProgress();
  const { width, height } = useWindowDimensions();
  const isCompact = height < 720 || width < 380;
  const cardWidth = Math.min(width - 36, 430);
  const cardHeight = Math.min(Math.max(height - (isCompact ? 292 : 320), 340), 472);

  const updateTutorialTargets = useCallback(
    (nextTargets: Partial<Record<TutorialTarget, TutorialSpotlightLayout>>) => {
      setTutorialTargets((current) => {
        const hasChanged = (Object.keys(nextTargets) as TutorialTarget[]).some((target) => {
          const currentTarget = current[target];
          const nextTarget = nextTargets[target];

          return (
            !currentTarget ||
            !nextTarget ||
            currentTarget.borderRadius !== nextTarget.borderRadius ||
            currentTarget.height !== nextTarget.height ||
            currentTarget.width !== nextTarget.width ||
            currentTarget.x !== nextTarget.x ||
            currentTarget.y !== nextTarget.y
          );
        });

        return hasChanged ? { ...current, ...nextTargets } : current;
      });
    },
    [],
  );

  const measureTutorialTargets = useCallback(() => {
    const root = rootRef.current;

    if (!root) {
      return;
    }

    root.measureInWindow((rootX, rootY) => {
      const nextTargets: Partial<Record<TutorialTarget, TutorialSpotlightLayout>> = {};
      let pendingMeasurements = 3;

      function finishMeasurement() {
        pendingMeasurements -= 1;
        if (pendingMeasurements === 0) {
          updateTutorialTargets(nextTargets);
        }
      }

      function measureTarget(
        target: TutorialTarget,
        ref: RefObject<View | null>,
        borderRadius: number,
      ) {
        const node = ref.current;

        if (!node) {
          finishMeasurement();
          return;
        }

        node.measureInWindow((targetX, targetY, targetWidth, targetHeight) => {
          nextTargets[target] = {
            borderRadius,
            height: targetHeight,
            width: targetWidth,
            x: targetX - rootX,
            y: targetY - rootY,
          };
          finishMeasurement();
        });
      }

      measureTarget('header', headerRef, 34);
      measureTarget('deck', deckRef, 18);
      measureTarget('actions', actionsRef, 40);
    });
  }, [updateTutorialTargets]);

  const scheduleTutorialMeasurement = useCallback(() => {
    if (!isTutorialActive) {
      return;
    }

    requestAnimationFrame(measureTutorialTargets);
  }, [isTutorialActive, measureTutorialTargets]);

  useEffect(() => {
    if (!isTutorialActive) {
      return;
    }

    const frame = requestAnimationFrame(measureTutorialTargets);
    return () => cancelAnimationFrame(frame);
  }, [activeIndex, cardHeight, cardWidth, height, isTutorialActive, measureTutorialTargets, width]);

  const rotate = position.x.interpolate({
    inputRange: [-220, 0, 220],
    outputRange: ['-10deg', '0deg', '10deg'],
    extrapolate: 'clamp',
  });
  const rejectFeedback = position.x.interpolate({
    inputRange: [-SWIPE_THRESHOLD, -24, 0],
    outputRange: [1, 0.16, 0],
    extrapolate: 'clamp',
  });
  const confirmFeedback = position.x.interpolate({
    inputRange: [0, 24, SWIPE_THRESHOLD],
    outputRange: [0, 0.16, 1],
    extrapolate: 'clamp',
  });
  const uncertainFeedback = position.y.interpolate({
    inputRange: [-SWIPE_THRESHOLD, -24, 0],
    outputRange: [1, 0.18, 0],
    extrapolate: 'clamp',
  });
  const rejectScale = position.x.interpolate({
    inputRange: [-220, 0],
    outputRange: [1.08, 0.86],
    extrapolate: 'clamp',
  });
  const confirmScale = position.x.interpolate({
    inputRange: [0, 220],
    outputRange: [0.86, 1.08],
    extrapolate: 'clamp',
  });
  const uncertainScale = position.y.interpolate({
    inputRange: [-220, 0],
    outputRange: [1.08, 0.86],
    extrapolate: 'clamp',
  });

  const resetCard = useCallback(() => {
    Animated.spring(position, {
      toValue: { x: 0, y: 0 },
      useNativeDriver: false,
      friction: 6,
    }).start();
  }, [position]);

  const commitDecision = useCallback(
    (decision: ClassifiedDecision, toValue: { x: number; y: number }) => {
      if (isSubmittingDecision) {
        return;
      }

      const item = items[activeIndex];
      if (!item) {
        return;
      }
      setIsSubmittingDecision(true);
      Animated.timing(position, {
        toValue,
        duration: 180,
        useNativeDriver: false,
      }).start(() => {
        recordDecision(item.id, decision);
        position.setValue({ x: 0, y: 0 });
        setIsSubmittingDecision(false);
      });
    },
    [activeIndex, isSubmittingDecision, items, position, recordDecision],
  );

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gesture) =>
          !isSubmittingDecision && (Math.abs(gesture.dx) > 8 || Math.abs(gesture.dy) > 8),
        onPanResponderMove: Animated.event([null, { dx: position.x, dy: position.y }], {
          useNativeDriver: false,
        }),
        onPanResponderRelease: (_, gesture) => {
          const absX = Math.abs(gesture.dx);
          const absY = Math.abs(gesture.dy);

          if (gesture.dy < -SWIPE_THRESHOLD && absY > absX) {
            commitDecision('uncertain', { x: 0, y: -SWIPE_EXIT_DISTANCE });
          } else if (gesture.dx > SWIPE_THRESHOLD) {
            commitDecision('confirmed_hatred', { x: SWIPE_EXIT_DISTANCE, y: 32 });
          } else if (gesture.dx < -SWIPE_THRESHOLD) {
            commitDecision('not_hatred', { x: -SWIPE_EXIT_DISTANCE, y: 32 });
          } else {
            resetCard();
          }
        },
      }),
    [commitDecision, isSubmittingDecision, position, resetCard],
  );

  function markUncertain() {
    commitDecision('uncertain', { x: 0, y: -SWIPE_EXIT_DISTANCE });
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <View ref={rootRef} onLayout={scheduleTutorialMeasurement} style={styles.root}>
        <GlimoShieldBackground swipeX={position.x} variant="review" />
        <View style={[styles.page, isCompact && styles.pageCompact]}>
          <View ref={headerRef} onLayout={scheduleTutorialMeasurement} style={styles.header}>
            <View style={styles.brandLockup}>
              <Image
                source={require('@/assets/glimo_mascot.png')}
                style={[styles.headerMascot, isCompact && styles.headerMascotCompact]}
                contentFit="contain"
              />
              <View style={styles.headerText}>
                <Text style={styles.eyebrow}>
                  {isTutorialActive ? 'Glimo tutorial' : 'Glimo review'}
                </Text>
                <Text style={[styles.title, isCompact && styles.titleCompact]}>
                  {isTutorialActive ? 'Practice deck' : 'Evidence deck'}
                </Text>
              </View>
            </View>
            <View style={[styles.counter, isCompact && styles.counterCompact]}>
              <Text style={styles.counterValue}>{remainingCount}</Text>
              <Text style={styles.counterLabel}>{isTutorialActive ? 'practice' : 'left'}</Text>
            </View>
          </View>

          <View
            ref={deckRef}
            onLayout={scheduleTutorialMeasurement}
            style={[styles.deck, { minHeight: cardHeight + 24, width: cardWidth }]}>
            {activeItem ? (
              <>
                {items[activeIndex + 1] && (
                  <ReviewCard
                    item={items[activeIndex + 1]}
                    cardHeight={cardHeight}
                    cardWidth={cardWidth}
                    compact={isCompact}
                    stacked
                    animatedStyle={styles.stackedCard}
                  />
                )}
                <Animated.View
                  {...panResponder.panHandlers}
                  style={[
                    styles.animatedCard,
                    { height: cardHeight, width: cardWidth },
                    {
                      transform: [
                        { translateX: position.x },
                        { translateY: position.y },
                        { rotate },
                      ],
                    },
                  ]}>
                  <Animated.View
                    pointerEvents="none"
                    style={[styles.decisionGlow, styles.rejectGlow, { opacity: rejectFeedback }]}
                  />
                  <Animated.View
                    pointerEvents="none"
                    style={[styles.decisionGlow, styles.confirmGlow, { opacity: confirmFeedback }]}
                  />
                  <Animated.View
                    pointerEvents="none"
                    style={[
                      styles.decisionGlow,
                      styles.uncertainGlow,
                      { opacity: uncertainFeedback },
                    ]}
                  />
                  <ReviewCard
                    item={activeItem}
                    cardHeight={cardHeight}
                    cardWidth={cardWidth}
                    compact={isCompact}
                  />
                  <Animated.View
                    pointerEvents="none"
                    style={[
                      styles.decisionStroke,
                      styles.rejectStroke,
                      { opacity: rejectFeedback },
                    ]}
                  />
                  <Animated.View
                    pointerEvents="none"
                    style={[
                      styles.decisionStroke,
                      styles.confirmStroke,
                      { opacity: confirmFeedback },
                    ]}
                  />
                  <Animated.View
                    pointerEvents="none"
                    style={[
                      styles.decisionStroke,
                      styles.uncertainStroke,
                      { opacity: uncertainFeedback },
                    ]}
                  />
                  <Animated.View
                    pointerEvents="none"
                    style={[
                      styles.decisionBadge,
                      styles.rejectBadge,
                      {
                        opacity: rejectFeedback,
                        transform: [{ rotate: '-14deg' }, { scale: rejectScale }],
                      },
                    ]}>
                    <Text style={[styles.decisionBadgeText, styles.rejectBadgeText]}>X</Text>
                  </Animated.View>
                  <Animated.View
                    pointerEvents="none"
                    style={[
                      styles.decisionBadge,
                      styles.confirmBadge,
                      {
                        opacity: confirmFeedback,
                        transform: [{ rotate: '12deg' }, { scale: confirmScale }],
                      },
                    ]}>
                    <Text style={[styles.decisionBadgeText, styles.confirmBadgeText]}>YES</Text>
                  </Animated.View>
                  <Animated.View
                    pointerEvents="none"
                    style={[
                      styles.decisionBadge,
                      styles.uncertainBadge,
                      {
                        opacity: uncertainFeedback,
                        transform: [{ rotate: '-3deg' }, { scale: uncertainScale }],
                      },
                    ]}>
                    <Text style={[styles.decisionBadgeText, styles.uncertainBadgeText]}>?</Text>
                  </Animated.View>
                </Animated.View>
              </>
            ) : (
              <View style={[styles.emptyCard, { minHeight: cardHeight, width: cardWidth }]}>
                <Image
                  source={require('@/assets/glimo_mascot.png')}
                  style={styles.emptyMascot}
                  contentFit="contain"
                />
                <Text style={styles.emptyTitle}>Queue complete</Text>
                <Text style={styles.emptyCopy}>
                  {isTutorialActive
                    ? 'Practice cards are complete. Finish the tutorial to load the real queue.'
                    : 'Citizen votes are ready for admin export and audit review.'}
                </Text>
                <Pressable
                  onPress={() => {
                    if (isTutorialActive) {
                      finishTutorial();
                    } else {
                      resetReviewQueue();
                    }
                  }}
                  style={styles.primaryButton}>
                  <Text style={styles.primaryButtonText}>
                    {isTutorialActive ? 'Finish tutorial' : 'Restart demo queue'}
                  </Text>
                </Pressable>
              </View>
            )}
          </View>

          <View
            ref={actionsRef}
            onLayout={scheduleTutorialMeasurement}
            style={[styles.actions, { width: cardWidth }]}>
            <Pressable
              disabled={!activeItem || isSubmittingDecision}
              onPress={() => commitDecision('not_hatred', { x: -SWIPE_EXIT_DISTANCE, y: 32 })}
              style={[styles.actionButton, styles.rejectButton]}>
              <Text style={styles.rejectText}>X</Text>
            </Pressable>
            <Pressable
              disabled={!activeItem || isSubmittingDecision}
              onPress={markUncertain}
              style={styles.actionButton}>
              <Text style={styles.maybeText}>?</Text>
            </Pressable>
            <Pressable
              disabled={!activeItem || isSubmittingDecision}
              onPress={() => commitDecision('confirmed_hatred', { x: SWIPE_EXIT_DISTANCE, y: 32 })}
              style={[styles.actionButton, styles.confirmButton]}>
              <Text style={styles.confirmText}>YES</Text>
            </Pressable>
          </View>
        </View>
        {isTutorialActive && <OnboardingTutorial targets={tutorialTargets} />}
      </View>
    </SafeAreaView>
  );
}

type ReviewCardProps = {
  cardHeight: number;
  item: ReviewItem;
  cardWidth: number;
  compact: boolean;
  stacked?: boolean;
  animatedStyle?: object;
};

function ReviewCard({
  cardHeight,
  item,
  cardWidth,
  compact,
  stacked,
  animatedStyle,
}: ReviewCardProps) {
  const guarded = guardRestatement(item.restatement);
  const caseId = makeReviewCaseId(item);

  return (
    <View
      style={[
        styles.card,
        { height: cardHeight, width: cardWidth },
        compact && styles.cardCompact,
        stacked && styles.cardStacked,
        animatedStyle,
      ]}>
      <Image
        source={require('@/assets/glimo_sheild.png')}
        style={[styles.cardWatermark, compact && styles.cardWatermarkCompact]}
        contentFit="contain"
      />
      <View style={styles.cardTop}>
        <Text style={styles.caseText}>{caseId}</Text>
      </View>

      <View style={styles.restatementBlock}>
        <Text style={styles.cardLabel}>Glimo protected restatement</Text>
        <Text style={[styles.restatementText, compact && styles.restatementTextCompact]}>
          {guarded.text}
        </Text>
      </View>
    </View>
  );
}

function makeReviewCaseId(item: ReviewItem): string {
  let hash = HASH_OFFSET;
  const input = `${item.source}\n${item.protectedText}`;

  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, HASH_PRIME);
  }

  return `case-${(hash >>> 0).toString(16).padStart(8, '0')}`;
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: AppColors.paper,
    overflow: 'hidden',
  },
  root: {
    flex: 1,
    overflow: 'hidden',
  },
  page: {
    flex: 1,
    alignItems: 'center',
    paddingHorizontal: 18,
    paddingBottom: 88,
    gap: 14,
  },
  pageCompact: {
    gap: 10,
    paddingBottom: 72,
  },
  header: {
    width: '100%',
    maxWidth: 720,
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 16,
    paddingTop: 8,
  },
  brandLockup: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  headerMascot: {
    width: 58,
    height: 66,
  },
  headerMascotCompact: {
    width: 48,
    height: 54,
  },
  headerText: {
    flex: 1,
  },
  eyebrow: {
    color: AppColors.blue,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  title: {
    color: AppColors.ink,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '900',
    marginTop: 4,
  },
  titleCompact: {
    fontSize: 24,
    lineHeight: 30,
  },
  counter: {
    width: 68,
    height: 68,
    borderRadius: 34,
    backgroundColor: AppColors.goldSoft,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#F4D96B',
  },
  counterCompact: {
    width: 58,
    height: 58,
    borderRadius: 29,
  },
  counterValue: {
    color: AppColors.ink,
    fontSize: 22,
    lineHeight: 24,
    fontWeight: '900',
  },
  counterLabel: {
    color: AppColors.muted,
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  deck: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  animatedCard: {
    position: 'absolute',
  },
  decisionGlow: {
    position: 'absolute',
    top: -14,
    right: -14,
    bottom: -14,
    left: -14,
    borderRadius: 18,
    borderWidth: 2,
    shadowOffset: { width: 0, height: 14 },
    shadowRadius: 26,
    shadowOpacity: 0.42,
    elevation: 6,
  },
  rejectGlow: {
    backgroundColor: 'rgba(232, 93, 117, 0.16)',
    borderColor: 'rgba(232, 93, 117, 0.46)',
    shadowColor: AppColors.coral,
  },
  confirmGlow: {
    backgroundColor: 'rgba(42, 157, 143, 0.16)',
    borderColor: 'rgba(42, 157, 143, 0.48)',
    shadowColor: AppColors.mint,
  },
  uncertainGlow: {
    backgroundColor: 'rgba(246, 200, 76, 0.18)',
    borderColor: 'rgba(246, 200, 76, 0.56)',
    shadowColor: AppColors.amber,
  },
  decisionStroke: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    borderRadius: 8,
    borderWidth: 4,
    zIndex: 2,
  },
  rejectStroke: {
    borderColor: AppColors.coral,
  },
  confirmStroke: {
    borderColor: AppColors.mint,
  },
  uncertainStroke: {
    borderColor: AppColors.amber,
  },
  decisionBadge: {
    position: 'absolute',
    minWidth: 72,
    minHeight: 54,
    borderRadius: 8,
    borderWidth: 4,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.92)',
    zIndex: 3,
  },
  rejectBadge: {
    top: 28,
    right: 24,
    borderColor: AppColors.coral,
  },
  confirmBadge: {
    top: 28,
    left: 24,
    borderColor: AppColors.mint,
  },
  uncertainBadge: {
    top: 18,
    alignSelf: 'center',
    borderColor: AppColors.amber,
  },
  decisionBadgeText: {
    fontSize: 30,
    lineHeight: 34,
    fontWeight: '900',
  },
  rejectBadgeText: {
    color: AppColors.coral,
  },
  confirmBadgeText: {
    color: AppColors.mint,
  },
  uncertainBadgeText: {
    color: AppColors.amber,
  },
  card: {
    backgroundColor: 'rgba(255, 255, 255, 0.96)',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    padding: 20,
    gap: 18,
    overflow: 'hidden',
    shadowColor: '#111827',
    shadowOpacity: 0.16,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 10 },
    elevation: 4,
  },
  cardCompact: {
    gap: 12,
    padding: 16,
  },
  cardStacked: {
    transform: [{ scale: 0.95 }, { translateY: 18 }],
    opacity: 0.5,
  },
  stackedCard: {
    position: 'absolute',
  },
  cardWatermark: {
    position: 'absolute',
    right: -42,
    bottom: -28,
    width: 190,
    height: 190,
    opacity: 0.08,
  },
  cardWatermarkCompact: {
    right: -54,
    bottom: -34,
    width: 168,
    height: 168,
  },
  cardTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  caseText: {
    color: AppColors.ink,
    fontSize: 12,
    fontWeight: '900',
  },
  restatementBlock: {
    gap: 12,
    flex: 1,
    justifyContent: 'center',
  },
  cardLabel: {
    color: AppColors.blue,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  restatementText: {
    color: AppColors.ink,
    fontSize: 24,
    lineHeight: 32,
    fontWeight: '800',
  },
  restatementTextCompact: {
    fontSize: 21,
    lineHeight: 28,
  },
  emptyCard: {
    minHeight: 380,
    backgroundColor: 'rgba(255, 255, 255, 0.96)',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    padding: 24,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 14,
  },
  emptyMascot: {
    width: 116,
    height: 132,
  },
  emptyTitle: {
    color: AppColors.ink,
    fontSize: 28,
    fontWeight: '900',
  },
  emptyCopy: {
    color: AppColors.muted,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: '600',
    textAlign: 'center',
  },
  primaryButton: {
    marginTop: 10,
    backgroundColor: AppColors.ink,
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  primaryButtonText: {
    color: AppColors.panel,
    fontSize: 14,
    fontWeight: '900',
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 12,
  },
  actionButton: {
    width: 74,
    height: 58,
    borderRadius: 29,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: AppColors.panel,
    borderWidth: 1,
    borderColor: AppColors.line,
    shadowColor: '#111827',
    shadowOpacity: 0.12,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  rejectButton: {
    backgroundColor: AppColors.coralSoft,
    borderColor: '#F3B6C2',
  },
  confirmButton: {
    backgroundColor: AppColors.mintSoft,
    borderColor: '#A7DED4',
  },
  rejectText: {
    color: AppColors.coral,
    fontSize: 24,
    fontWeight: '900',
  },
  maybeText: {
    color: AppColors.amber,
    fontSize: 24,
    fontWeight: '900',
  },
  confirmText: {
    color: AppColors.mint,
    fontSize: 17,
    fontWeight: '900',
  },
});
