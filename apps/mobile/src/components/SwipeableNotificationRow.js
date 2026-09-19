import React, {
  useCallback,
  useMemo,
  useRef,
} from 'react';

import {
  Animated,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {
  Ionicons,
} from '@expo/vector-icons';

import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';


const ACTION_WIDTH = 88;
const ACTIONS_WIDTH =
  ACTION_WIDTH * 2;


export default function SwipeableNotificationRow({
  item,
  copy,
  onOpen,
  onToggleRead,
  onDelete,
  markReadLabel,
  markUnreadLabel,
  deleteLabel,
}) {
  const translateX =
    useRef(
      new Animated.Value(0)
    ).current;

  const startXRef =
    useRef(0);

  const openRef =
    useRef(false);


  const animateTo =
    useCallback(
      (value) => {
        openRef.current =
          value !== 0;

        Animated.spring(
          translateX,
          {
            toValue: value,
            useNativeDriver: true,
            damping: 22,
            stiffness: 240,
            mass: 0.8,
          }
        ).start();
      },
      [translateX]
    );


  const panResponder =
    useMemo(
      () =>
        PanResponder.create({
          onMoveShouldSetPanResponder:
            (_, gesture) => {
              const horizontal =
                Math.abs(gesture.dx);

              const vertical =
                Math.abs(gesture.dy);

              if (
                horizontal < 8
                || horizontal
                  <= vertical * 1.2
              ) {
                return false;
              }

              return (
                gesture.dx < 0
                || openRef.current
              );
            },

          onPanResponderGrant: () => {
            startXRef.current =
              openRef.current
                ? -ACTIONS_WIDTH
                : 0;
          },

          onPanResponderMove:
            (_, gesture) => {
              const next =
                Math.max(
                  -ACTIONS_WIDTH,
                  Math.min(
                    0,
                    startXRef.current
                      + gesture.dx
                  )
                );

              translateX.setValue(next);
            },

          onPanResponderRelease:
            (_, gesture) => {
              if (gesture.vx > 0.35) {
                animateTo(0);
                return;
              }

              const projected =
                startXRef.current
                + gesture.dx;

              const shouldOpen =
                gesture.vx < -0.35
                || projected
                  < -(ACTIONS_WIDTH * 0.45);

              animateTo(
                shouldOpen
                  ? -ACTIONS_WIDTH
                  : 0
              );
            },

          onPanResponderTerminate:
            () => {
              animateTo(
                openRef.current
                  ? -ACTIONS_WIDTH
                  : 0
              );
            },
        }),
      [
        animateTo,
        translateX,
      ]
    );


  const handleOpen =
    useCallback(() => {
      if (openRef.current) {
        animateTo(0);
        return;
      }

      onOpen(item);
    }, [
      animateTo,
      item,
      onOpen,
    ]);


  const handleToggleRead =
    useCallback(() => {
      animateTo(0);
      onToggleRead(item);
    }, [
      animateTo,
      item,
      onToggleRead,
    ]);


  const handleDelete =
    useCallback(() => {
      animateTo(0);
      onDelete(item);
    }, [
      animateTo,
      item,
      onDelete,
    ]);


  const toggleLabel =
    item.read_at
      ? markUnreadLabel
      : markReadLabel;


  return (
    <View style={styles.shell}>
      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={toggleLabel}
          onPress={handleToggleRead}
          style={[
            styles.action,
            styles.readAction,
          ]}
        >
          <Ionicons
            name={
              item.read_at
                ? 'mail-outline'
                : 'mail-open-outline'
            }
            size={21}
            color={
              colors.accentStrong
              || colors.tealDark
            }
          />

          <Text
            style={styles.readActionText}
            numberOfLines={2}
          >
            {toggleLabel}
          </Text>
        </Pressable>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel={deleteLabel}
          onPress={handleDelete}
          style={[
            styles.action,
            styles.deleteAction,
          ]}
        >
          <Ionicons
            name="trash-outline"
            size={21}
            color="#FFFFFF"
          />

          <Text
            style={styles.deleteActionText}
          >
            {deleteLabel}
          </Text>
        </Pressable>
      </View>

      <Animated.View
        {...panResponder.panHandlers}
        style={[
          styles.card,
          !item.read_at
            && styles.unreadCard,
          {
            transform: [
              {
                translateX,
              },
            ],
          },
        ]}
      >
        <Pressable
          onPress={handleOpen}
          style={styles.cardPressable}
        >
          <View
            style={styles.iconCircle}
          >
            <Ionicons
              name={copy.icon}
              size={21}
              color={
                colors.accentStrong
                || colors.tealDark
              }
            />
          </View>

          <View style={styles.cardBody}>
            <View
              style={styles.titleRow}
            >
              <Text
                style={styles.cardTitle}
              >
                {copy.title}
              </Text>

              {!item.read_at ? (
                <View
                  style={styles.unreadDot}
                />
              ) : null}
            </View>

            <Text
              style={styles.cardText}
            >
              {copy.body}
            </Text>

            <Text
              style={styles.timestamp}
            >
              {new Date(
                item.created_at
              ).toLocaleString()}
            </Text>
          </View>
        </Pressable>
      </Animated.View>
    </View>
  );
}


const styles =
  StyleSheet.create({
    shell: {
      position: 'relative',
      overflow: 'hidden',
      borderRadius: spacing.radii.lg,
    },

    actions: {
      ...StyleSheet.absoluteFillObject,
      flexDirection: 'row',
      justifyContent: 'flex-end',
    },

    action: {
      width: ACTION_WIDTH,
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.xs,
      paddingHorizontal: spacing.xs,
    },

    readAction: {
      backgroundColor:
        colors.accentSoft
        || '#E6F4F6',
    },

    deleteAction: {
      backgroundColor:
        colors.error
        || '#B42318',
    },

    readActionText: {
      ...typography.caption,
      fontWeight: '700',
      textAlign: 'center',
      color:
        colors.accentStrong
        || colors.tealDark,
    },

    deleteActionText: {
      ...typography.caption,
      fontWeight: '700',
      color: '#FFFFFF',
    },

    card: {
      backgroundColor:
        colors.surface
        || colors.cardBg,
      borderWidth: 1,
      borderColor:
        colors.borderSubtle
        || colors.border,
      borderRadius: spacing.radii.lg,
    },

    unreadCard: {
      borderColor:
        colors.accent
        || colors.teal,
      backgroundColor:
        colors.accentSoft
        || '#E6F4F6',
    },

    cardPressable: {
      flexDirection: 'row',
      gap: spacing.md,
      padding: spacing.lg,
    },

    iconCircle: {
      width: 40,
      height: 40,
      borderRadius: 20,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor:
        colors.accentSoft
        || '#E6F4F6',
    },

    cardBody: {
      flex: 1,
    },

    titleRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
    },

    cardTitle: {
      ...typography.cardTitle,
      flex: 1,
      color:
        colors.textPrimary
        || colors.textDark,
    },

    cardText: {
      ...typography.body,
      marginTop: spacing.xs,
      color:
        colors.textSecondary
        || colors.textMuted,
    },

    timestamp: {
      ...typography.caption,
      marginTop: spacing.sm,
      color:
        colors.textTertiary
        || colors.textMuted,
    },

    unreadDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor:
        colors.accent
        || colors.teal,
    },
  });
