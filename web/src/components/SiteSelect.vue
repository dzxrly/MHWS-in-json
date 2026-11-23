<script setup lang="ts" generic="T extends string | number">
import { computed, nextTick, ref, shallowRef, useId, watch } from "vue";

type Option = {
  label: string;
  value: T;
  group?: string;
  disabled?: boolean;
};

const props = defineProps<{
  options: readonly Option[];
  label: string;
  menuAnchor?: HTMLElement | null;
  disabled?: boolean;
  id?: string;
}>();
const model = defineModel<T>({ required: true });
defineOptions({ inheritAttrs: false });

const trigger = ref<HTMLButtonElement>();
const popup = ref<HTMLDivElement>();
const open = ref(false);
const activeValue = shallowRef<T>();
const generatedId = `site-select-${useId()}`;
const listId = `${generatedId}-list`;
const optionId = (index: number) => `${listId}-${index}`;

const selectedIndex = computed(() => props.options.findIndex((option) => option.value === model.value));
const enabled = computed(() => props.options.flatMap((option, index) => option.disabled ? [] : [index]));
const disabled = computed(() => props.disabled || enabled.value.length === 0);
const initialIndex = computed(() => enabled.value.includes(selectedIndex.value) ? selectedIndex.value : enabled.value[0]);
const activeIndex = computed(() => {
  const index = enabled.value.find((index) => props.options[index].value === activeValue.value);
  return index ?? initialIndex.value;
});
const groups = computed(() => {
  const result: { label?: string; start: number; options: (Option & { index: number })[] }[] = [];
  props.options.forEach((option, index) => {
    const group = result.at(-1);
    if (group && group.label === option.group) {
      group.options.push({ ...option, index });
    } else {
      result.push({ label: option.group, start: index, options: [{ ...option, index }] });
    }
  });
  return result;
});

let search = "";
let lastKeyTime = 0;

function highlight(index: number) {
  activeValue.value = props.options[index]?.value;
}

function show(index = initialIndex.value) {
  if (disabled.value) return;
  trigger.value?.focus({ preventScroll: true });
  highlight(index);
  open.value = true;
}

function choose(index: number) {
  if (!open.value || !enabled.value.includes(index)) return;
  open.value = false;
  model.value = props.options[index].value;
}

function onKeydown(event: KeyboardEvent) {
  const { key } = event;
  if (event.isComposing || event.ctrlKey || event.metaKey || disabled.value) return;
  if (key === "Tab") {
    open.value = false;
    return;
  }
  if (key === "Escape") {
    if (open.value) {
      open.value = false;
      event.preventDefault();
      event.stopPropagation();
    }
    return;
  }

  const indices = enabled.value;
  switch (key) {
    case "Enter":
    case " ":
      event.preventDefault();
      if (open.value) choose(activeIndex.value);
      else show();
      return;
    case "ArrowDown":
    case "ArrowUp": {
      event.preventDefault();
      const step = key === "ArrowDown" ? 1 : -1;
      if (!open.value) {
        const edge = step > 0 ? indices[0] : indices[indices.length - 1];
        show(indices.includes(selectedIndex.value) ? selectedIndex.value : edge);
      } else {
        const position = indices.indexOf(activeIndex.value) + step;
        highlight(indices[Math.max(0, Math.min(position, indices.length - 1))]);
      }
      return;
    }
    case "Home":
    case "End": {
      event.preventDefault();
      const edge = key === "Home" ? indices[0] : indices[indices.length - 1];
      if (open.value) highlight(edge);
      else show(edge);
      return;
    }
  }

  if (key.length !== 1 || event.altKey) return;
  const letter = key.toLocaleLowerCase();
  const previousSearch = event.timeStamp - lastKeyTime < 500 ? search : "";
  lastKeyTime = event.timeStamp;
  search = previousSearch + letter;
  const cycling = previousSearch.length > 0 && [...previousSearch].every((char) => char === letter);
  const prefix = cycling ? letter : search;
  const currentIndex = open.value ? activeIndex.value : selectedIndex.value;
  const first = prefix.length > 1 ? 0 : indices.indexOf(currentIndex) + 1;
  const ordered = [...indices.slice(first), ...indices.slice(0, first)];
  const match = ordered.find((index) => props.options[index].label.trimStart().toLocaleLowerCase().startsWith(prefix));
  if (match === undefined) return;
  event.preventDefault();
  if (open.value) highlight(match);
  else show(match);
}

function positionPopup() {
  const anchor = trigger.value;
  const menu = popup.value;
  if (!anchor || !menu) return;
  const rect = anchor.getBoundingClientRect();
  const viewport = window.visualViewport;
  const left = viewport?.offsetLeft ?? 0;
  const top = viewport?.offsetTop ?? 0;
  const width = viewport?.width ?? document.documentElement.clientWidth;
  const height = viewport?.height ?? document.documentElement.clientHeight;
  if (!rect.width || !rect.height || rect.bottom <= top || rect.top >= top + height ||
    rect.right <= left || rect.left >= left + width) {
    open.value = false;
    return;
  }

  const gutter = 8;
  const gap = 6;
  // Paired filters share the width and trailing edge of their toolbar group.
  const horizontal = props.menuAnchor?.getBoundingClientRect() ?? rect;
  const menuWidth = Math.min(Math.max(horizontal.width, 176), width - gutter * 2);
  const menuLeft = props.menuAnchor ? horizontal.right - menuWidth : horizontal.left;
  menu.style.width = `${menuWidth}px`;
  menu.style.left = `${Math.max(left + gutter, Math.min(menuLeft, left + width - gutter - menuWidth))}px`;

  const below = top + height - rect.bottom - gutter - gap;
  const above = rect.top - top - gutter - gap;
  const opensUp = below < menu.scrollHeight && above > below;
  menu.dataset.placement = opensUp ? "above" : "below";
  menu.style.maxHeight = `${Math.max(0, opensUp ? above : below)}px`;
  menu.style.top = `${opensUp ? rect.top - gap - menu.offsetHeight : rect.bottom + gap}px`;
}

watch(open, (isOpen, _, onCleanup) => {
  const anchor = trigger.value;
  if (!isOpen || !anchor) {
    search = "";
    return;
  }
  positionPopup();

  const outside = (event: PointerEvent) => {
    const path = event.composedPath();
    if (!path.includes(anchor) && popup.value && !path.includes(popup.value)) open.value = false;
  };
  const onScroll = (event: Event) => {
    if (event.target !== popup.value) positionPopup();
  };
  const viewport = window.visualViewport;
  const observer = new ResizeObserver(positionPopup);
  observer.observe(anchor);
  if (props.menuAnchor) observer.observe(props.menuAnchor);
  document.addEventListener("pointerdown", outside, true);
  const afterMotion = (event: AnimationEvent) => {
    if (event.target instanceof Element && event.target.contains(anchor)) positionPopup();
  };
  document.addEventListener("animationend", afterMotion);
  window.addEventListener("scroll", onScroll, true);
  window.addEventListener("resize", positionPopup);
  viewport?.addEventListener("resize", positionPopup);
  viewport?.addEventListener("scroll", positionPopup);
  onCleanup(() => {
    observer.disconnect();
    document.removeEventListener("animationend", afterMotion);
    document.removeEventListener("pointerdown", outside, true);
    window.removeEventListener("scroll", onScroll, true);
    window.removeEventListener("resize", positionPopup);
    viewport?.removeEventListener("resize", positionPopup);
    viewport?.removeEventListener("scroll", positionPopup);
  });
}, { flush: "post" });

watch([open, activeIndex], async ([isOpen]) => {
  if (!isOpen) return;
  await nextTick();
  const menu = popup.value;
  const item = document.getElementById(optionId(activeIndex.value));
  if (!menu || !item) return;
  const top = item.offsetTop;
  const bottom = top + item.offsetHeight;
  if (top < menu.scrollTop) menu.scrollTop = top;
  else if (bottom > menu.scrollTop + menu.clientHeight) menu.scrollTop = bottom - menu.clientHeight;
}, { flush: "post" });

watch(disabled, (isDisabled) => {
  if (isDisabled) open.value = false;
});
watch(() => props.options, () => {
  if (open.value) positionPopup();
}, { flush: "post" });
</script>

<template>
  <button
    v-bind="$attrs"
    :id="id ?? generatedId"
    ref="trigger"
    class="site-select"
    type="button"
    role="combobox"
    :disabled="disabled"
    :aria-label="label"
    :aria-expanded="open"
    :aria-controls="open ? listId : undefined"
    :aria-activedescendant="open ? optionId(activeIndex) : undefined"
    @click="open ? (open = false) : show()"
    @keydown="onKeydown"
    @blur="open = false"
  >
    <span class="site-select-caption">{{ options[selectedIndex]?.label ?? label }}</span>
    <svg class="site-select-chevron" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m6 9 6 6 6-6" />
    </svg>
  </button>
  <Teleport to="body">
    <div
      v-if="open"
      :id="listId"
      ref="popup"
      class="site-select-list"
      :class="{ 'align-end': menuAnchor }"
      role="listbox"
      :aria-label="label"
      @mousedown.prevent
    >
      <div
        v-for="group in groups"
        :key="group.start"
        class="site-select-group"
        :role="group.label ? 'group' : 'presentation'"
        :aria-label="group.label"
      >
        <div v-if="group.label" class="site-select-group-title" aria-hidden="true">{{ group.label }}</div>
        <div
          v-for="option in group.options"
          :id="optionId(option.index)"
          :key="option.value"
          class="site-select-option"
          role="option"
          :aria-selected="option.index === selectedIndex"
          :aria-disabled="option.disabled || undefined"
          :data-active="option.index === activeIndex || undefined"
          @click="choose(option.index)"
        >
          <svg v-if="option.index === selectedIndex" class="site-select-check" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="m5 12 4 4L19 6" />
          </svg>
          <span>{{ option.label }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.site-select {
  --select-height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: var(--select-height);
  min-width: 0;
  max-width: 100%;
  padding: 0 12px;
  appearance: none;
  border: 0;
  border-radius: calc(var(--select-height) / 2);
  background: color-mix(in srgb, var(--primary-container) 72%, transparent);
  color: var(--on-primary-container);
  font-size: 14px;
  font-weight: 600;
  text-align: start;
  transition:
    background-color var(--dur-effects) var(--effects),
    border-radius var(--dur-spring) var(--spring);
}
.site-select:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
  background: var(--primary-container);
}
.site-select[aria-expanded="true"] {
  border-radius: var(--shape-l);
  background: var(--primary-container);
}
.site-select:not(:disabled):active {
  border-radius: var(--shape-m);
  transition-duration: var(--dur-press);
  transition-timing-function: var(--effects-fast);
}
.site-select-caption {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.site-select-chevron,
.site-select-check {
  flex: none;
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.site-select-chevron {
  transition: transform var(--dur-spring-fast) var(--spring-fast);
}
.site-select[aria-expanded="true"] .site-select-chevron {
  transform: rotate(180deg);
}
.site-select-list {
  position: fixed;
  z-index: 60;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 4px;
  border-radius: var(--shape-l-plus);
  background: var(--secondary-container);
  color: var(--on-secondary-container);
  box-shadow: var(--shadow-menu);
  font-size: 14px;
  transform-origin: var(--menu-origin-x, left) top;
  animation: site-select-open var(--dur-effects) var(--emphasized-decelerate) both;
}
.site-select-list.align-end { --menu-origin-x: right; }
.site-select-list[data-placement="above"] {
  transform-origin: var(--menu-origin-x, left) bottom;
}
@keyframes site-select-open {
  from { opacity: 0; transform: scale(0.97); }
  to { opacity: 1; transform: scale(1); }
}
.site-select-group + .site-select-group {
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px solid color-mix(in srgb, currentColor 12%, transparent);
}
.site-select-group-title {
  padding: 4px 12px 2px 38px;
  font-size: 12px;
  font-weight: 650;
  overflow-wrap: anywhere;
}
.site-select-option {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 6px 12px;
  border-radius: var(--shape-m);
  cursor: pointer;
  overflow-wrap: anywhere;
  transition:
    border-radius var(--dur-spring) var(--spring),
    background-color var(--dur-effects) var(--effects);
}
.site-select-option > span {
  grid-column: 2;
}
.site-select-option + .site-select-option {
  margin-top: 2px;
}
.site-select-option[aria-selected="true"] {
  border-radius: 22px;
  background: color-mix(in srgb, currentColor 12%, transparent);
  font-weight: 650;
}
:where(html:has(.site-select[aria-expanded="true"]:focus-visible)) .site-select-option[data-active] {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}
.site-select-option[aria-disabled="true"] {
  opacity: 0.4;
  cursor: default;
}
@media (hover: hover) {
  .site-select:not(:disabled):hover {
    background: var(--primary-container);
  }
  .site-select-option:not([aria-disabled="true"]):not([aria-selected="true"]):hover {
    background: color-mix(in srgb, currentColor calc(var(--state-hover) * 100%), transparent);
  }
}
@media (prefers-reduced-motion: reduce) {
  .site-select,
  .site-select-chevron,
  .site-select-option {
    transition: none;
  }
  .site-select-list {
    animation: none;
  }
}
</style>
