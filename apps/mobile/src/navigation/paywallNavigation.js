import { StackActions } from '@react-navigation/native';

function getRootNavigation(navigation) {
  let currentNavigation = navigation;

  while (currentNavigation?.getParent?.()) {
    currentNavigation = currentNavigation.getParent();
  }

  return currentNavigation;
}

export function presentPlans(navigation, params) {
  const rootNavigation = getRootNavigation(navigation);

  if (!rootNavigation?.dispatch) {
    return false;
  }

  const rootState = rootNavigation.getState?.();
  const activeRoute =
    rootState?.routes?.[rootState.index];

  if (activeRoute?.name === 'Plans') {
    return false;
  }

  rootNavigation.dispatch(
    StackActions.push('Plans', params)
  );

  return true;
}
