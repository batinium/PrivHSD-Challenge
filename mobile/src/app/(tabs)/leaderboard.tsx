import { ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';

import { GlimoShieldBackground } from '@/components/glimo-shield-background';
import { AppColors } from '@/constants/theme';
import {
  Achievement,
  ReviewerStanding,
  achievements,
  getReviewerPoints,
  getReviewerTitle,
  useReviewProgress,
} from '@/state/review-progress';

export default function LeaderboardScreen() {
  const { currentReviewer, leaderboard, unlockedAchievements } = useReviewProgress();
  const { width } = useWindowDimensions();
  const isWide = width >= 860;
  const currentStanding = leaderboard.find((standing) => standing.isCurrentUser);
  const currentRank = currentStanding?.rank ?? leaderboard.length;
  const currentPoints = currentStanding?.points ?? getReviewerPoints(currentReviewer);
  const currentTitle = currentStanding?.title ?? getReviewerTitle(currentReviewer);
  const unlockedIds = new Set(unlockedAchievements.map((achievement) => achievement.id));
  const nextAchievement = achievements.find((achievement) => !unlockedIds.has(achievement.id));

  return (
    <SafeAreaView style={styles.safeArea}>
      <GlimoShieldBackground />
      <ScrollView contentContainerStyle={styles.page} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <View style={styles.brandLockup}>
            <Image
              source={require('@/assets/glimo_mascot_text_below.png')}
              style={styles.brandMark}
              contentFit="contain"
            />
            <View style={styles.headerText}>
              <Text style={styles.eyebrow}>Reviewer rank</Text>
              <Text style={styles.title}>Glimo leaderboard</Text>
            </View>
          </View>
          <View style={styles.rankPill}>
            <Text style={styles.rankPillLabel}>Rank</Text>
            <Text style={styles.rankPillValue}>#{currentRank}</Text>
          </View>
        </View>

        <View style={[styles.heroPanel, isWide && styles.heroPanelWide]}>
          <View style={styles.heroCopy}>
            <Text style={styles.currentLabel}>Current title</Text>
            <Text style={styles.currentTitle}>{currentTitle}</Text>
            <Text style={styles.currentMeta}>
              {currentReviewer.totalClassified} classified reviews / {currentPoints} points
            </Text>
          </View>
          <View style={styles.heroBadgeRow}>
            {(currentStanding?.badges ?? []).slice(-4).map((badge) => (
              <View key={badge} style={styles.heroBadge}>
                <Text style={styles.heroBadgeText}>{badge}</Text>
              </View>
            ))}
          </View>
        </View>

        {nextAchievement && (
          <View style={styles.nextPanel}>
            <View>
              <Text style={styles.nextLabel}>Next badge</Text>
              <Text style={styles.nextTitle}>{nextAchievement.name}</Text>
            </View>
            <Text style={styles.nextRequirement}>{nextAchievement.requirement}</Text>
          </View>
        )}

        <View style={[styles.metricsGrid, isWide && styles.metricsGridWide]}>
          <Metric label="Classified" value={String(currentReviewer.totalClassified)} tone="blue" />
          <Metric label="Hate confirmed" value={String(currentReviewer.confirmedHatred)} tone="coral" />
          <Metric label="Speech protected" value={String(currentReviewer.protectedSpeech)} tone="mint" />
          <Metric label="Streak" value={String(currentReviewer.streak)} tone="amber" />
        </View>

        <View style={[styles.contentGrid, isWide && styles.contentGridWide]}>
          <View style={styles.panel}>
            <Text style={styles.panelTitle}>Top reviewers</Text>
            <View style={styles.standingList}>
              {leaderboard.map((standing) => (
                <StandingRow key={standing.id} standing={standing} />
              ))}
            </View>
          </View>

          <View style={styles.panel}>
            <Text style={styles.panelTitle}>Achievements</Text>
            <View style={styles.achievementGrid}>
              {achievements.map((achievement) => (
                <AchievementTile
                  achievement={achievement}
                  key={achievement.id}
                  unlocked={unlockedIds.has(achievement.id)}
                />
              ))}
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

type MetricProps = {
  label: string;
  value: string;
  tone: 'blue' | 'mint' | 'amber' | 'coral';
};

function Metric({ label, value, tone }: MetricProps) {
  return (
    <View style={[styles.metric, metricTone[tone]]}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function StandingRow({ standing }: { standing: ReviewerStanding }) {
  return (
    <View style={[styles.standingRow, standing.isCurrentUser && styles.currentStandingRow]}>
      <Text style={styles.standingRank}>#{standing.rank}</Text>
      <View style={styles.avatar}>
        <Text style={styles.avatarText}>{makeInitials(standing.displayName)}</Text>
      </View>
      <View style={styles.standingCopy}>
        <Text style={styles.standingName}>{standing.displayName}</Text>
        <Text style={styles.standingTitle}>{standing.title}</Text>
      </View>
      <View style={styles.standingScore}>
        <Text style={styles.standingPoints}>{standing.points}</Text>
        <Text style={styles.standingPointsLabel}>pts</Text>
      </View>
    </View>
  );
}

function AchievementTile({
  achievement,
  unlocked,
}: {
  achievement: Achievement;
  unlocked: boolean;
}) {
  return (
    <View style={[styles.achievementTile, !unlocked && styles.achievementTileLocked]}>
      <View style={[styles.achievementBadge, unlocked && styles.achievementBadgeUnlocked]}>
        <Text style={[styles.achievementBadgeText, unlocked && styles.achievementBadgeTextUnlocked]}>
          {achievement.badge}
        </Text>
      </View>
      <View style={styles.achievementCopy}>
        <Text style={styles.achievementName}>{achievement.name}</Text>
        <Text style={styles.achievementRequirement}>{achievement.requirement}</Text>
      </View>
      <Text style={[styles.achievementState, unlocked && styles.achievementStateUnlocked]}>
        {unlocked ? 'Unlocked' : 'Locked'}
      </Text>
    </View>
  );
}

function makeInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

const metricTone = StyleSheet.create({
  blue: { backgroundColor: AppColors.blueSoft },
  mint: { backgroundColor: AppColors.mintSoft },
  amber: { backgroundColor: AppColors.amberSoft },
  coral: { backgroundColor: AppColors.coralSoft },
});

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: AppColors.paper,
    overflow: 'hidden',
  },
  page: {
    padding: 20,
    gap: 16,
    paddingBottom: 96,
    alignSelf: 'center',
    width: '100%',
    maxWidth: 1160,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  brandLockup: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  brandMark: {
    width: 82,
    height: 82,
  },
  headerText: {
    flex: 1,
    paddingTop: 12,
  },
  eyebrow: {
    color: AppColors.blue,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  title: {
    color: AppColors.ink,
    fontSize: 32,
    lineHeight: 38,
    fontWeight: '900',
    marginTop: 4,
  },
  rankPill: {
    minWidth: 76,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#F4D96B',
    backgroundColor: AppColors.goldSoft,
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  rankPillLabel: {
    color: AppColors.muted,
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  rankPillValue: {
    color: AppColors.ink,
    fontSize: 24,
    lineHeight: 28,
    fontWeight: '900',
  },
  heroPanel: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: 'rgba(255, 255, 255, 0.95)',
    padding: 18,
    gap: 16,
  },
  heroPanelWide: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  heroCopy: {
    flex: 1,
    gap: 5,
  },
  currentLabel: {
    color: AppColors.muted,
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  currentTitle: {
    color: AppColors.ink,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '900',
  },
  currentMeta: {
    color: AppColors.slate,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
  heroBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap',
  },
  heroBadge: {
    width: 54,
    height: 54,
    borderRadius: 27,
    backgroundColor: AppColors.goldSoft,
    borderWidth: 1,
    borderColor: '#F4D96B',
    alignItems: 'center',
    justifyContent: 'center',
  },
  heroBadgeText: {
    color: AppColors.ink,
    fontSize: 16,
    fontWeight: '900',
  },
  nextPanel: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.panel,
    padding: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 16,
  },
  nextLabel: {
    color: AppColors.muted,
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  nextTitle: {
    color: AppColors.ink,
    fontSize: 17,
    lineHeight: 22,
    fontWeight: '900',
  },
  nextRequirement: {
    color: AppColors.blue,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '900',
    textAlign: 'right',
    flexShrink: 1,
  },
  metricsGrid: {
    gap: 12,
  },
  metricsGridWide: {
    flexDirection: 'row',
  },
  metric: {
    flex: 1,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(16, 32, 68, 0.08)',
    padding: 16,
    gap: 8,
  },
  metricLabel: {
    color: AppColors.slate,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  metricValue: {
    color: AppColors.ink,
    fontSize: 30,
    lineHeight: 34,
    fontWeight: '900',
  },
  contentGrid: {
    gap: 16,
  },
  contentGridWide: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  panel: {
    flex: 1,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: 'rgba(255, 255, 255, 0.95)',
    padding: 18,
    gap: 16,
  },
  panelTitle: {
    color: AppColors.ink,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '900',
  },
  standingList: {
    gap: 10,
  },
  standingRow: {
    minHeight: 68,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.panel,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  currentStandingRow: {
    borderColor: '#F4D96B',
    backgroundColor: AppColors.goldSoft,
  },
  standingRank: {
    width: 34,
    color: AppColors.blue,
    fontSize: 14,
    fontWeight: '900',
  },
  avatar: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: AppColors.blueSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    color: AppColors.blue,
    fontSize: 14,
    fontWeight: '900',
  },
  standingCopy: {
    flex: 1,
    minWidth: 0,
  },
  standingName: {
    color: AppColors.ink,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '900',
  },
  standingTitle: {
    color: AppColors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
  },
  standingScore: {
    alignItems: 'flex-end',
  },
  standingPoints: {
    color: AppColors.ink,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '900',
  },
  standingPointsLabel: {
    color: AppColors.muted,
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  achievementGrid: {
    gap: 10,
  },
  achievementTile: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.panel,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  achievementTileLocked: {
    opacity: 0.54,
  },
  achievementBadge: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: AppColors.blueSoft,
    borderWidth: 1,
    borderColor: AppColors.line,
    alignItems: 'center',
    justifyContent: 'center',
  },
  achievementBadgeUnlocked: {
    backgroundColor: AppColors.goldSoft,
    borderColor: '#F4D96B',
  },
  achievementBadgeText: {
    color: AppColors.blue,
    fontSize: 13,
    fontWeight: '900',
  },
  achievementBadgeTextUnlocked: {
    color: AppColors.ink,
  },
  achievementCopy: {
    flex: 1,
    minWidth: 0,
  },
  achievementName: {
    color: AppColors.ink,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '900',
  },
  achievementRequirement: {
    color: AppColors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
  },
  achievementState: {
    color: AppColors.muted,
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  achievementStateUnlocked: {
    color: AppColors.mint,
  },
});
