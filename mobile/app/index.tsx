/**
 * Root index route – redirects to the auth flow on launch.
 *
 * expo-router renders this when the "/" route is matched (i.e. on cold start).
 * Without this file, a stale default scaffold page ("Hello World") can appear
 * if one was left behind by a previous build or Expo CLI scaffolding.
 *
 * The redirect targets the (auth) group; the AuthGuard in _layout.tsx will
 * immediately forward authenticated users to (tabs).
 */

import { Redirect } from "expo-router";
import React from "react";

export default function RootIndex() {
  return <Redirect href="/(auth)/" />;
}
