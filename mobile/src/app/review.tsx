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
import { guardRestatement, summarizeGuard } from '@/utils/privacy';

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
      <GlimoShieldBackground swipeX={position.x} variant="review" />
      <View style={styles.page}>
        <View style={styles.header}>
          <View style={styles.brandLockup}>
            <Image
              source={require('@/assets/glimo_mascot.png')}
              style={styles.headerMascot}
              contentFit="contain"
            />
            <View style={styles.headerText}>
              <Text style={styles.eyebrow}>Glimo review</Text>
              <Text style={styles.title}>Evidence deck</Text>
            </View>
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
  const guardSignal =
    guarded.findings.length === 0
      ? 'Clear'
      : `${guarded.findings.length} finding${guarded.findings.length === 1 ? '' : 's'}`;

  return (
    <View style={[styles.card, { width: cardWidth }, stacked && styles.cardStacked, animatedStyle]}>
      <Image
        source={require('@/assets/glimo_sheild.png')}
        style={styles.cardWatermark}
        contentFit="contain"
      />
      <View style={styles.cardTop}>
        <View style={styles.caseIdentity}>
          <Image
            source={require('@/assets/glimo_mascot.png')}
            style={styles.cardMascot}
            contentFit="contain"
          />
          <View>
            <Text style={styles.caseText}>{item.id}</Text>
            <Text style={styles.caseSource}>{item.source}</Text>
          </View>
        </View>
        <View style={[styles.riskPill, riskTone[item.riskLevel]]}>
          <Text style={styles.riskText}>{item.riskLevel}</Text>
        </View>
      </View>

      <View style={styles.restatementBlock}>
        <Text style={styles.cardLabel}>Glimo protected restatement</Text>
        <Text style={styles.restatementText}>{guarded.text}</Text>
      </View>

      <View style={styles.cardSignals}>
        <View style={styles.signalBox}>
          <Text style={styles.signalLabel}>Classifier</Text>
          <Text style={styles.signalValue}>{Math.round(item.classifierScore * 100)}%</Text>
        </View>
        <View style={styles.signalBox}>
          <Text style={styles.signalLabel}>Guard</Text>
          <Text style={styles.signalValue}>{guardSignal}</Text>
        </View>
      </View>

      {!stacked && (
        <View style={styles.motionSeal}>
          <Image
            source={require('@/assets/shield_animation.gif')}
            style={styles.motionGif}
            contentFit="cover"
          />
          <View style={styles.motionCopy}>
            <Text style={styles.motionTitle}>Shield pass</Text>
            <Text style={styles.motionMeta}>{summarizeGuard(guarded.findings)}</Text>
          </View>
        </View>
      )}
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
    overflow: 'hidden',
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
    backgroundColor: 'rgba(255, 255, 255, 0.94)',
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
    minHeight: 472,
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
  caseSource: {
    color: AppColors.muted,
    fontSize: 11,
    fontWeight: '800',
    marginTop: 2,
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
  cardSignals: {
    flexDirection: 'row',
    gap: 10,
  },
  signalBox: {
    flex: 1,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: '#F8FBFF',
    padding: 12,
    gap: 4,
  },
  signalLabel: {
    color: AppColors.muted,
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  signalValue: {
    color: AppColors.ink,
    fontSize: 14,
    fontWeight: '900',
  },
  motionSeal: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#F4D96B',
    backgroundColor: AppColors.goldSoft,
    padding: 10,
  },
  motionGif: {
    width: 82,
    height: 46,
    borderRadius: 6,
  },
  motionCopy: {
    flex: 1,
    gap: 2,
  },
  motionTitle: {
    color: AppColors.ink,
    fontSize: 13,
    fontWeight: '900',
  },
  motionMeta: {
    color: AppColors.slate,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
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
