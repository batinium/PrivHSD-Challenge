import { router } from 'expo-router';
import { Image } from 'expo-image';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { GlimoShieldBackground } from '@/components/glimo-shield-background';
import { AppColors } from '@/constants/theme';

type AuthMode = 'login' | 'signup';
type LoginRole = 'Admin' | 'Reviewer';

const captchaCodes = ['GLIMO', 'SHIELD', 'REVIEW'] as const;

type AuthScreenProps = {
  mode: AuthMode;
};

export function AuthScreen({ mode }: AuthScreenProps) {
  const { width } = useWindowDimensions();
  const isWide = width >= 820;
  const isSignup = mode === 'signup';
  const [role, setRole] = useState<LoginRole>('Reviewer');
  const [remember, setRemember] = useState(true);
  const [agreementAccepted, setAgreementAccepted] = useState(false);
  const [captchaIndex, setCaptchaIndex] = useState(0);
  const [email, setEmail] = useState('');
  const [emailConfirmation, setEmailConfirmation] = useState('');
  const [password, setPassword] = useState('');
  const [captchaResponse, setCaptchaResponse] = useState('');

  const captchaCode = captchaCodes[captchaIndex];

  function continueToConsole() {
    router.replace('/console');
  }

  function goToAlternateAuth() {
    if (isSignup) {
      router.replace('/');
    } else {
      router.push('/signup');
    }
  }

  function refreshCaptcha() {
    setCaptchaIndex((current) => (current + 1) % captchaCodes.length);
    setCaptchaResponse('');
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <GlimoShieldBackground />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.keyboardView}>
        <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
          <View style={[styles.shell, isWide && styles.shellWide]}>
            <View style={[styles.brandPanel, isWide && styles.brandPanelWide]}>
              <Image
                source={require('@/assets/glimo_mascot_text_below.png')}
                style={styles.brandMascot}
                contentFit="contain"
              />
              <View style={styles.brandCopy}>
                <Text style={styles.eyebrow}>Protected review</Text>
                <Text style={styles.title}>Glimo access</Text>
                <Text style={styles.subtitle}>
                  {isSignup
                    ? 'Create access for the review workspace.'
                    : 'Sign in to continue to the review workspace.'}
                </Text>
              </View>
              <View style={styles.statusRow}>
                <View style={styles.statusDot} />
                <Text style={styles.statusText}>Local demo environment</Text>
              </View>
            </View>

            <View style={styles.formCard}>
              <View style={styles.formHeader}>
                <Text style={styles.formTitle}>{isSignup ? 'Create account' : 'Sign in'}</Text>
                <Text style={styles.formSubtitle}>
                  {isSignup ? 'Request reviewer access.' : 'Use your reviewer account.'}
                </Text>
              </View>

              <View style={styles.fieldGroup}>
                <Text style={styles.label}>Email</Text>
                <TextInput
                  autoCapitalize="none"
                  autoComplete="email"
                  keyboardType="email-address"
                  onChangeText={setEmail}
                  placeholder="name@team.org"
                  placeholderTextColor={AppColors.muted}
                  style={styles.input}
                  value={email}
                />
              </View>

              {isSignup && (
                <View style={styles.fieldGroup}>
                  <Text style={styles.label}>Retype email</Text>
                  <TextInput
                    autoCapitalize="none"
                    autoComplete="email"
                    keyboardType="email-address"
                    onChangeText={setEmailConfirmation}
                    placeholder="name@team.org"
                    placeholderTextColor={AppColors.muted}
                    style={styles.input}
                    value={emailConfirmation}
                  />
                </View>
              )}

              <View style={styles.fieldGroup}>
                <Text style={styles.label}>Password</Text>
                <TextInput
                  autoCapitalize="none"
                  onChangeText={setPassword}
                  placeholder="Password"
                  placeholderTextColor={AppColors.muted}
                  secureTextEntry
                  style={styles.input}
                  value={password}
                />
              </View>

              {!isSignup && (
                <View style={styles.roleControl}>
                  {(['Reviewer', 'Admin'] as const).map((option) => {
                    const selected = option === role;
                    return (
                      <Pressable
                        key={option}
                        onPress={() => setRole(option)}
                        style={[styles.roleButton, selected && styles.roleButtonSelected]}>
                        <Text style={[styles.roleText, selected && styles.roleTextSelected]}>
                          {option}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              )}

              <View style={styles.captchaPanel}>
                <View style={styles.captchaHeader}>
                  <View>
                    <Text style={styles.label}>Captcha</Text>
                    <Text style={styles.captchaHelp}>Type the code shown below.</Text>
                  </View>
                  <Pressable onPress={refreshCaptcha}>
                    <Text style={styles.linkText}>Refresh</Text>
                  </Pressable>
                </View>
                <View style={styles.captchaChallenge}>
                  <Text style={styles.captchaCode}>{captchaCode}</Text>
                </View>
                <TextInput
                  autoCapitalize="characters"
                  onChangeText={setCaptchaResponse}
                  placeholder="Enter captcha"
                  placeholderTextColor={AppColors.muted}
                  style={styles.input}
                  value={captchaResponse}
                />
              </View>

              {!isSignup && (
                <View style={styles.formOptions}>
                  <Pressable onPress={() => setRemember((value) => !value)} style={styles.remember}>
                    <View style={[styles.checkbox, remember && styles.checkboxChecked]}>
                      {remember && <View style={styles.checkboxFill} />}
                    </View>
                    <Text style={styles.rememberText}>Remember this device</Text>
                  </Pressable>
                  <Pressable onPress={goToAlternateAuth}>
                    <Text style={styles.linkText}>Need access?</Text>
                  </Pressable>
                </View>
              )}

              {isSignup && (
                <View style={styles.legalBox}>
                  <AgreementCheckbox
                    checked={agreementAccepted}
                    onPress={() => setAgreementAccepted((value) => !value)}
                  />
                  <View style={styles.legalLinks}>
                    <Text style={styles.legalPrefix}>Legal:</Text>
                    <Pressable>
                      <Text style={styles.legalLink}>User Agreement</Text>
                    </Pressable>
                    <Pressable>
                      <Text style={styles.legalLink}>Terms of Use</Text>
                    </Pressable>
                    <Pressable>
                      <Text style={styles.legalLink}>Conditions</Text>
                    </Pressable>
                    <Pressable>
                      <Text style={styles.legalLink}>Privacy Policy</Text>
                    </Pressable>
                  </View>
                </View>
              )}

              <Pressable onPress={continueToConsole} style={styles.primaryButton}>
                <Text style={styles.primaryButtonText}>
                  {isSignup ? 'Create account' : 'Sign in'}
                </Text>
              </Pressable>

              {isSignup ? (
                <Pressable onPress={goToAlternateAuth} style={styles.secondaryAction}>
                  <Text style={styles.secondaryActionText}>Already have an account? Sign in</Text>
                </Pressable>
              ) : (
                <Pressable onPress={goToAlternateAuth} style={styles.secondaryAction}>
                  <Text style={styles.secondaryActionText}>Create a new account</Text>
                </Pressable>
              )}

              <Text style={styles.footerNote}>
                {isSignup
                  ? 'Account creation is disabled for this MVP build.'
                  : 'Authentication is disabled for this MVP build.'}
              </Text>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

type AgreementCheckboxProps = {
  checked: boolean;
  onPress: () => void;
};

function AgreementCheckbox({ checked, onPress }: AgreementCheckboxProps) {
  return (
    <Pressable onPress={onPress} style={styles.agreementRow}>
      <View style={[styles.checkbox, checked && styles.checkboxChecked]}>
        {checked && <View style={styles.checkboxFill} />}
      </View>
      <Text style={styles.agreementText}>
        I hereby agree with User Agreement and have read Privacy Policy.
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: AppColors.paper,
    overflow: 'hidden',
  },
  keyboardView: {
    flex: 1,
  },
  page: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 20,
  },
  shell: {
    width: '100%',
    maxWidth: 1080,
    alignSelf: 'center',
    gap: 16,
  },
  shellWide: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  brandPanel: {
    backgroundColor: 'rgba(255, 255, 255, 0.92)',
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    padding: 22,
    gap: 16,
    overflow: 'hidden',
  },
  brandPanelWide: {
    flex: 1,
    justifyContent: 'space-between',
    minHeight: 480,
  },
  brandMascot: {
    width: 132,
    height: 132,
  },
  brandCopy: {
    gap: 8,
  },
  eyebrow: {
    color: AppColors.blue,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  title: {
    color: AppColors.ink,
    fontSize: 42,
    lineHeight: 46,
    fontWeight: '900',
  },
  subtitle: {
    color: AppColors.muted,
    fontSize: 17,
    lineHeight: 25,
    fontWeight: '700',
    maxWidth: 380,
  },
  statusRow: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: AppColors.blueSoft,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#C7D7F0',
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  statusDot: {
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: AppColors.mint,
  },
  statusText: {
    color: AppColors.blue,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  formCard: {
    width: '100%',
    maxWidth: 430,
    alignSelf: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.96)',
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    padding: 22,
    gap: 16,
    shadowColor: '#111827',
    shadowOpacity: 0.16,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 10 },
    elevation: 4,
  },
  formHeader: {
    gap: 6,
  },
  formTitle: {
    color: AppColors.ink,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '900',
  },
  formSubtitle: {
    color: AppColors.muted,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
  fieldGroup: {
    gap: 8,
  },
  label: {
    color: AppColors.slate,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  input: {
    minHeight: 50,
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    backgroundColor: AppColors.paper,
    color: AppColors.ink,
    fontSize: 16,
    fontWeight: '700',
    paddingHorizontal: 14,
  },
  roleControl: {
    flexDirection: 'row',
    backgroundColor: AppColors.paper,
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    padding: 4,
    gap: 4,
  },
  roleButton: {
    flex: 1,
    minHeight: 42,
    borderRadius: 7,
    alignItems: 'center',
    justifyContent: 'center',
  },
  roleButtonSelected: {
    backgroundColor: AppColors.goldSoft,
    borderWidth: 1,
    borderColor: '#F4D96B',
  },
  roleText: {
    color: AppColors.muted,
    fontSize: 14,
    fontWeight: '900',
  },
  roleTextSelected: {
    color: AppColors.ink,
  },
  captchaPanel: {
    gap: 10,
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    backgroundColor: 'rgba(231, 238, 249, 0.64)',
    padding: 12,
  },
  captchaHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
  },
  captchaHelp: {
    color: AppColors.muted,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '700',
  },
  captchaChallenge: {
    minHeight: 48,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#C7D7F0',
    backgroundColor: AppColors.panel,
    alignItems: 'center',
    justifyContent: 'center',
  },
  captchaCode: {
    color: AppColors.blue,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '900',
    letterSpacing: 0,
  },
  formOptions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  remember: {
    flexDirection: 'row',
    alignItems: 'center',
    flexShrink: 1,
    gap: 9,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: AppColors.line,
    backgroundColor: AppColors.panel,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxChecked: {
    backgroundColor: AppColors.mint,
    borderColor: AppColors.mint,
  },
  checkboxFill: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: AppColors.panel,
  },
  rememberText: {
    color: AppColors.slate,
    fontSize: 13,
    fontWeight: '800',
  },
  linkText: {
    color: AppColors.blue,
    fontSize: 13,
    fontWeight: '900',
  },
  legalBox: {
    gap: 10,
    borderWidth: 1,
    borderColor: AppColors.line,
    borderRadius: 8,
    padding: 12,
    backgroundColor: AppColors.paper,
  },
  agreementRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 9,
  },
  agreementText: {
    flex: 1,
    color: AppColors.slate,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '800',
  },
  legalLinks: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 8,
  },
  legalPrefix: {
    color: AppColors.muted,
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  legalLink: {
    color: AppColors.blue,
    fontSize: 12,
    fontWeight: '900',
    textDecorationLine: 'underline',
  },
  primaryButton: {
    minHeight: 52,
    borderRadius: 8,
    backgroundColor: AppColors.ink,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: AppColors.ink,
    shadowOpacity: 0.22,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
  },
  primaryButtonText: {
    color: AppColors.panel,
    fontSize: 16,
    fontWeight: '900',
  },
  secondaryAction: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 34,
  },
  secondaryActionText: {
    color: AppColors.blue,
    fontSize: 13,
    fontWeight: '900',
  },
  footerNote: {
    color: AppColors.muted,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '700',
    textAlign: 'center',
  },
});
