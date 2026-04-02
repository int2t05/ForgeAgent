/** 生成中仅在用户仍贴近列表底部时跟滚动；上移阅读时不再强制吸底，便于自由滚动。 */
export function isNearScrollBottom(el: HTMLElement, thresholdPx = 96): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= thresholdPx
}
