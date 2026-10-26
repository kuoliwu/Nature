/**
 * 可左右滑的列（只用 React Native 內建的 PanResponder＋Animated，手機觸控與電腦滑鼠拖曳都能用）：
 *   往右滑 → 露出左邊的按鈕（例如釘選）
 *   往左滑 → 露出右邊的按鈕（可以多顆，例如備份、刪除）
 * 一次只開一列：由外層傳入 open／onOpenChange 控制。
 * 注意：電腦用滑鼠拖曳放開時，網頁版裡面的 Pressable 仍會收到一次按下（onPress），
 * 外層要忽略 onOpenChange 之後一小段時間內的點擊（見建案列表 service/index.tsx）。
 */
import { ReactNode, useEffect, useMemo, useRef } from 'react';
import { Animated, PanResponder, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from './ui';

export type SwipeSide = 'left' | 'right';
export type SwipeAction = { label: string; icon?: string; color: string; textColor: string; onPress: () => void };

const ACTION_W = 84;

export function SwipeRow(props: {
  children: ReactNode;
  left?: SwipeAction; // 往右滑露出
  right?: SwipeAction[]; // 往左滑露出（由左到右排列）
  open: SwipeSide | null;
  onOpenChange: (side: SwipeSide | null) => void;
}) {
  const x = useRef(new Animated.Value(0)).current;
  const base = useRef(0); // 開始拖曳時列的位置
  const startX = useRef(0); // 開始拖曳時手指／滑鼠的 pageX（自己算位移：網頁版滑鼠的 gestureState.dx 不可靠）
  const pos = useRef(0); // 拖曳中最後的位置（放開時的事件在網頁版沒有可靠的座標）
  const propsRef = useRef(props);
  propsRef.current = props;

  const rightWidth = () => ACTION_W * (propsRef.current.right?.length ?? 0);
  const target = (side: SwipeSide | null) => (side === 'left' ? ACTION_W : side === 'right' ? -rightWidth() : 0);

  useEffect(() => {
    Animated.spring(x, { toValue: target(props.open), useNativeDriver: false, bounciness: 0, speed: 20 }).start();
  }, [props.open, x]);

  const responder = useMemo(
    () =>
      PanResponder.create({
        // 明顯是左右滑才接手，上下捲動交給列表；用 Capture：裡面的卡片（Pressable）按下時已先拿到觸控，
        // 要在捕捉階段由外層搶過來，卡片的點擊也會因此取消（不會滑完又進入建案）
        onMoveShouldSetPanResponderCapture: (_, g) => Math.abs(g.dx) > 10 && Math.abs(g.dx) > Math.abs(g.dy) * 1.5,
        onPanResponderTerminationRequest: () => false,
        onPanResponderGrant: (e, g) => {
          base.current = pos.current = target(propsRef.current.open);
          startX.current = e.nativeEvent.pageX - g.dx; // 接手前已經移動的距離也算進去
        },
        onPanResponderMove: (e) => {
          const { left, right } = propsRef.current;
          const max = left ? ACTION_W * 1.3 : 0;
          const min = right?.length ? -rightWidth() - ACTION_W * 0.3 : 0;
          pos.current = Math.max(min, Math.min(max, base.current + e.nativeEvent.pageX - startX.current));
          x.setValue(pos.current);
        },
        onPanResponderRelease: () => {
          const p = pos.current;
          const { left, right, onOpenChange } = propsRef.current;
          const side: SwipeSide | null = p > ACTION_W / 2 && left ? 'left' : p < -ACTION_W / 2 && right?.length ? 'right' : null;
          onOpenChange(side);
          // 狀態沒變（例如拖一半放開又回原位）時，也要把位置彈回去
          Animated.spring(x, { toValue: target(side), useNativeDriver: false, bounciness: 0, speed: 20 }).start();
        },
      }),
    [x],
  );

  const action = (a: SwipeAction, side: SwipeSide, last = true) => (
    <Pressable
      key={a.label}
      onPress={() => {
        props.onOpenChange(null);
        a.onPress();
      }}
      accessibilityRole="button"
      accessibilityLabel={a.label}
      style={[s.action, side === 'left' ? s.actionLeft : last && s.actionRight, { backgroundColor: a.color }]}
    >
      {!!a.icon && <Text style={[s.icon, { color: a.textColor }]}>{a.icon}</Text>}
      <Text style={[s.actionText, { color: a.textColor }]}>{a.label}</Text>
    </Pressable>
  );

  return (
    <View style={s.wrap}>
      <View style={s.under}>
        {props.left && action(props.left, 'left')}
        <View style={{ flex: 1 }} />
        {props.right?.map((a, i) => action(a, 'right', i === props.right!.length - 1))}
      </View>
      <Animated.View testID="swipe-front" style={[s.front, { transform: [{ translateX: x }] }]} {...responder.panHandlers}>
        {props.children}
      </Animated.View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { borderRadius: 12, overflow: 'hidden' },
  front: { userSelect: 'none' }, // 網頁版用滑鼠拖曳時不要選到文字
  under: { ...StyleSheet.absoluteFill, flexDirection: 'row', backgroundColor: colors.subtle, borderRadius: 12 },
  action: { width: ACTION_W, alignItems: 'center', justifyContent: 'center', gap: 4 },
  actionLeft: { borderTopLeftRadius: 12, borderBottomLeftRadius: 12 },
  actionRight: { borderTopRightRadius: 12, borderBottomRightRadius: 12 },
  icon: { fontSize: 20 },
  actionText: { fontSize: 14, fontWeight: '700' },
});
