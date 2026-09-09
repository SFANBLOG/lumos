import apiClient from './client'

export interface LoginForm {
  username: string
  password: string
}

export interface RegisterForm extends LoginForm {
  email: string
}

export interface UserInfo {
  id: string
  username: string
  email: string
  is_active: boolean
}

export const authApi = {
  login(data: LoginForm) {
    return apiClient.post<{ access_token: string }>('/auth/login', data)
  },
  register(data: RegisterForm) {
    return apiClient.post<UserInfo>('/auth/register', data)
  },
  me() {
    return apiClient.get<UserInfo>('/auth/me')
  },
}
