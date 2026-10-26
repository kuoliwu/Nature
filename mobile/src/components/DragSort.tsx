/**
 * 長按後上下拖曳排序（只用 PanResponder＋Animated，手機觸控與電腦滑鼠都能用）：
 *   1. 列裡的 Pressable 用 onLongPress={() => drag.begin(key)} 開始，onPressOut={drag.endIfIdle}
 *   2. 每一列外層套 <Animated.View {...drag.rowProps(key)}>
 *   3. 手指不放開往上下拖：超過半列就和隔壁交換；放開後 onDrop(新順序)
 * group：只能在同一群裡移動（例如釘選的建案固定在最前面）。
 * 列表要用一般 ScrollView（FlatList 每列包在各自的容器裡，拖曳中的列浮不到別列上面），拖曳中要關掉捲動。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, LayoutChangeEvent, PanResponder } from 'react-native';

const GAP = 10; // 列與列的間距（與列表的 gap 一致）

const EMPTY: never[] = [];

export function useDragSort<T>(opts: {
  items: T[] | null | undefined; // 要傳穩定的參考（例如 useLoad 的 data），不要每次 render 都產生新陣列
  keyOf: (item: T) => number;
  groupOf?: (item: T) => string | boolean;
  onDrop: (ordered: T[]) => void;
}) {
  const items = opts.items ?? (EMPTY as T[]);
  const [list, setList] = useState(items);
  const [dragging, setDragging] = useState<number | null>(null);
  const dy = useRef(new Animated.Value(0)).current;
  const s = useRef({ key: null as number | null, start: 0, index: 0, startY: 0, active: false, heights: new Map<number, number>() }).current;
  const listRef = useRef(list);
  listRef.current = list;
  const optsRef = useRef(opts);
  optsRef.current = opts;

  // 沒在拖曳時，跟著外面的資料更新（例如重新載入、釘選）
  useEffect(() => {
    if (s.key === null) setList(items);
  }, [items, s]);

  function finish() {
    const moved = s.index !== s.start;
    s.key = null;
    s.active = false;
    setDragging(null);
    Animated.spring(dy, { toValue: 0, useNativeDriver: false, bounciness: 0, speed: 24 }).start();
    if (moved) optsRef.current.onDrop(listRef.current);
  }

  const responder = useMemo(
    () =>
      PanResponder.create({
        // 長按開始拖曳後，同一次觸控的移動由外層接手（捕捉階段，搶過裡面的卡片與左右滑）
        onMoveShouldSetPanResponderCapture: () => s.key !== null,
        onPanResponderTerminationRequest: () => false,
        onPanResponderGrant: (e, g) => {
          s.active = true;
          s.startY = e.nativeEvent.pageY - g.dy;
        },
        onPanResponderMove: (e) => {
          if (s.key === null) return;
          const items = listRef.current;
          const { groupOf } = optsRef.current;
          const step = (s.heights.get(s.key) ?? 100) + GAP;
          const offset = e.nativeEvent.pageY - s.startY;
          // 只能在同一群裡移動
          const me = items[s.index];
          const same = items.map((it, i) => ({ it, i })).filter(({ it }) => !groupOf || groupOf(it) === groupOf(me)).map(({ i }) => i);
          const target = Math.max(same[0], Math.min(same[same.length - 1], s.start + Math.round(offset / step)));
          if (target !== s.index) {
            const next = [...items];
            const [moved] = next.splice(s.index, 1);
            next.splice(target, 0, moved);
            s.index = target;
            listRef.current = next;
            setList(next);
          }
          dy.setValue(offset - (s.index - s.start) * step);
        },
        onPanResponderRelease: finish,
        onPanResponderTerminate: finish,
      }),
    [dy, s],
  );

  return {
    list,
    dragging,
    /** 長按開始 */
    begin(key: number) {
      s.key = key;
      s.start = s.index = listRef.current.findIndex((it) => optsRef.current.keyOf(it) === key);
      s.active = false;
      dy.setValue(0);
      setDragging(key);
    },
    /** 長按後沒有移動就放開：結束拖曳狀態（卡片的 onPressOut 呼叫） */
    endIfIdle() {
      // 開始拖曳時卡片也會收到 pressOut（觸控被外層接手），稍等確認不是在拖曳中
      setTimeout(() => {
        if (s.key !== null && !s.active) finish();
      }, 80);
    },
    rowProps(key: number) {
      const isDragging = key === dragging;
      return {
        onLayout: (e: LayoutChangeEvent) => s.heights.set(key, e.nativeEvent.layout.height),
        ...responder.panHandlers,
        style: isDragging
          ? {
              zIndex: 10,
              elevation: 8,
              shadowColor: '#000',
              shadowOpacity: 0.35,
              shadowRadius: 10,
              shadowOffset: { width: 0, height: 4 },
              transform: [{ translateY: dy }, { scale: 1.03 }],
            }
          : undefined,
      };
    },
  };
}
