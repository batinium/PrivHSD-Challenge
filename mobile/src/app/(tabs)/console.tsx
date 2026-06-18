import { useMemo, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';

import { GlimoShieldBackground } from '@/components/glimo-shield-background';
import { AppColors } from '@/constants/theme';
import { frozenBatch, restatementModels, reviewSeedItems } from '@/data/review-data';
import { guardRestatement, summarizeGuard } from '@/utils/privacy';

const pipelineSteps = [
  'Deterministic PII removal',
  'Optional Presidio/scrubadub span assist',
  'HSD classification sidecar',
  'Frozen protected CSV export',
  'Restatement leakage guard',
  'Glimo swipe review queue',
];

export default function AdminDashboard() {
  const [selectedModel, setSelectedModel] =
    useState<(typeof restatementModels)[number]>(restatementModels[0]);
  const [guardStrict, setGuardStrict] = useState(true);
  const { width } = useWindowDimensions();
  const isWide = width >= 860;

  const guardSummary = useMemo(() => {
    return reviewSeedItems.reduce(
      (summary, item) => {
        const result = guardRestatement(item.restatement);
        return {
          clean: summary.clean + (result.findings.length === 0 ? 1 : 0),
          flagged: summary.flagged + (result.findings.length > 0 ? 1 : 0),
        };
      },
      { clean: 0, flagged: 0 },
    );
  }, []);

  const hateRows = reviewSeedItems.filter((item) => item.classifierLabel === 'hate').length;

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
              <Text style={styles.eyebrow}>Frozen MVP</Text>
              <Text style={styles.title}>Glimo review console</Text>
            </View>
          </View>
          <View style={styles.statusPill}>
            <View style={styles.statusDot} />
            <Text style={styles.statusText}>{frozenBatch.validationStatus}</Text>
          </View>
        </View>

        <View style={[styles.metricsGrid, isWide && styles.metricsGridWide]}>
          <Metric label="Rows" value={String(frozenBatch.rows)} tone="blue" />
          <Metric label="Changed text" value={String(frozenBatch.changedTextCells)} tone="mint" />
          <Metric label="Private score" value={frozenBatch.baselineScore} tone="amber" />
          <Metric label="Review queue" value={`${reviewSeedItems.length} seeded`} tone="coral" />
        </View>

        <View style={[styles.contentGrid, isWide && styles.contentGridWide]}>
          <View style={styles.panel}>
            <Text style={styles.panelTitle}>Baseline run</Text>
            <Text style={styles.panelCopy}>{frozenBatch.currentStage}</Text>
            <View style={styles.pathBox}>
              <Text style={styles.pathLabel}>Input</Text>
              <Text style={styles.pathText}>{frozenBatch.sourceCsv}</Text>
            </View>
            <View style={styles.pathBox}>
              <Text style={styles.pathLabel}>Output</Text>
              <Text style={styles.pathText}>{frozenBatch.protectedCsv}</Text>
            </View>
            <View style={styles.stepList}>
              {pipelineSteps.map((step, index) => (
                <View key={step} style={styles.stepRow}>
                  <Text style={styles.stepNumber}>{index + 1}</Text>
                  <Text style={styles.stepText}>{step}</Text>
                </View>
              ))}
            </View>
          </View>

          <View style={styles.panel}>
            <Text style={styles.panelTitle}>Restatement model</Text>
            <Text style={styles.panelCopy}>
              The admin picks the model. Citizen reviewers only see guarded restatements.
            </Text>
            <View style={styles.modelList}>
              {restatementModels.map((model) => {
                const selected = model === selectedModel;
                return (
                  <Pressable
                    key={model}
                    onPress={() => setSelectedModel(model)}
                    style={[styles.modelButton, selected && styles.modelButtonSelected]}>
                    <Text style={[styles.modelText, selected && styles.modelTextSelected]}>
                      {model}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <Pressable
              onPress={() => setGuardStrict((value) => !value)}
              style={[styles.toggleRow, guardStrict && styles.toggleRowActive]}>
              <View style={[styles.toggleKnob, guardStrict && styles.toggleKnobActive]} />
              <Text style={styles.toggleText}>
                Restatement PII leakage guard {guardStrict ? 'on' : 'off'}
              </Text>
            </Pressable>
          </View>
        </View>

        <View style={[styles.contentGrid, isWide && styles.contentGridWide]}>
          <View style={styles.panel}>
            <Text style={styles.panelTitle}>Citizen queue</Text>
            <Text style={styles.panelCopy}>
              {hateRows} classifier-positive cases and {reviewSeedItems.length - hateRows}{' '}
              classifier-negative cases are ready for balanced review.
            </Text>
            {reviewSeedItems.map((item) => {
              const result = guardRestatement(item.restatement);
              return (
                <View key={item.id} style={styles.queueRow}>
                  <View>
                    <Text style={styles.queueTitle}>{item.id}</Text>
                    <Text style={styles.queueMeta}>
                      {item.source} / {item.classifierLabel} / {item.riskLevel}
                    </Text>
                  </View>
                  <Text style={styles.queueGuard}>{summarizeGuard(result.findings)}</Text>
                </View>
              );
            })}
          </View>

          <View style={styles.panel}>
            <View style={styles.guardHeader}>
              <Image
                source={require('@/assets/glimo_mascot.png')}
                style={styles.guardMascot}
                contentFit="contain"
              />
              <View style={styles.guardHeaderCopy}>
                <Text style={styles.panelTitle}>Glimo guard</Text>
                <Text style={styles.panelCopy}>
                  Every restatement is checked before it reaches the swipe deck.
                </Text>
              </View>
            </View>
            <View style={styles.guardScore}>
              <Text style={styles.guardNumber}>{guardSummary.clean}</Text>
              <Text style={styles.guardLabel}>clean restatements</Text>
            </View>
            <View style={styles.guardScoreMuted}>
              <Text style={styles.guardNumberMuted}>{guardSummary.flagged}</Text>
              <Text style={styles.guardLabel}>flagged before citizen review</Text>
            </View>
            <Text style={styles.panelCopy}>
              Guard checks run after restatement and before a card enters the review deck.
              Direct identifiers are remasked and findings stay in admin audit data.
            </Text>
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
  },
  eyebrow: {
    color: AppColors.coral,
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0,
  },
  title: {
    color: AppColors.ink,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '800',
    marginTop: 4,
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: AppColors.panel,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: AppColors.mint,
  },
  statusText: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '700',
    textTransform: 'uppercase',
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
    padding: 16,
    minHeight: 88,
    justifyContent: 'space-between',
  },
  metricLabel: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '700',
  },
  metricValue: {
    color: AppColors.ink,
    fontSize: 24,
    lineHeight: 30,
    fontWeight: '900',
    marginTop: 12,
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
    backgroundColor: 'rgba(255, 255, 255, 0.94)',
    borderRadius: 8,
    padding: 18,
    borderWidth: 1,
    borderColor: AppColors.line,
    gap: 14,
  },
  panelTitle: {
    color: AppColors.ink,
    fontSize: 18,
    fontWeight: '900',
  },
  panelCopy: {
    color: AppColors.muted,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '500',
  },
  pathBox: {
    backgroundColor: '#F9FAFB',
    borderRadius: 8,
    padding: 12,
    borderWidth: 1,
    borderColor: AppColors.line,
    gap: 4,
  },
  pathLabel: {
    color: AppColors.muted,
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  pathText: {
    color: AppColors.ink,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '700',
  },
  stepList: {
    gap: 10,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  stepNumber: {
    width: 24,
    height: 24,
    borderRadius: 12,
    textAlign: 'center',
    lineHeight: 24,
    color: AppColors.panel,
    backgroundColor: AppColors.ink,
    fontSize: 12,
    fontWeight: '900',
  },
  stepText: {
    color: AppColors.slate,
    fontSize: 14,
    fontWeight: '700',
    flex: 1,
  },
  modelList: {
    gap: 8,
  },
  modelButton: {
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    backgroundColor: '#F9FAFB',
  },
  modelButtonSelected: {
    borderColor: AppColors.mint,
    backgroundColor: AppColors.mintSoft,
  },
  modelText: {
    color: AppColors.slate,
    fontWeight: '700',
    fontSize: 14,
  },
  modelTextSelected: {
    color: AppColors.ink,
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    padding: 12,
  },
  toggleRowActive: {
    borderColor: AppColors.mint,
  },
  toggleKnob: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: AppColors.line,
  },
  toggleKnobActive: {
    backgroundColor: AppColors.mint,
  },
  toggleText: {
    color: AppColors.slate,
    fontWeight: '800',
    fontSize: 14,
    flex: 1,
  },
  queueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderTopWidth: 1,
    borderTopColor: AppColors.line,
    paddingTop: 12,
  },
  queueTitle: {
    color: AppColors.ink,
    fontSize: 14,
    fontWeight: '900',
  },
  queueMeta: {
    color: AppColors.muted,
    fontSize: 12,
    fontWeight: '700',
    marginTop: 2,
  },
  queueGuard: {
    color: AppColors.mint,
    fontSize: 12,
    fontWeight: '900',
    textAlign: 'right',
    maxWidth: 150,
  },
  guardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  guardMascot: {
    width: 68,
    height: 76,
  },
  guardHeaderCopy: {
    flex: 1,
    gap: 4,
  },
  guardScore: {
    backgroundColor: AppColors.mintSoft,
    borderRadius: 8,
    padding: 16,
  },
  guardScoreMuted: {
    backgroundColor: '#F9FAFB',
    borderRadius: 8,
    padding: 16,
  },
  guardNumber: {
    color: AppColors.mint,
    fontSize: 38,
    lineHeight: 44,
    fontWeight: '900',
  },
  guardNumberMuted: {
    color: AppColors.slate,
    fontSize: 38,
    lineHeight: 44,
    fontWeight: '900',
  },
  guardLabel: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '800',
    marginTop: 4,
  },
});
