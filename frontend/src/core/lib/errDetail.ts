/** 将 unknown 错误转为 ErrorAlert 等组件可用的简短文案 */
export function errDetail(e: unknown): string {
  return e instanceof Error ? e.message : '未知错误'
}
