/**
 * 演示数据开关。
 *
 * 生产构建默认关闭：所有示例合同、示例风险、写死的统计数字都不进入页面。
 * 本地需要展示完整工作台形态时，在 front/.env.local 中设置：
 *   VITE_DEMO_MODE=true
 * 并重新启动 dev server（vite.config.ts 会据此切换 @/mock/demo 的实现）。
 */
export const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true'

/** 供非演示模式做兜底：开关关闭时返回 empty。 */
export function demoOnly<T>(demo: T, empty: T): T {
  return isDemoMode ? demo : empty
}
