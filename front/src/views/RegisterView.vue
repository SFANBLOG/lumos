<template>
  <div class="login-page">
    <el-card class="login-card" shadow="hover">
      <h2 class="title">注册账号</h2>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="handleRegister">
        <el-form-item label="用户名" prop="username"><el-input v-model.trim="form.username" placeholder="3–64 位字母、数字或 . _ -" /></el-form-item>
        <el-form-item label="邮箱" prop="email"><el-input v-model.trim="form.email" placeholder="请输入邮箱" /></el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" :type="showPassword ? 'text' : 'password'" placeholder="至少 8 位"><template #append><el-button link @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</el-button></template></el-input>
        </el-form-item>
        <el-form-item label="再次输入密码" prop="confirmPassword">
          <el-input v-model="form.confirmPassword" :type="showConfirmPassword ? 'text' : 'password'" placeholder="请再次输入密码"><template #append><el-button link @click="showConfirmPassword = !showConfirmPassword">{{ showConfirmPassword ? '隐藏' : '显示' }}</el-button></template></el-input>
        </el-form-item>
        <el-form-item label="验证码" prop="captchaAnswer"><div class="captcha-row"><el-input v-model.trim="form.captchaAnswer" placeholder="请输入结果" /><el-button :loading="captchaLoading" @click="loadCaptcha">{{ captchaQuestion || '获取验证码' }}</el-button></div></el-form-item>
        <el-button native-type="submit" type="primary" :loading="loading" style="width: 100%">注册</el-button>
      </el-form>
      <div class="extra"><el-link type="primary" @click="$router.push('/login')">已有账号？去登录</el-link></div>
      <footer>All Rights Reserved · 何朋伟</footer>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import { apiErrorMessage } from '@/api/client'

const router = useRouter(); const authStore = useAuthStore(); const formRef = ref(); const loading = ref(false); const captchaLoading = ref(false)
const captchaQuestion = ref(''); const captchaToken = ref(''); const showPassword = ref(false); const showConfirmPassword = ref(false)
const form = reactive({ username: '', email: '', password: '', confirmPassword: '', captchaAnswer: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }, { min: 3, max: 64, message: '用户名长度应为 3–64 个字符', trigger: 'blur' }, { pattern: /^[A-Za-z0-9_.-]+$/, message: '用户名仅支持字母、数字和 . _ -', trigger: 'blur' }],
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 8, max: 128, message: '密码长度应为 8–128 个字符', trigger: 'blur' }],
  confirmPassword: [{ required: true, message: '请再次输入密码', trigger: 'blur' }, { validator: (_: unknown, value: string, callback: (error?: Error) => void) => value === form.password ? callback() : callback(new Error('两次输入的密码不一致')), trigger: 'blur' }],
  captchaAnswer: [{ required: true, message: '请输入验证码', trigger: 'blur' }],
}
async function loadCaptcha() { captchaLoading.value = true; try { const { data } = await authApi.captcha(); captchaQuestion.value = data.question; captchaToken.value = data.token; form.captchaAnswer = '' } catch { ElMessage.error('验证码加载失败，请重试') } finally { captchaLoading.value = false } }
async function handleRegister() { const valid = await formRef.value.validate().catch(() => false); if (!valid || !captchaToken.value) return; loading.value = true; try { await authStore.register(form.username, form.email, form.password, captchaToken.value, form.captchaAnswer); ElMessage.success('注册成功，请登录'); router.push('/login') } catch (e: any) { ElMessage.error(apiErrorMessage(e, '注册失败')); await loadCaptcha() } finally { loading.value = false } }
onMounted(loadCaptcha)
</script>

<style scoped>
.login-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #f5f7fa; padding: 24px; }
.login-card { width: min(100%, 430px); }.title { text-align: center; margin-bottom: 24px; }.captcha-row { display: flex; width: 100%; gap: 8px; }.captcha-row .el-button { min-width: 118px; }.extra { text-align: center; margin-top: 16px; } footer { margin-top: 28px; text-align: center; color: #909399; font-size: 12px; }
</style>
