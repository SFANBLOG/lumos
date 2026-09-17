<template>
  <div class="page"><el-card class="card" shadow="hover">
    <h2>重置密码</h2><p>验证账户信息后设置新密码</p>
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
      <el-form-item label="用户名" prop="username"><el-input v-model.trim="form.username" /></el-form-item>
      <el-form-item label="注册邮箱" prop="email"><el-input v-model.trim="form.email" /></el-form-item>
      <el-form-item label="新密码" prop="password"><el-input v-model="form.password" :type="show ? 'text' : 'password'" placeholder="至少 8 位"><template #append><el-button link @click="show=!show">{{ show ? '隐藏' : '显示' }}</el-button></template></el-input></el-form-item>
      <el-form-item label="确认新密码" prop="confirm"><el-input v-model="form.confirm" :type="showConfirm ? 'text' : 'password'"><template #append><el-button link @click="showConfirm=!showConfirm">{{ showConfirm ? '隐藏' : '显示' }}</el-button></template></el-input></el-form-item>
      <el-form-item label="验证码" prop="captcha"><div class="captcha"><el-input v-model.trim="form.captcha" placeholder="请输入结果" /><el-button :loading="captchaLoading" @click="loadCaptcha">{{ question || '获取验证码' }}</el-button></div></el-form-item>
      <el-button native-type="submit" type="primary" :loading="loading" style="width:100%">重置密码</el-button>
    </el-form>
    <div class="back"><el-link type="primary" @click="$router.push('/login')">返回登录</el-link></div>
  </el-card></div>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api/auth'
import { apiErrorMessage } from '@/api/client'
const router=useRouter(); const formRef=ref(); const loading=ref(false); const captchaLoading=ref(false); const question=ref(''); const token=ref(''); const show=ref(false); const showConfirm=ref(false)
const form=reactive({username:'',email:'',password:'',confirm:'',captcha:''})
const rules={username:[{required:true,message:'请输入用户名',trigger:'blur'}],email:[{required:true,message:'请输入邮箱',trigger:'blur'},{type:'email',message:'邮箱格式不正确',trigger:'blur'}],password:[{required:true,message:'请输入新密码',trigger:'blur'},{min:8,max:128,message:'密码长度应为 8–128 个字符',trigger:'blur'}],confirm:[{required:true,message:'请确认新密码',trigger:'blur'},{validator:(_:unknown,v:string,cb:(e?:Error)=>void)=>v===form.password?cb():cb(new Error('两次输入的密码不一致')),trigger:'blur'}],captcha:[{required:true,message:'请输入验证码',trigger:'blur'}]}
async function loadCaptcha(){captchaLoading.value=true;try{const {data}=await authApi.captcha();question.value=data.question;token.value=data.token;form.captcha=''}catch{ElMessage.error('验证码加载失败')}finally{captchaLoading.value=false}}
async function submit(){const ok=await formRef.value.validate().catch(()=>false);if(!ok||!token.value)return;loading.value=true;try{const {data}=await authApi.resetPassword({username:form.username,email:form.email,new_password:form.password,captcha_token:token.value,captcha_answer:form.captcha});ElMessage.success(data.message);router.push('/login')}catch(e:any){ElMessage.error(apiErrorMessage(e,'重置失败'));await loadCaptcha()}finally{loading.value=false}}
onMounted(loadCaptcha)
</script>
<style scoped>.page{min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f5f7fa;padding:24px}.card{width:min(100%,430px)}h2{text-align:center;margin:0 0 8px}p{text-align:center;color:#909399;margin:0 0 24px}.captcha{display:flex;width:100%;gap:8px}.captcha .el-button{min-width:118px}.back{text-align:center;margin-top:16px}</style>
