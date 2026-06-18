import { useCallback, useMemo, useState } from 'react';
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
import { AppColors } from '@/constants/theme';
import { ReviewDecision, ReviewItem, reviewSeedItems } from '@/data/review-data';
import { guardRestatement } from '@/utils/privacy';

const SWIPE_THRESHOLD = 110;
const HASH_OFFSET = 0x811c9dc5;
const HASH_PRIME = 0x01000193;

export default function CitizenReview() {
  const [items, setItems] = useState(reviewSeedItems);
  const [activeIndex, setActiveIndex] = useState(0);
  const [position] = useState(() => new Animated.ValueXY());
  const { width, height } = useWindowDimensions();
  const isCompact = height < 720 || width < 380;
  const cardWidth = Math.min(width - 36, 430);
  const cardHeight = Math.min(Math.max(height - (isCompact ? 292 : 320), 340), 472);
  const activeItem = items[activeIndex];
  const remainingCount = Math.max(items.length - activeIndex, 0);

  const rotate = position.x.interpolate({
    inputRange: [-220, 0, 220],
    outputRange: ['-10deg', '0deg', '10deg'],
    extrapolate: 'clamp',
  });

  const resetCard = useCallback(() => {
    Animated.spring(position, {
      toValue: { x: 0, y: 0 },
      useNativeDriver: false,
      friction: 6,
    }).start();
  }, [position]);

  const commitDecision = useCallback((decision: ReviewDecision, toX: number) => {
    const item = items[activeIndex];
    if (!item) {
      return;
    }
    Animated.timing(position, {
      toValue: { x: toX, y: 32 },
      duration: 180,
      useNativeDriver: false,
    }).start(() => {
      setItems((current) =>
        current.map((entry) => (entry.id === item.id ? { ...entry, decision } : entry)),
      );
      setActiveIndex((current) => current + 1);
      position.setValue({ x: 0, y: 0 });
    });
  }, [activeIndex, items, position]);

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gesture) =>
          Math.abs(gesture.dx) > 8 || Math.abs(gesture.dy) > 8,
        onPanResponderMove: Animated.event([null, { dx: position.x, dy: position.y }], {
          useNativeDriver: false,
        }),
        onPanResponderRelease: (_, gesture) => {
          if (gesture.dx > SWIPE_THRESHOLD) {
            commitDecision('confirmed_hatred', 420);
          } else if (gesture.dx < -SWIPE_THRESHOLD) {
            commitDecision('not_hatred', -420);
          } else {
            resetCard();
          }
        },
      }),
    [commitDecision, position, resetCard],
  );

  function markUncertain() {
    commitDecision('uncertain', 0);
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <GlimoShieldBackground swipeX={position.x} variant="review" />
      <View style={[styles.page, isCompact && styles.pageCompact]}>
        <View style={styles.header}>
          <View style={styles.brandLockup}>
            <Image
              source={require('@/assets/glimo_mascot.png')}
              style={[styles.headerMascot, isCompact && styles.headerMascotCompact]}
              contentFit="contain"
            />
            <View style={styles.headerText}>
              <Text style={styles.eyebrow}>Glimo review</Text>
              <Text style={[styles.title, isCompact && styles.titleCompact]}>Evidence deck</Text>
            </View>
          </View>
          <View style={[styles.counter, isCompact && styles.counterCompact]}>
            <Text style={styles.counterValue}>{remainingCount}</Text>
            <Text style={styles.counterLabel}>left</Text>
          </View>
        </View>

        <View style={[styles.deck, { minHeight: cardHeight + 24, width: cardWidth }]}>
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
                  {
                    transform: [
                      { translateX: position.x },
                      { translateY: position.y },
                      { rotate },
                    ],
                  },
                ]}>
                <ReviewCard
                  item={activeItem}
                  cardHeight={cardHeight}
                  cardWidth={cardWidth}
                  compact={isCompact}
                />
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
                Citizen votes are ready for admin export and audit review.
              </Text>
              <Pressable
                onPress={() => {
                  setActiveIndex(0);
                  setItems(reviewSeedItems);
                }}
                style={styles.primaryButton}>
                <Text style={styles.primaryButtonText}>Restart demo queue</Text>
              </Pressable>
            </View>
          )}
        </View>

        <View style={[styles.actions, { width: cardWidth }]}>
          <Pressable
            disabled={!activeItem}
            onPress={() => commitDecision('not_hatred', -420)}
            style={[styles.actionButton, styles.rejectButton]}>
            <Text style={styles.rejectText}>X</Text>
          </Pressable>
          <Pressable disabled={!activeItem} onPress={markUncertain} style={styles.actionButton}>
            <Text style={styles.maybeText}>?</Text>
          </Pressable>
          <Pressable
            disabled={!activeItem}
            onPress={() => commitDecision('confirmed_hatred', 420)}
            style={[styles.actionButton, styles.confirmButton]}>
            <Text style={styles.confirmText}>YES</Text>
          </Pressable>
        </View>
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
        <View style={styles.caseIdentity}>
          <Image
            source={require('@/assets/glimo_mascot.png')}
            style={styles.cardMascot}
            contentFit="contain"
          />
          <Text style={styles.caseText}>{caseId}</Text>
        </View>
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
  caseIdentity: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 10,
  },
  cardMascot: {
    width: 42,
    height: 48,
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
