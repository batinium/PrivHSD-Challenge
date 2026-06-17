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
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppColors } from '@/constants/theme';
import { ReviewDecision, ReviewItem, reviewSeedItems } from '@/data/review-data';
import { guardRestatement } from '@/utils/privacy';

const SWIPE_THRESHOLD = 110;

export default function CitizenReview() {
  const [items, setItems] = useState(reviewSeedItems);
  const [activeIndex, setActiveIndex] = useState(0);
  const [history, setHistory] = useState<{ id: string; decision: ReviewDecision }[]>([]);
  const [position] = useState(() => new Animated.ValueXY());
  const { width } = useWindowDimensions();
  const cardWidth = Math.min(width - 36, 430);
  const activeItem = items[activeIndex];

  const stats = useMemo(() => {
    return {
      done: history.length,
      remaining: Math.max(items.length - activeIndex, 0),
      confirmed: history.filter((item) => item.decision === 'confirmed_hatred').length,
      dismissed: history.filter((item) => item.decision === 'not_hatred').length,
    };
  }, [activeIndex, history, items.length]);

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
      setHistory((current) => [...current, { id: item.id, decision }]);
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
      <View style={styles.page}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>Citizen review</Text>
            <Text style={styles.title}>Restated evidence deck</Text>
          </View>
          <View style={styles.counter}>
            <Text style={styles.counterValue}>{stats.remaining}</Text>
            <Text style={styles.counterLabel}>left</Text>
          </View>
        </View>

        <View style={styles.statsRow}>
          <Stat label="Done" value={String(stats.done)} />
          <Stat label="Confirm" value={String(stats.confirmed)} />
          <Stat label="Reject" value={String(stats.dismissed)} />
        </View>

        <View style={[styles.deck, { width: cardWidth }]}>
          {activeItem ? (
            <>
              {items[activeIndex + 1] && (
                <ReviewCard
                  item={items[activeIndex + 1]}
                  cardWidth={cardWidth}
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
                <ReviewCard item={activeItem} cardWidth={cardWidth} />
              </Animated.View>
            </>
          ) : (
            <View style={[styles.emptyCard, { width: cardWidth }]}>
              <Text style={styles.emptyTitle}>Queue complete</Text>
              <Text style={styles.emptyCopy}>
                Citizen votes are ready for admin export and audit review.
              </Text>
              <Pressable
                onPress={() => {
                  setActiveIndex(0);
                  setHistory([]);
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
  item: ReviewItem;
  cardWidth: number;
  stacked?: boolean;
  animatedStyle?: object;
};

function ReviewCard({ item, cardWidth, stacked, animatedStyle }: ReviewCardProps) {
  const guarded = guardRestatement(item.restatement);
  return (
    <View style={[styles.card, { width: cardWidth }, stacked && styles.cardStacked, animatedStyle]}>
      <View style={styles.cardTop}>
        <View style={styles.casePill}>
          <Text style={styles.caseText}>{item.id}</Text>
        </View>
        <View style={[styles.riskPill, riskTone[item.riskLevel]]}>
          <Text style={styles.riskText}>{item.riskLevel}</Text>
        </View>
      </View>

      <View style={styles.restatementBlock}>
        <Text style={styles.cardLabel}>Restated for citizen review</Text>
        <Text style={styles.restatementText}>{guarded.text}</Text>
      </View>
    </View>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const riskTone = StyleSheet.create({
  low: { backgroundColor: AppColors.mintSoft },
  medium: { backgroundColor: AppColors.amberSoft },
  high: { backgroundColor: AppColors.coralSoft },
});

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: AppColors.paper,
  },
  page: {
    flex: 1,
    alignItems: 'center',
    paddingHorizontal: 18,
    paddingBottom: 88,
    gap: 14,
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
  eyebrow: {
    color: AppColors.coral,
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
  counter: {
    width: 68,
    height: 68,
    borderRadius: 34,
    backgroundColor: AppColors.panel,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: AppColors.line,
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
  statsRow: {
    width: '100%',
    maxWidth: 430,
    flexDirection: 'row',
    gap: 10,
  },
  stat: {
    flex: 1,
    backgroundColor: AppColors.panel,
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: AppColors.line,
  },
  statValue: {
    color: AppColors.ink,
    fontSize: 18,
    fontWeight: '900',
  },
  statLabel: {
    color: AppColors.muted,
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  deck: {
    flex: 1,
    minHeight: 420,
    justifyContent: 'center',
    alignItems: 'center',
  },
  animatedCard: {
    position: 'absolute',
  },
  card: {
    minHeight: 410,
    backgroundColor: AppColors.panel,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    padding: 20,
    justifyContent: 'space-between',
    shadowColor: '#111827',
    shadowOpacity: 0.16,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 10 },
    elevation: 4,
  },
  cardStacked: {
    transform: [{ scale: 0.95 }, { translateY: 18 }],
    opacity: 0.5,
  },
  stackedCard: {
    position: 'absolute',
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  casePill: {
    borderRadius: 999,
    backgroundColor: '#F9FAFB',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  caseText: {
    color: AppColors.slate,
    fontSize: 12,
    fontWeight: '900',
  },
  riskPill: {
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  riskText: {
    color: AppColors.ink,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  restatementBlock: {
    gap: 12,
  },
  cardLabel: {
    color: AppColors.muted,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  restatementText: {
    color: AppColors.ink,
    fontSize: 26,
    lineHeight: 34,
    fontWeight: '800',
  },
  emptyCard: {
    minHeight: 380,
    backgroundColor: AppColors.panel,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    padding: 24,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 14,
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
