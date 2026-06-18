import { useEffect, useMemo, useState } from 'react';
import { Animated, Easing, StyleSheet, View, useWindowDimensions } from 'react-native';

type GlimoShieldBackgroundProps = {
  swipeX?: Animated.Value;
  variant?: 'dashboard' | 'review';
};

const shieldSource = require('@/assets/glimo_sheild.png');

const layerConfigs = [
  { size: 72, spacingX: 170, spacingY: 210, duration: 26000, drift: 18, opacity: 0.12 },
  { size: 112, spacingX: 260, spacingY: 310, duration: 34000, drift: 34, opacity: 0.08 },
  { size: 46, spacingX: 126, spacingY: 170, duration: 21000, drift: 12, opacity: 0.14 },
] as const;

export function GlimoShieldBackground({
  swipeX,
  variant = 'dashboard',
}: GlimoShieldBackgroundProps) {
  const { width, height } = useWindowDimensions();
  const [fallValues] = useState(() => layerConfigs.map(() => new Animated.Value(0)));
  const [idleDrift] = useState(() => new Animated.Value(0));

  useEffect(() => {
    const fallAnimations = fallValues.map((value, index) =>
      Animated.loop(
        Animated.timing(value, {
          toValue: 1,
          duration: layerConfigs[index].duration,
          easing: Easing.linear,
          isInteraction: false,
          useNativeDriver: false,
        }),
      ),
    );

    const driftAnimation = Animated.loop(
      Animated.sequence([
        Animated.timing(idleDrift, {
          toValue: 1,
          duration: 5200,
          easing: Easing.inOut(Easing.sin),
          isInteraction: false,
          useNativeDriver: false,
        }),
        Animated.timing(idleDrift, {
          toValue: 0,
          duration: 5200,
          easing: Easing.inOut(Easing.sin),
          isInteraction: false,
          useNativeDriver: false,
        }),
      ]),
    );

    fallAnimations.forEach((animation) => animation.start());
    driftAnimation.start();

    return () => {
      fallAnimations.forEach((animation) => animation.stop());
      driftAnimation.stop();
    };
  }, [fallValues, idleDrift]);

  const layers = useMemo(
    () =>
      layerConfigs.map((config, layerIndex) => {
        const spacingX = variant === 'review' ? config.spacingX * 0.88 : config.spacingX;
        const spacingY = variant === 'review' ? config.spacingY * 0.9 : config.spacingY;
        const columns = Math.ceil(width / spacingX) + 3;
        const rows = Math.ceil((height + spacingY * 4) / spacingY) + 2;

        return Array.from({ length: columns * rows }, (_, index) => {
          const row = Math.floor(index / columns);
          const column = index % columns;
          const alternate = (row + layerIndex) % 2 === 0 ? 0 : spacingX * 0.42;
          const rotation = ((row * 7 + column * 11 + layerIndex * 13) % 28) - 14;

          return {
            key: `${layerIndex}-${index}`,
            left: column * spacingX - config.size + alternate,
            rotate: `${rotation}deg`,
            size: variant === 'review' ? config.size * 1.05 : config.size,
            top: row * spacingY - spacingY * 3,
          };
        });
      }),
    [height, variant, width],
  );

  const idleDirection = idleDrift.interpolate({
    inputRange: [0, 1],
    outputRange: [-1, 1],
  });
  const baseDirection = swipeX
    ? Animated.add(
        Animated.multiply(idleDirection, 0.35),
        swipeX.interpolate({
          inputRange: [-220, 0, 220],
          outputRange: [-1, 0, 1],
          extrapolate: 'clamp',
        }),
      )
    : idleDirection;

  return (
    <View style={[StyleSheet.absoluteFill, styles.noPointerEvents]}>
      <View style={styles.wash} />
      {layers.map((sprites, layerIndex) => {
        const config = layerConfigs[layerIndex];
        const translateY = fallValues[layerIndex].interpolate({
          inputRange: [0, 1],
          outputRange: [-config.spacingY, 0],
        });
        const translateX = Animated.multiply(baseDirection, config.drift);

        return (
          <Animated.View
            key={config.size}
            style={[
              styles.layer,
              {
                opacity: config.opacity,
                transform: [{ translateX }, { translateY }],
              },
            ]}>
            {sprites.map((sprite) => (
              <Animated.Image
                key={sprite.key}
                source={shieldSource}
                resizeMode="contain"
                style={[
                  styles.shield,
                  {
                    height: sprite.size,
                    left: sprite.left,
                    top: sprite.top,
                    transform: [{ rotate: sprite.rotate }],
                    width: sprite.size,
                  },
                ]}
              />
            ))}
          </Animated.View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  layer: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  },
  noPointerEvents: {
    pointerEvents: 'none',
  },
  shield: {
    position: 'absolute',
  },
  wash: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: 'rgba(246, 250, 255, 0.86)',
  },
});
