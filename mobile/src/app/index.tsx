import { Redirect } from 'expo-router';

import { AuthScreen } from '@/components/auth-screen';
import { isStaticReviewMode } from '@/config/runtime';

export default function LoginScreen() {
  if (isStaticReviewMode) {
    return <Redirect href="/review" />;
  }

  return <AuthScreen mode="login" />;
}
