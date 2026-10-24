/** 簽名板：手指 / 觸控筆 / 滑鼠書寫，記錄每一筆的座標，由後端繪成 PNG */
import { useMemo, useRef, useState } from 'react';
import { LayoutChangeEvent, PanResponder, StyleSheet, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { colors } from './ui';

export type Strokes = number[][][]; // [筆畫][點][x, y]

function toPath(stroke: number[][]): string {
  if (stroke.length === 1) {
    const [x, y] = stroke[0];
    return `M ${x} ${y} L ${x + 0.1} ${y + 0.1}`; // 單點也畫得出來
  }
  return stroke.map(([x, y], i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
}

export function SignaturePad(props: {
  strokes: Strokes;
  onChange: (strokes: Strokes, size: { width: number; height: number }) => void;
  onDrawingChange?: (drawing: boolean) => void; // 書寫時讓外層停止捲動
  height?: number;
}) {
  const [size, setSize] = useState({ width: 0, height: props.height ?? 220 });
  const strokesRef = useRef(props.strokes);
  strokesRef.current = props.strokes;
  const sizeRef = useRef(size);
  sizeRef.current = size;
  const onChangeRef = useRef(props.onChange);
  onChangeRef.current = props.onChange;
  const onDrawingRef = useRef(props.onDrawingChange);
  onDrawingRef.current = props.onDrawingChange;

  const responder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderTerminationRequest: () => false,
        onPanResponderGrant: (e) => {
          onDrawingRef.current?.(true);
          const { locationX, locationY } = e.nativeEvent;
          onChangeRef.current([...strokesRef.current, [[locationX, locationY]]], sizeRef.current);
        },
        onPanResponderMove: (e) => {
          const { locationX, locationY } = e.nativeEvent;
          const strokes = strokesRef.current;
          const last = strokes[strokes.length - 1];
          if (!last) return;
          const [px, py] = last[last.length - 1];
          if (Math.abs(px - locationX) + Math.abs(py - locationY) < 1.5) return; // 太近的點略過
          onChangeRef.current([...strokes.slice(0, -1), [...last, [locationX, locationY]]], sizeRef.current);
        },
        onPanResponderRelease: () => onDrawingRef.current?.(false),
        onPanResponderTerminate: () => onDrawingRef.current?.(false),
      }),
    [],
  );

  const onLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    setSize({ width, height });
  };

  return (
    <View style={[localStyles.pad, { height: props.height ?? 220 }]} onLayout={onLayout} {...responder.panHandlers}>
      {/* pointerEvents=none：觸控一律落在外層 View，座標才會以簽名板為基準 */}
      <Svg width="100%" height="100%" pointerEvents="none">
        {props.strokes.map((s, i) => (
          <Path key={i} d={toPath(s)} stroke={colors.text} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" fill="none" />
        ))}
      </Svg>
      {props.strokes.length === 0 && (
        <View style={localStyles.hint} pointerEvents="none">
          <Text style={localStyles.hintText}>請在此框內簽名</Text>
        </View>
      )}
    </View>
  );
}

const localStyles = StyleSheet.create({
  pad: {
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: colors.border,
    borderRadius: 12,
    backgroundColor: '#fff',
    overflow: 'hidden',
  },
  hint: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
  hintText: { color: '#9ca3af', fontSize: 16 },
});
