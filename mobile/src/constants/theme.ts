/**
 * Below are the colors that are used in the app. The colors are defined in the light and dark mode.
 * There are many other ways to style your app. For example, [Nativewind](https://www.nativewind.dev/), [Tamagui](https://tamagui.dev/), [unistyles](https://reactnativeunistyles.vercel.app), etc.
 */

import { Platform } from 'react-native';

export const Colors = {
  light: {
    text: '#102044',
    background: '#F6FAFF',
    backgroundElement: '#FFFFFF',
    backgroundSelected: '#FFF1B8',
    textSecondary: '#60718E',
  },
  dark: {
    text: '#F9FAFB',
    background: '#0B1530',
    backgroundElement: '#15213D',
    backgroundSelected: '#2A2B38',
    textSecondary: '#C8D3E8',
  },
} as const;

export const AppColors = {
  ink: '#102044',
  panel: '#FFFFFF',
  paper: '#F6FAFF',
  line: '#DDE6F3',
  muted: '#60718E',
  coral: '#E85D75',
  coralSoft: '#FCE8EC',
  mint: '#2A9D8F',
  mintSoft: '#DFF4EF',
  amber: '#F6C84C',
  amberSoft: '#FFF1B8',
  blue: '#18376D',
  blueSoft: '#E7EEF9',
  gold: '#F7C84B',
  goldSoft: '#FFF7D7',
  slate: '#334663',
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

export const Fonts = Platform.select({
  ios: {
    /** iOS `UIFontDescriptorSystemDesignDefault` */
    sans: 'system-ui',
    /** iOS `UIFontDescriptorSystemDesignSerif` */
    serif: 'ui-serif',
    /** iOS `UIFontDescriptorSystemDesignRounded` */
    rounded: 'ui-rounded',
    /** iOS `UIFontDescriptorSystemDesignMonospaced` */
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: 'var(--font-display)',
    serif: 'var(--font-serif)',
    rounded: 'var(--font-rounded)',
    mono: 'var(--font-mono)',
  },
});

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 64,
} as const;

export const BottomTabInset = Platform.select({ ios: 50, android: 80 }) ?? 0;
export const MaxContentWidth = 800;
