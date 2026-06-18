import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  PanResponder,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  type TextStyle,
  View,
  type ViewStyle,
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
import { ReviewItem, tutorialDecisionGuides } from '@/data/review-data';
import { TutorialTarget, useOnboarding } from '@/state/onboarding';
import { ClassifiedDecision, useReviewProgress } from '@/state/review-progress';
import { makePublicCaseId } from '@/utils/case-id';
import { guardRestatement } from '@/utils/privacy';

const SWIPE_THRESHOLD = 110;
const SWIPE_EXIT_DISTANCE = 420;
const MIN_RESTATEMENT_FONT_SIZE = 8;
const RESTATEMENT_AVERAGE_CHAR_WIDTH = 0.52;
const RESTATEMENT_LINE_HEIGHT_RATIO = 4 / 3;

type BrowserSelectionHost = {
  getSelection?: () => { removeAllRanges?: () => void } | null;
};

type WebSwipeSurfaceStyle = ViewStyle & {
  WebkitUserSelect?: 'none';
  touchAction?: 'none';
  userSelect?: 'none';
};

type WebTextFitStyle = TextStyle & {
  overflowWrap?: 'anywhere';
  wordBreak?: 'break-word';
};

const WEB_SWIPE_SURFACE_STYLE: WebSwipeSurfaceStyle | null =
  Platform.OS === 'web'
    ? {
        WebkitUserSelect: 'none',
        touchAction: 'none',
        userSelect: 'none',
      }
    : null;

const WEB_RESTATEMENT_TEXT_STYLE: WebTextFitStyle | null =
  Platform.OS === 'web'
    ? {
        overflowWrap: 'anywhere',
        wordBreak: 'break-word',
      }
    : null;

function clearBrowserSelection() {
  if (Platform.OS !== 'web') {
    return;
  }

  (globalThis as BrowserSelectionHost).getSelection?.()?.removeAllRanges?.();
}

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
  const {
    finishTutorial,
    isTutorialActive,
    isTutorialVisible,
    setTutorialFeedback,
  } = useOnboarding();
  const {
    activeIndex,
    activeItem,
    isLoadingReviewBatch,
    items,
    recordDecision,
    redrawReviewBatch,
    remainingCount,
    reviewQueueMessage,
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
    if (!isTutorialVisible) {
      return;
    }

    requestAnimationFrame(measureTutorialTargets);
  }, [isTutorialVisible, measureTutorialTargets]);

  useEffect(() => {
    if (!isTutorialVisible) {
      return;
    }

    const frame = requestAnimationFrame(measureTutorialTargets);
    return () => cancelAnimationFrame(frame);
  }, [activeIndex, cardHeight, cardWidth, height, isTutorialVisible, measureTutorialTargets, width]);

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
      const tutorialGuide = tutorialDecisionGuides[item.id];
      if (isTutorialActive && tutorialGuide && decision !== tutorialGuide.expectedDecision) {
        setTutorialFeedback(tutorialGuide.wrongChoiceMessage);
        resetCard();
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
    [
      activeIndex,
      isSubmittingDecision,
      isTutorialActive,
      items,
      position,
      recordDecision,
      resetCard,
      setTutorialFeedback,
    ],
  );

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => !isSubmittingDecision,
        onMoveShouldSetPanResponder: (_, gesture) =>
          !isSubmittingDecision && (Math.abs(gesture.dx) > 8 || Math.abs(gesture.dy) > 8),
        onPanResponderGrant: clearBrowserSelection,
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
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
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
                  {isTutorialVisible ? 'Glimo tutorial' : 'Glimo review'}
                </Text>
                <Text style={[styles.title, isCompact && styles.titleCompact]}>
                  {isTutorialVisible ? 'Practice deck' : 'Evidence deck'}
                </Text>
                {!isTutorialVisible ? (
                  <Text style={styles.queueStatus}>{reviewQueueMessage}</Text>
                ) : null}
              </View>
            </View>
            <View style={styles.headerActions}>
              {!isTutorialVisible ? (
                <Pressable
                  disabled={isLoadingReviewBatch || isSubmittingDecision}
                  onPress={redrawReviewBatch}
                  style={[
                    styles.redrawButton,
                    (isLoadingReviewBatch || isSubmittingDecision) && styles.buttonDisabled,
                  ]}>
                  <Text style={styles.redrawText}>
                    {isLoadingReviewBatch ? 'Loading' : 'Redraw'}
                  </Text>
                </Pressable>
              ) : null}
              <View style={[styles.counter, isCompact && styles.counterCompact]}>
                <Text style={styles.counterValue}>{remainingCount}</Text>
                <Text style={styles.counterLabel}>{isTutorialVisible ? 'practice' : 'left'}</Text>
              </View>
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
                    WEB_SWIPE_SURFACE_STYLE,
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
                    <Text selectable={false} style={[styles.decisionBadgeText, styles.rejectBadgeText]}>
                      NO
                    </Text>
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
                    <Text selectable={false} style={[styles.decisionBadgeText, styles.confirmBadgeText]}>
                      YES
                    </Text>
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
                    <Text
                      selectable={false}
                      style={[styles.decisionBadgeText, styles.uncertainBadgeText]}>
                      REVIEW
                    </Text>
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
                  {isTutorialVisible
                    ? 'Practice cards are complete. Finish the tutorial to load the real queue.'
                    : 'Citizen votes are ready for admin export and audit review.'}
                </Text>
                <Pressable
                  onPress={() => {
                    if (isTutorialVisible) {
                      finishTutorial();
                    } else {
                      void redrawReviewBatch();
                    }
                  }}
                  style={styles.primaryButton}>
                  <Text style={styles.primaryButtonText}>
                    {isTutorialVisible ? 'Finish tutorial' : 'Redraw cards'}
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
              <Text style={styles.rejectText}>NO</Text>
            </Pressable>
            <Pressable
              disabled={!activeItem || isSubmittingDecision}
              onPress={markUncertain}
              style={styles.actionButton}>
              <Text style={styles.reviewText}>REVIEW</Text>
            </Pressable>
            <Pressable
              disabled={!activeItem || isSubmittingDecision}
              onPress={() => commitDecision('confirmed_hatred', { x: SWIPE_EXIT_DISTANCE, y: 32 })}
              style={[styles.actionButton, styles.confirmButton]}>
              <Text style={styles.confirmText}>YES</Text>
            </Pressable>
          </View>
        </View>
        {isTutorialVisible && <OnboardingTutorial targets={tutorialTargets} />}
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
  const caseId = makePublicCaseId(item.source, item.protectedText);
  const baseRestatementFontSize = compact ? 21 : 24;
  const reservedCardHeight = compact ? 96 : 108;
  const availableTextHeight = Math.max(cardHeight - reservedCardHeight, compact ? 210 : 232);
  const availableTextWidth = Math.max(cardWidth - (compact ? 32 : 40), 220);
  const normalizedRestatementLength = Math.max(
    1,
    guarded.text.replace(/\s+/g, ' ').trim().length,
  );
  let fittedRestatementFontSize = baseRestatementFontSize;

  while (fittedRestatementFontSize > MIN_RESTATEMENT_FONT_SIZE) {
    const lineHeight = Math.ceil(fittedRestatementFontSize * RESTATEMENT_LINE_HEIGHT_RATIO);
    const charsPerLine = Math.max(
      12,
      Math.floor(
        availableTextWidth /
          (fittedRestatementFontSize * RESTATEMENT_AVERAGE_CHAR_WIDTH),
      ),
    );
    const estimatedLineCount = Math.ceil(normalizedRestatementLength / charsPerLine);

    if (estimatedLineCount * lineHeight <= availableTextHeight) {
      break;
    }

    fittedRestatementFontSize -= 1;
  }

  const fittedRestatementStyle = {
    fontSize: fittedRestatementFontSize,
    lineHeight: Math.ceil(fittedRestatementFontSize * RESTATEMENT_LINE_HEIGHT_RATIO),
  };

  return (
    <View
      style={[
        styles.card,
        WEB_SWIPE_SURFACE_STYLE,
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
        <Text selectable={false} style={styles.caseText}>
          {caseId}
        </Text>
      </View>

      <View style={styles.restatementBlock}>
        <Text selectable={false} style={styles.cardLabel}>
          Glimo protected restatement
        </Text>
        <Text
          adjustsFontSizeToFit
          minimumFontScale={MIN_RESTATEMENT_FONT_SIZE / baseRestatementFontSize}
          selectable={false}
          style={[
            styles.restatementText,
            compact && styles.restatementTextCompact,
            WEB_RESTATEMENT_TEXT_STYLE,
            fittedRestatementStyle,
          ]}>
          {guarded.text}
        </Text>
      </View>
    </View>
  );
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
  queueStatus: {
    color: AppColors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
    marginTop: 2,
  },
  headerActions: {
    alignItems: 'flex-end',
    gap: 8,
  },
  redrawButton: {
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: AppColors.panel,
  },
  redrawText: {
    color: AppColors.slate,
    fontSize: 12,
    lineHeight: 15,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  buttonDisabled: {
    opacity: 0.42,
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
    backgroundColor: 'rgba(42, 157, 143, 0.16)',
    borderColor: 'rgba(42, 157, 143, 0.48)',
    shadowColor: AppColors.mint,
  },
  confirmGlow: {
    backgroundColor: 'rgba(232, 93, 117, 0.16)',
    borderColor: 'rgba(232, 93, 117, 0.46)',
    shadowColor: AppColors.coral,
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
    borderColor: AppColors.mint,
  },
  confirmStroke: {
    borderColor: AppColors.coral,
  },
  uncertainStroke: {
    borderColor: AppColors.amber,
  },
  decisionBadge: {
    position: 'absolute',
    minWidth: 78,
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
    borderColor: AppColors.mint,
  },
  confirmBadge: {
    top: 28,
    left: 24,
    borderColor: AppColors.coral,
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
    color: AppColors.mint,
  },
  confirmBadgeText: {
    color: AppColors.coral,
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
    minHeight: 0,
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
    flexShrink: 1,
    fontSize: 24,
    lineHeight: 32,
    fontWeight: '800',
    maxWidth: '100%',
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
    width: 84,
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
    backgroundColor: AppColors.mintSoft,
    borderColor: '#A7DED4',
  },
  confirmButton: {
    backgroundColor: AppColors.coralSoft,
    borderColor: '#F3B6C2',
  },
  rejectText: {
    color: AppColors.mint,
    fontSize: 20,
    fontWeight: '900',
  },
  reviewText: {
    color: AppColors.amber,
    fontSize: 13,
    fontWeight: '900',
  },
  confirmText: {
    color: AppColors.coral,
    fontSize: 17,
    fontWeight: '900',
  },
});
