import apiClient from './client'

export interface LoginForm {
  username: string
  password: string
}

export interface RegisterForm extends LoginForm {
  email: string
  captcha_token: string
  captcha_answer: string
}

export interface UserInfo {
  id: string
  username: string
  email: string
  is_active: boolean
}

export interface PasswordResetForm {
  username: string
  email: string
  new_password: string
  captcha_token: string
  captcha_answer: string
}

export const authApi = {
  login(data: LoginForm) {
    return apiClient.post<{ access_token: string }>('/auth/login', data)
  },
  register(data: RegisterForm) {
    return apiClient.post<UserInfo>('/auth/register', data)
  },
  captcha() {
    return apiClient.get<{ question: string; token: string }>('/auth/captcha')
  },
  resetPassword(data: PasswordResetForm) {
    return apiClient.post<{ message: string }>('/auth/password-reset', data)
  },
  me() {
    return apiClient.get<UserInfo>('/auth/me')
  },
}
