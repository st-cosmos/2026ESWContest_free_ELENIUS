// 터치 화면용 가상 키보드 (한글 두벌식 / 영문 / 숫자·기호)
//
// 라즈베리파이 키오스크에서는 chromium 이 XWayland 로 뜨기 때문에 Wayland 온스크린
// 키보드(squeekboard)가 입력창 포커스를 감지하지 못한다. OS 키보드에 의존하지 않고
// 앱 안에서 직접 그린다. document 의 focusin/focusout 을 감시해 <input>/<textarea>
// 에 포커스가 오면 화면 하단에 나타나고, 포커스가 빠지면 사라진다.
//
// 한글은 hangul-js 로 조합한다. 커서 바로 앞 글자를 자모로 분해해 새 자모를 붙이고
// 다시 합치는 방식이라 '각' + 'ㅅ' → '갃', '갃' + 'ㅏ' → '각사' 처럼 동작한다.

import { ChevronDown, CornerDownLeft, Delete } from "lucide-react";
import Hangul from "hangul-js";
import { useCallback, useEffect, useRef, useState } from "react";

type Field = HTMLInputElement | HTMLTextAreaElement;
type Layout = "ko" | "en" | "num";

// 키오스크 뷰포트는 1097×686 CSS px (1920×1200 @ DPR 1.75) — 화면의 약 38%
const KB_HEIGHT = 260; // px, theme.css 의 --kb-h 와 맞춘다

const KO_ROWS = [
  ["ㅂ", "ㅈ", "ㄷ", "ㄱ", "ㅅ", "ㅛ", "ㅕ", "ㅑ", "ㅐ", "ㅔ"],
  ["ㅁ", "ㄴ", "ㅇ", "ㄹ", "ㅎ", "ㅗ", "ㅓ", "ㅏ", "ㅣ"],
  ["ㅋ", "ㅌ", "ㅊ", "ㅍ", "ㅠ", "ㅜ", "ㅡ"],
];
const KO_SHIFT: Record<string, string> = {
  ㅂ: "ㅃ", ㅈ: "ㅉ", ㄷ: "ㄸ", ㄱ: "ㄲ", ㅅ: "ㅆ", ㅐ: "ㅒ", ㅔ: "ㅖ",
};
const EN_ROWS = [
  ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
  ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
  ["z", "x", "c", "v", "b", "n", "m"],
];
const NUM_ROWS = [
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
  ["-", "/", ":", ";", "(", ")", "@", "&", "_", "\""],
  [".", ",", "?", "!", "'", "#", "*", "+", "="],
];

const JAMO = new Set([
  ...KO_ROWS.flat(),
  ...Object.values(KO_SHIFT),
]);

function isTextField(el: Element | null): el is Field {
  if (!el) return false;
  if (el instanceof HTMLTextAreaElement) return !el.readOnly && !el.disabled;
  if (el instanceof HTMLInputElement) {
    if (el.readOnly || el.disabled) return false;
    const t = (el.type || "text").toLowerCase();
    return ["text", "search", "tel", "url", "email", "password"].includes(t);
  }
  return false;
}

function initialLayout(el: Field): Layout {
  const mode = (el.inputMode || "").toLowerCase();
  if (mode === "numeric" || mode === "tel" || mode === "decimal") return "num";
  if (mode === "latin" || el.type === "email" || el.type === "url") return "en";
  return "ko";
}

// React 의 controlled input 은 el.value 를 직접 바꾸면 onChange 가 안 뜬다.
// 프로토타입의 value setter 로 값을 넣고 input 이벤트를 흘려 보낸다.
function setNativeValue(el: Field, value: string) {
  const proto =
    el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

export function VirtualKeyboard() {
  const [target, setTarget] = useState<Field | null>(null);
  const [layout, setLayout] = useState<Layout>("ko");
  const [shift, setShift] = useState(false);

  // 한글 조합 상태: 어느 필드의 어느 위치(커서 앞 글자)를 조합 중인지.
  // 커서가 움직였거나 다른 필드면 조합을 끊는다.
  const compose = useRef<{ el: Field; pos: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onFocusIn = (e: FocusEvent) => {
      const el = e.target as Element | null;
      if (isTextField(el)) {
        setTarget(el);
        setLayout(initialLayout(el));
        setShift(false);
        compose.current = null;
      }
    };
    const onFocusOut = (e: FocusEvent) => {
      // 키보드 버튼은 pointerdown 에서 preventDefault 하므로 포커스를 뺏지 않지만,
      // 혹시 relatedTarget 이 키보드 안이면 무시한다.
      const next = e.relatedTarget as Node | null;
      if (next && rootRef.current?.contains(next)) return;
      setTarget(null);
      compose.current = null;
    };
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    // 이미 포커스된 채로 마운트된 경우(autoFocus)
    if (isTextField(document.activeElement)) {
      setTarget(document.activeElement);
      setLayout(initialLayout(document.activeElement));
    }
    return () => {
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
    };
  }, []);

  // 키보드가 떠 있는 동안 화면을 그만큼 줄여서 입력창이 가려지지 않게 한다
  useEffect(() => {
    const body = document.body;
    if (target) {
      body.classList.add("kb-open");
      body.style.setProperty("--kb-h", `${KB_HEIGHT}px`);
      // 화면이 줄어든 뒤 입력창이 키보드에 가리지 않도록 보이는 위치로 스크롤
      const t = window.setTimeout(
        () => target.scrollIntoView({ block: "nearest", behavior: "smooth" }),
        50,
      );
      return () => {
        window.clearTimeout(t);
        body.classList.remove("kb-open");
      };
    } else {
      body.classList.remove("kb-open");
    }
    return () => body.classList.remove("kb-open");
  }, [target]);

  const replaceRange = useCallback(
    (el: Field, start: number, end: number, text: string) => {
      const v = el.value;
      setNativeValue(el, v.slice(0, start) + text + v.slice(end));
      const caret = start + text.length;
      try {
        el.setSelectionRange(caret, caret);
      } catch {
        /* type=number 등 selection 미지원 */
      }
      return caret;
    },
    [],
  );

  const caretOf = (el: Field) => {
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? start;
    return { start, end };
  };

  const composing = (el: Field, pos: number) =>
    compose.current !== null &&
    compose.current.el === el &&
    compose.current.pos === pos;

  const typeText = useCallback(
    (el: Field, text: string) => {
      const { start, end } = caretOf(el);
      const isJamo = text.length === 1 && JAMO.has(text);

      if (isJamo && start === end && start > 0 && composing(el, start)) {
        // 조합 중: 커서 앞 글자를 분해해 새 자모를 붙이고 다시 합친다
        const prev = el.value[start - 1];
        const jamo = [...Hangul.disassemble(prev), text];
        const out = Hangul.assemble(jamo);
        const caret = replaceRange(el, start - 1, start, out);
        compose.current = { el, pos: caret };
        return;
      }

      const caret = replaceRange(el, start, end, text);
      compose.current = isJamo ? { el, pos: caret } : null;
    },
    [replaceRange],
  );

  const backspace = useCallback(
    (el: Field) => {
      const { start, end } = caretOf(el);
      if (start !== end) {
        replaceRange(el, start, end, "");
        compose.current = null;
        return;
      }
      if (start === 0) return;

      if (composing(el, start)) {
        // 조합 중이면 자모 하나만 뺀다 ('각' → '가', '가' → 'ㄱ', 'ㄱ' → '')
        const prev = el.value[start - 1];
        const jamo = Hangul.disassemble(prev);
        jamo.pop();
        const out = Hangul.assemble(jamo);
        const caret = replaceRange(el, start - 1, start, out);
        compose.current = out ? { el, pos: caret } : null;
        return;
      }

      replaceRange(el, start - 1, start, "");
      compose.current = null;
    },
    [replaceRange],
  );

  const onKey = useCallback(
    (key: string) => {
      const el = target;
      if (!el) return;
      switch (key) {
        case "{bksp}":
          backspace(el);
          break;
        case "{shift}":
          setShift((s) => !s);
          break;
        case "{ko}":
          setLayout("ko");
          setShift(false);
          compose.current = null;
          break;
        case "{en}":
          setLayout("en");
          setShift(false);
          compose.current = null;
          break;
        case "{num}":
          setLayout("num");
          setShift(false);
          compose.current = null;
          break;
        case "{space}":
          typeText(el, " ");
          break;
        case "{enter}":
          if (el instanceof HTMLTextAreaElement) {
            typeText(el, "\n");
          } else {
            // 한 줄 입력은 완료 = 키보드 닫기
            compose.current = null;
            el.blur();
          }
          break;
        case "{hide}":
          compose.current = null;
          el.blur();
          break;
        default: {
          let text = key;
          if (shift) {
            if (layout === "ko") text = KO_SHIFT[key] ?? key;
            else if (layout === "en") text = key.toUpperCase();
          }
          typeText(el, text);
          if (shift && layout !== "num") setShift(false);
        }
      }
    },
    [target, layout, shift, typeText, backspace],
  );

  if (!target) return null;

  const rows = layout === "ko" ? KO_ROWS : layout === "en" ? EN_ROWS : NUM_ROWS;

  const label = (k: string) => {
    if (!shift) return k;
    if (layout === "ko") return KO_SHIFT[k] ?? k;
    if (layout === "en") return k.toUpperCase();
    return k;
  };

  const Key = ({
    k,
    children,
    className = "",
    flex,
  }: {
    k: string;
    children?: React.ReactNode;
    className?: string;
    flex?: number;
  }) => (
    <button
      type="button"
      className={`vk-key ${className}`}
      style={flex ? { flex } : undefined}
      // pointerdown 에서 preventDefault: 입력창 포커스를 유지한 채 키 입력
      onPointerDown={(e) => {
        e.preventDefault();
        onKey(k);
      }}
    >
      {children ?? label(k)}
    </button>
  );

  return (
    <div
      ref={rootRef}
      className="vk"
      // 키보드 바탕을 눌러도 포커스가 안 빠지게
      onPointerDown={(e) => e.preventDefault()}
    >
      {rows.map((row, i) => (
        <div className="vk-row" key={i}>
          {i === 2 && layout !== "num" && (
            <Key k="{shift}" className={`vk-fn${shift ? " active" : ""}`} flex={1.5}>
              ⇧
            </Key>
          )}
          {i === 2 && layout === "num" && (
            <Key k="{shift}" className="vk-fn vk-ghost" flex={1.5}>
              {" "}
            </Key>
          )}
          {row.map((k) => (
            <Key k={k} key={k} />
          ))}
          {i === 2 && (
            <Key k="{bksp}" className="vk-fn" flex={1.5}>
              <Delete size={22} />
            </Key>
          )}
        </div>
      ))}
      <div className="vk-row">
        <Key k={layout === "num" ? "{ko}" : "{num}"} className="vk-fn" flex={1.5}>
          {layout === "num" ? "한글" : "?123"}
        </Key>
        <Key k={layout === "en" ? "{ko}" : "{en}"} className="vk-fn" flex={1.5}>
          {layout === "en" ? "한글" : "ABC"}
        </Key>
        <Key k="{space}" flex={layout === "num" ? 7 : 6}>
          {" "}
        </Key>
        {layout !== "num" && <Key k="-" flex={1} />}
        <Key k="{enter}" className="vk-fn vk-enter" flex={2}>
          <CornerDownLeft size={18} />
          <span>완료</span>
        </Key>
        <Key k="{hide}" className="vk-fn" flex={1}>
          <ChevronDown size={22} />
        </Key>
      </div>
    </div>
  );
}
