import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  // 演示数据默认关闭：生产构建把 @/mock/demo 指向空实现，
  // 示例合同、示例风险与写死的统计数字不会出现在真实环境。
  const demoEnabled = env.VITE_DEMO_MODE === 'true'
  const demoModule = resolve(
    __dirname,
    demoEnabled ? 'src/mock/demo.ts' : 'src/mock/demo.empty.ts',
  )

  return {
    plugins: [vue()],
    resolve: {
      // 精确匹配必须先于 '@' 前缀别名，否则会被替换成 src/mock/demo.ts
      alias: [
        { find: /^@\/mock\/demo$/, replacement: demoModule },
        { find: '@', replacement: resolve(__dirname, 'src') },
      ],
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://localhost:8001',
          changeOrigin: true,
        },
      },
    },
  }
})
