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

type LectureSection = {
  id: string;
  title: string;
  body: string;
  examples: string[];
};

type Lecture = {
  id: string;
  title: string;
  level: string;
  duration: string;
  summary: string;
  goals: string[];
  sections: LectureSection[];
  signals: { label: string; detail: string }[];
  checkpoint: {
    question: string;
    answerId: string;
    options: { id: string; label: string; text: string }[];
    explanation: string;
  };
  glossary: { term: string; definition: string }[];
};

const lectures: Lecture[] = [
  {
    id: 'foundations',
    title: 'Foundations of Hate Speech Detection',
    level: 'Intro',
    duration: '18 min',
    summary:
      'A practical walkthrough of what reviewers should preserve, what they should ignore, and why context matters.',
    goals: [
      'Separate protected-group targeting from general profanity.',
      'Identify whether a comment attacks identity, behavior, or policy.',
      'Use uncertainty when the masked text loses the target or direction.',
    ],
    sections: [
      {
        id: 'scope',
        title: 'Scope and Targeting',
        body:
          'Hate speech review starts with the target. A harsh insult is not enough by itself; the comment must attack, demean, exclude, or threaten a protected identity group or a person because of that identity.',
        examples: [
          'Identity target: a comment blames a protected group for social harm.',
          'Non-identity target: a comment insults a public figure for a decision.',
          'Borderline target: a masked text says "those people" without enough context.',
        ],
      },
      {
        id: 'context',
        title: 'Context and Direction',
        body:
          'Direction tells reviewers who is speaking about whom. Quotation, counterspeech, reported abuse, satire, and sarcasm can reverse the meaning, so reviewers should not rely on isolated words alone.',
        examples: [
          'Counterspeech can repeat slurs while condemning them.',
          'Reported abuse can describe harm without endorsing it.',
          'Sarcasm can be risky when the masked text removes the setup.',
        ],
      },
      {
        id: 'decision',
        title: 'Decision Boundaries',
        body:
          'A YES decision means the protected restatement still describes hate speech. A NO decision means the text is offensive, political, or rude without protected-group targeting. REVIEW is for missing target, missing direction, or weak evidence.',
        examples: [
          'YES: dehumanizing or exclusionary language aimed at a protected group.',
          'NO: criticism of an ideology, policy, company, or individual behavior.',
          'REVIEW: target is replaced so heavily that intent cannot be recovered.',
        ],
      },
    ],
    signals: [
      {
        label: 'Target cue',
        detail: 'Look for the identity group or protected trait the comment is about.',
      },
      {
        label: 'Attack verb',
        detail: 'Check whether the text insults, threatens, excludes, or dehumanizes.',
      },
      {
        label: 'Speaker stance',
        detail: 'Confirm whether the author endorses the attack or reports it.',
      },
    ],
    checkpoint: {
      question:
        'A masked text says a group should be excluded from a public service because of identity. What is the strongest review decision?',
      answerId: 'yes',
      options: [
        { id: 'yes', label: 'A', text: 'YES, protected-group exclusion is still visible.' },
        { id: 'no', label: 'B', text: 'NO, because all direct names were removed.' },
        { id: 'review', label: 'C', text: 'REVIEW, because the text is political.' },
      ],
      explanation:
        'The protected target and exclusionary action are still visible, so the masked variant keeps enough evidence for YES.',
    },
    glossary: [
      {
        term: 'Protected target',
        definition: 'A person or group referenced by protected identity or perceived identity.',
      },
      {
        term: 'Counterspeech',
        definition: 'Language that quotes or references hate speech to reject or criticize it.',
      },
      {
        term: 'Directionality',
        definition: 'The relationship between speaker, target, and claim in the comment.',
      },
    ],
  },
  {
    id: 'workflow',
    title: 'Model Signals, Privacy, and Review Workflows',
    level: 'Applied',
    duration: '22 min',
    summary:
      'A guided example of how masked text, restatements, classifier confidence, and admin triage fit together.',
    goals: [
      'Read masked variants without over-trusting generated restatements.',
      'Use classifier confidence as a signal, not a final answer.',
      'Escalate cases when masking removes identity, stance, or severity.',
    ],
    sections: [
      {
        id: 'privacy',
        title: 'Privacy Layer',
        body:
          'The privacy layer reduces exposure to personal or high-risk details while keeping enough semantic evidence for review. Good masking removes identifiers without flattening the target, action, or stance.',
        examples: [
          'Useful masking keeps "attacks a religious group" visible.',
          'Over-masking turns the target into a vague phrase with no review value.',
          'Residual leakage can leave a direct person, place, or unique event exposed.',
        ],
      },
      {
        id: 'signals',
        title: 'Classifier and Audit Signals',
        body:
          'Classifier scores help prioritize work, but they are not a verdict. Deviation audit signals flag restatements that may have dropped target cues, offensive cues, or context terms.',
        examples: [
          'High score plus low drift can be reviewed quickly.',
          'High score plus medium drift needs closer reading.',
          'Low score with explicit targeting can still be YES.',
        ],
      },
      {
        id: 'triage',
        title: 'Admin Triage',
        body:
          'Admins compare scrubbed text and restatements, inspect missing terms, and decide whether a row is approved, sent to lookup, held, or returned to training. The goal is a clean public review queue.',
        examples: [
          'Approve when masking is privacy-safe and meaning is preserved.',
          'Lookup when terms were lost but source context may resolve it.',
          'Train when the case reveals a repeatable model or masking failure.',
        ],
      },
    ],
    signals: [
      {
        label: 'Deviation risk',
        detail: 'A compact warning for source-to-restatement meaning loss.',
      },
      {
        label: 'Token highlights',
        detail: 'Terms likely driving classifier behavior or audit attention.',
      },
      {
        label: 'Vote spread',
        detail: 'Reviewer disagreement that may reveal ambiguity or UI confusion.',
      },
    ],
    checkpoint: {
      question:
        'A restatement reads cleanly, but the audit says target cue loss and the scrubbed text shows the target only as a placeholder. What should the reviewer do?',
      answerId: 'review',
      options: [
        { id: 'yes', label: 'A', text: 'YES, because the model score is high.' },
        { id: 'no', label: 'B', text: 'NO, because the restatement is clean.' },
        { id: 'review', label: 'C', text: 'REVIEW, because key evidence is missing.' },
      ],
      explanation:
        'When target evidence is lost, the safest review action is REVIEW. The admin console can inspect source context and correct the pipeline.',
    },
    glossary: [
      {
        term: 'Scrubbed text',
        definition: 'The masked or privacy-filtered variant used to reduce sensitive exposure.',
      },
      {
        term: 'Restatement',
        definition: 'A generated description that should preserve meaning while avoiding direct source text.',
      },
      {
        term: 'Deviation audit',
        definition: 'A structured check for meaning loss between source, scrubbed text, and restatement.',
      },
    ],
  },
];

export default function LibraryScreen() {
  const { width } = useWindowDimensions();
  const isWide = width >= 920;
  const [selectedLectureId, setSelectedLectureId] = useState(lectures[0].id);
  const [selectedSectionId, setSelectedSectionId] = useState(lectures[0].sections[0].id);
  const [checkpointAnswers, setCheckpointAnswers] = useState<Record<string, string>>({});

  const selectedLecture = useMemo(
    () => lectures.find((lecture) => lecture.id === selectedLectureId) ?? lectures[0],
    [selectedLectureId],
  );
  const selectedSection =
    selectedLecture.sections.find((section) => section.id === selectedSectionId) ??
    selectedLecture.sections[0];
  const selectedAnswerId = checkpointAnswers[selectedLecture.id];
  const answeredCorrectly = selectedAnswerId === selectedLecture.checkpoint.answerId;

  function selectLecture(lecture: Lecture) {
    setSelectedLectureId(lecture.id);
    setSelectedSectionId(lecture.sections[0].id);
  }

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
              <Text style={styles.eyebrow}>Reviewer library</Text>
              <Text style={styles.title}>Hate speech detection lectures</Text>
            </View>
          </View>
          <View style={styles.countPill}>
            <Text style={styles.countPillValue}>{lectures.length}</Text>
            <Text style={styles.countPillLabel}>lectures</Text>
          </View>
        </View>

        <View style={[styles.heroBand, isWide && styles.heroBandWide]}>
          <View style={styles.heroCopy}>
            <Text style={styles.heroLabel}>Current lecture</Text>
            <Text style={styles.heroTitle}>{selectedLecture.title}</Text>
            <Text style={styles.heroSummary}>{selectedLecture.summary}</Text>
          </View>
          <View style={styles.heroStats}>
            <View style={styles.statBox}>
              <Text style={styles.statValue}>{selectedLecture.level}</Text>
              <Text style={styles.statLabel}>level</Text>
            </View>
            <View style={styles.statBox}>
              <Text style={styles.statValue}>{selectedLecture.duration}</Text>
              <Text style={styles.statLabel}>time</Text>
            </View>
            <View style={styles.statBox}>
              <Text style={styles.statValue}>{selectedLecture.sections.length}</Text>
              <Text style={styles.statLabel}>modules</Text>
            </View>
          </View>
        </View>

        <View style={[styles.libraryShell, isWide && styles.libraryShellWide]}>
          <View style={[styles.lectureRail, isWide && styles.lectureRailWide]}>
            <Text style={styles.railTitle}>Lecture set</Text>
            {lectures.map((lecture) => {
              const selected = lecture.id === selectedLecture.id;
              return (
                <Pressable
                  key={lecture.id}
                  onPress={() => selectLecture(lecture)}
                  style={({ pressed }) => [
                    styles.lectureTile,
                    selected && styles.lectureTileSelected,
                    pressed && styles.pressed,
                  ]}>
                  <View style={styles.lectureTileTop}>
                    <Text style={[styles.levelBadge, selected && styles.levelBadgeSelected]}>
                      {lecture.level}
                    </Text>
                    <Text style={styles.lectureTime}>{lecture.duration}</Text>
                  </View>
                  <Text style={styles.lectureTitle}>{lecture.title}</Text>
                  <Text style={styles.lectureSummary}>{lecture.summary}</Text>
                </Pressable>
              );
            })}
          </View>

          <View style={styles.lessonMain}>
            <View style={styles.lessonHeader}>
              <Text style={styles.moduleEyebrow}>Learning goals</Text>
              <View style={[styles.goalsGrid, isWide && styles.goalsGridWide]}>
                {selectedLecture.goals.map((goal) => (
                  <View key={goal} style={styles.goalItem}>
                    <View style={styles.goalMarker} />
                    <Text style={styles.goalText}>{goal}</Text>
                  </View>
                ))}
              </View>
            </View>

            <View style={styles.sectionTabs}>
              {selectedLecture.sections.map((section) => {
                const selected = section.id === selectedSection.id;
                return (
                  <Pressable
                    key={section.id}
                    onPress={() => setSelectedSectionId(section.id)}
                    style={({ pressed }) => [
                      styles.sectionTab,
                      selected && styles.sectionTabSelected,
                      pressed && styles.pressed,
                    ]}>
                    <Text
                      style={[
                        styles.sectionTabText,
                        selected && styles.sectionTabTextSelected,
                      ]}>
                      {section.title}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            <View style={styles.contentBand}>
              <Text style={styles.sectionTitle}>{selectedSection.title}</Text>
              <Text style={styles.sectionBody}>{selectedSection.body}</Text>
              <View style={styles.exampleList}>
                {selectedSection.examples.map((example, index) => (
                  <View key={example} style={styles.exampleRow}>
                    <Text style={styles.exampleIndex}>{String(index + 1).padStart(2, '0')}</Text>
                    <Text style={styles.exampleText}>{example}</Text>
                  </View>
                ))}
              </View>
            </View>

            <View style={[styles.signalGrid, isWide && styles.signalGridWide]}>
              {selectedLecture.signals.map((signal) => (
                <View key={signal.label} style={styles.signalPanel}>
                  <Text style={styles.signalTitle}>{signal.label}</Text>
                  <Text style={styles.signalText}>{signal.detail}</Text>
                </View>
              ))}
            </View>

            <View style={styles.checkpointBand}>
              <Text style={styles.moduleEyebrow}>Checkpoint</Text>
              <Text style={styles.checkpointQuestion}>{selectedLecture.checkpoint.question}</Text>
              <View style={styles.answerGrid}>
                {selectedLecture.checkpoint.options.map((option) => {
                  const selected = selectedAnswerId === option.id;
                  const correct = option.id === selectedLecture.checkpoint.answerId;
                  return (
                    <Pressable
                      key={option.id}
                      onPress={() =>
                        setCheckpointAnswers((current) => ({
                          ...current,
                          [selectedLecture.id]: option.id,
                        }))
                      }
                      style={({ pressed }) => [
                        styles.answerOption,
                        selected && styles.answerOptionSelected,
                        selected && correct && styles.answerOptionCorrect,
                        pressed && styles.pressed,
                      ]}>
                      <Text
                        style={[
                          styles.answerLetter,
                          selected && correct && styles.answerLetterCorrect,
                        ]}>
                        {option.label}
                      </Text>
                      <Text style={styles.answerText}>{option.text}</Text>
                    </Pressable>
                  );
                })}
              </View>
              {selectedAnswerId ? (
                <View
                  style={[
                    styles.feedbackPanel,
                    answeredCorrectly ? styles.feedbackCorrect : styles.feedbackReview,
                  ]}>
                  <Text style={styles.feedbackTitle}>
                    {answeredCorrectly ? 'Correct' : 'Needs review'}
                  </Text>
                  <Text style={styles.feedbackText}>{selectedLecture.checkpoint.explanation}</Text>
                </View>
              ) : null}
            </View>

            <View style={styles.glossaryGrid}>
              {selectedLecture.glossary.map((item) => (
                <View key={item.term} style={styles.glossaryItem}>
                  <Text style={styles.glossaryTerm}>{item.term}</Text>
                  <Text style={styles.glossaryDefinition}>{item.definition}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

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
  countPill: {
    minWidth: 82,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#F4D96B',
    backgroundColor: AppColors.goldSoft,
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  countPillValue: {
    color: AppColors.ink,
    fontSize: 24,
    lineHeight: 28,
    fontWeight: '900',
  },
  countPillLabel: {
    color: AppColors.muted,
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  heroBand: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: 'rgba(255, 255, 255, 0.95)',
    padding: 18,
    gap: 16,
  },
  heroBandWide: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  heroCopy: {
    flex: 1,
    gap: 6,
  },
  heroLabel: {
    color: AppColors.mint,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  heroTitle: {
    color: AppColors.ink,
    fontSize: 26,
    lineHeight: 32,
    fontWeight: '900',
  },
  heroSummary: {
    color: AppColors.slate,
    fontSize: 15,
    lineHeight: 22,
    maxWidth: 720,
  },
  heroStats: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  statBox: {
    minWidth: 86,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.blueSoft,
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  statValue: {
    color: AppColors.ink,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '900',
  },
  statLabel: {
    color: AppColors.muted,
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
    marginTop: 2,
  },
  libraryShell: {
    gap: 16,
  },
  libraryShellWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  lectureRail: {
    gap: 10,
  },
  lectureRailWide: {
    width: 300,
    flexShrink: 0,
  },
  railTitle: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  lectureTile: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.panel,
    padding: 14,
    gap: 8,
  },
  lectureTileSelected: {
    borderColor: AppColors.blue,
    backgroundColor: AppColors.blueSoft,
  },
  lectureTileTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  levelBadge: {
    overflow: 'hidden',
    borderRadius: 8,
    backgroundColor: AppColors.mintSoft,
    color: AppColors.mint,
    fontSize: 11,
    fontWeight: '900',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'uppercase',
  },
  levelBadgeSelected: {
    backgroundColor: AppColors.panel,
    color: AppColors.blue,
  },
  lectureTime: {
    color: AppColors.muted,
    fontSize: 12,
    fontWeight: '800',
  },
  lectureTitle: {
    color: AppColors.ink,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '900',
  },
  lectureSummary: {
    color: AppColors.slate,
    fontSize: 13,
    lineHeight: 19,
  },
  lessonMain: {
    flex: 1,
    gap: 14,
    minWidth: 0,
  },
  lessonHeader: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: 'rgba(255, 255, 255, 0.95)',
    padding: 16,
    gap: 12,
  },
  moduleEyebrow: {
    color: AppColors.coral,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  goalsGrid: {
    gap: 10,
  },
  goalsGridWide: {
    flexDirection: 'row',
  },
  goalItem: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    borderRadius: 8,
    backgroundColor: AppColors.paper,
    padding: 12,
  },
  goalMarker: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: AppColors.gold,
    marginTop: 6,
  },
  goalText: {
    flex: 1,
    color: AppColors.slate,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '700',
  },
  sectionTabs: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  sectionTab: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.panel,
    paddingVertical: 9,
    paddingHorizontal: 12,
  },
  sectionTabSelected: {
    borderColor: AppColors.blue,
    backgroundColor: AppColors.blue,
  },
  sectionTabText: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '900',
  },
  sectionTabTextSelected: {
    color: AppColors.panel,
  },
  contentBand: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.panel,
    padding: 18,
    gap: 12,
  },
  sectionTitle: {
    color: AppColors.ink,
    fontSize: 24,
    lineHeight: 30,
    fontWeight: '900',
  },
  sectionBody: {
    color: AppColors.slate,
    fontSize: 15,
    lineHeight: 23,
  },
  exampleList: {
    gap: 8,
  },
  exampleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    borderRadius: 8,
    backgroundColor: AppColors.paper,
    padding: 12,
  },
  exampleIndex: {
    color: AppColors.blue,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '900',
  },
  exampleText: {
    flex: 1,
    color: AppColors.ink,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
  signalGrid: {
    gap: 10,
  },
  signalGridWide: {
    flexDirection: 'row',
  },
  signalPanel: {
    flex: 1,
    minWidth: 0,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.mintSoft,
    padding: 14,
    gap: 6,
  },
  signalTitle: {
    color: AppColors.mint,
    fontSize: 13,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  signalText: {
    color: AppColors.ink,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '700',
  },
  checkpointBand: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#F4D96B',
    backgroundColor: AppColors.goldSoft,
    padding: 16,
    gap: 12,
  },
  checkpointQuestion: {
    color: AppColors.ink,
    fontSize: 18,
    lineHeight: 25,
    fontWeight: '900',
  },
  answerGrid: {
    gap: 8,
  },
  answerOption: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.panel,
    padding: 12,
  },
  answerOptionSelected: {
    borderColor: AppColors.coral,
    backgroundColor: AppColors.coralSoft,
  },
  answerOptionCorrect: {
    borderColor: AppColors.mint,
    backgroundColor: AppColors.mintSoft,
  },
  answerLetter: {
    width: 24,
    height: 24,
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: AppColors.blueSoft,
    color: AppColors.blue,
    textAlign: 'center',
    fontSize: 13,
    lineHeight: 24,
    fontWeight: '900',
  },
  answerLetterCorrect: {
    backgroundColor: AppColors.mint,
    color: AppColors.panel,
  },
  answerText: {
    flex: 1,
    color: AppColors.ink,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
  feedbackPanel: {
    borderRadius: 8,
    borderWidth: 1,
    padding: 12,
    gap: 4,
  },
  feedbackCorrect: {
    borderColor: '#A7DED4',
    backgroundColor: AppColors.mintSoft,
  },
  feedbackReview: {
    borderColor: '#F3B6C2',
    backgroundColor: AppColors.coralSoft,
  },
  feedbackTitle: {
    color: AppColors.ink,
    fontSize: 14,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  feedbackText: {
    color: AppColors.slate,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '700',
  },
  glossaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  glossaryItem: {
    flexGrow: 1,
    flexBasis: 220,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.panel,
    padding: 14,
    gap: 6,
  },
  glossaryTerm: {
    color: AppColors.blue,
    fontSize: 14,
    fontWeight: '900',
  },
  glossaryDefinition: {
    color: AppColors.slate,
    fontSize: 13,
    lineHeight: 19,
  },
  pressed: {
    opacity: 0.75,
  },
});
