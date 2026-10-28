<template>
  <div class="login-page">
    <aside class="brand-panel">
      <div class="brand-top">
        <div class="brand-mark">契</div>
        <div>
          <div class="brand-name">契智</div>
          <div class="brand-sub">QI ZHI LEGAL INTELLIGENCE</div>
        </div>
      </div>

      <div class="brand-copy">
        <h1>让每一份合同<br />在签署前被看清</h1>
        <p>AI 合同风险审查 · 规则可配置 · 结论可追溯</p>
      </div>

      <AppImage
        :src="illustration"
        width="100%"
        ratio="640 / 560"
        fit="contain"
        radius="18px"
        :lazy="false"
        class="brand-illustration"
        alt="契智合同审查插画"
      />

      <div class="brand-points">
        <span>10 类风险条款</span>
        <span>RAG 法条溯源</span>
        <span>全流程留痕</span>
      </div>
    </aside>

    <main class="form-panel">
      <div class="form-card">
        <div class="form-head">
          <h2>欢迎回来</h2>
          <p>登录后进入契智合同审查工作台</p>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
              size="large"
              placeholder="用户名 / 企业邮箱"
              :prefix-icon="User"
            />
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              size="large"
              type="password"
              show-password
              placeholder="登录密码"
              :prefix-icon="Lock"
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <div class="form-row">
            <el-checkbox v-model="remember">记住登录状态</el-checkbox>
            <el-link type="primary" :underline="false" @click="$router.push('/forgot-password')">
              忘记密码？
            </el-link>
          </div>

          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登录工作台
          </el-button>
        </el-form>

        <div class="form-divider"><span>安全登录</span></div>

        <div class="form-footer">
          还没有账号？
          <el-link type="primary" :underline="false" @click="$router.push('/register')">申请开通</el-link>
        </div>

        <div class="security-note">
          <el-icon><Lock /></el-icon>
          合同数据本地加密存储，AI 审查全程留痕可追溯
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import AppImage from '@/components/AppImage.vue'
import { useAuthStore } from '@/stores/auth'
import { apiErrorMessage } from '@/api/client'
import { brandIllustration } from '@/utils/placeholder'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)
const remember = ref(true)
const illustration = brandIllustration()

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const handleLogin = async () => {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch (e: any) {
    ElMessage.error(apiErrorMessage(e, '登录失败'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(420px, 1.05fr) minmax(400px, 1fr);
  background: #ffffff;
}

/* ── 品牌区 ─────────────────────────────────── */
.brand-panel {
  position: relative;
  padding: 40px 46px 34px;
  background: radial-gradient(120% 80% at 10% 0%, #332a72 0%, #221c4d 45%, #171332 100%);
  color: #ffffff;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.brand-panel::after {
  content: "";
  position: absolute;
  right: -120px;
  bottom: -140px;
  width: 380px;
  height: 380px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(108, 76, 241, 0.45), transparent 68%);
  pointer-events: none;
}
.brand-top {
  display: flex;
  align-items: center;
  gap: 11px;
  position: relative;
  z-index: 1;
}
.brand-mark {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  background: linear-gradient(140deg, #8f78f5, #6c4cf1 55%, #5a3ade);
  display: grid;
  place-items: center;
  font-size: 18px;
  font-weight: 700;
  box-shadow: 0 8px 20px rgba(108, 76, 241, 0.45);
}
.brand-name {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 3px;
}
.brand-sub {
  margin-top: 3px;
  font-size: 8px;
  letter-spacing: 1.3px;
  color: #9c96c4;
}
.brand-copy {
  margin-top: 44px;
  position: relative;
  z-index: 1;
}
.brand-copy h1 {
  margin: 0;
  font-size: 34px;
  line-height: 1.35;
  font-weight: 700;
  letter-spacing: -0.5px;
}
.brand-copy p {
  margin: 14px 0 0;
  font-size: 13px;
  color: #b3adcf;
  letter-spacing: 0.2px;
}
.brand-illustration {
  margin-top: 26px;
  background: transparent;
  position: relative;
  z-index: 1;
}
.brand-points {
  margin-top: auto;
  padding-top: 22px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  position: relative;
  z-index: 1;
}
.brand-points span {
  padding: 5px 11px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.05);
  font-size: 11px;
  color: #cec9e6;
}

/* ── 表单区 ─────────────────────────────────── */
.form-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 36px 28px;
  background: #ffffff;
}
.form-card {
  width: 358px;
}
.form-head h2 {
  margin: 0;
  font-size: 25px;
  font-weight: 700;
  color: var(--qz-ink);
  letter-spacing: -0.3px;
}
.form-head p {
  margin: 9px 0 26px;
  font-size: 13px;
  color: var(--qz-muted);
}
.form-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: -4px 0 18px;
}
.login-btn {
  width: 100%;
  height: 44px;
  font-size: 14px;
  border-radius: 11px;
}
.form-divider {
  position: relative;
  text-align: center;
  margin: 24px 0 20px;
}
.form-divider::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 1px;
  background: var(--qz-line);
}
.form-divider span {
  position: relative;
  padding: 0 12px;
  background: #ffffff;
  font-size: 11px;
  color: #b0b4c4;
}
.form-footer {
  text-align: center;
  font-size: 12.5px;
  color: var(--qz-ink-3);
}
.security-note {
  margin-top: 26px;
  padding: 11px 12px;
  border-radius: 10px;
  background: #fafbfe;
  color: var(--qz-muted);
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 7px;
  line-height: 1.6;
}

@media (max-width: 940px) {
  .login-page {
    grid-template-columns: minmax(0, 1fr);
  }
  .brand-panel {
    display: none;
  }
  .form-panel {
    background: linear-gradient(180deg, #f7f5ff, #ffffff 240px);
  }
}
</style>
