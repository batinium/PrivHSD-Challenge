import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { useColorScheme } from 'react-native';

import { OnboardingProvider } from '@/state/onboarding';
import { ReviewProgressProvider } from '@/state/review-progress';

export default function RootLayout() {
  const colorScheme = useColorScheme();
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <OnboardingProvider>
        <ReviewProgressProvider>
          <Stack screenOptions={{ headerShown: false }} />
        </ReviewProgressProvider>
      </OnboardingProvider>
    </ThemeProvider>
  );
}
