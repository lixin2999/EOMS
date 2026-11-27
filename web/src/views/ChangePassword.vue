<template>
  <div class="change-password-page">
    <div class="change-card">
      <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px">
        <img class="brand-mark" src="/brand/dongyan-logo.jpg" alt="东研智联 Logo" />
        <strong>东研智联账号安全</strong>
      </div>
      <h2 style="margin: 14px 0 6px; font-size: 22px">修改登录密码</h2>
      <p class="muted" style="margin: 0 0 22px; font-size: 13px; line-height: 1.7">
        <template v-if="auth.firstLogin">
          当前账号为首次登录或密码已被重置，为保障账号安全，请先设置新的登录密码。
        </template>
        <template v-else>定期更换密码有助于保护账号与业务数据安全。</template>
      </p>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" size="large">
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="form.old_password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="form.new_password" type="password" show-password autocomplete="new-password" />
          <div class="password-meter">
            <span v-for="index in 3" :key="index" :class="['', strength.class, { active: index <= strength.score }]" />
          </div>
          <div class="form-tip">至少 8 位，需同时包含字母与数字，建议加入大小写与符号。</div>
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input v-model="form.confirm" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-button type="primary" style="width: 100%; margin-top: 8px" :loading="loading" @click="submit">
          确认修改并重新登录
        </el-button>
        <el-button link style="width: 100%; margin-top: 12px" @click="logout">退出登录</el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const formRef = ref()
const loading = ref(false)
const form = ref({ old_password: '', new_password: '', confirm: '' })

const strength = computed(() => {
  const value = form.value.new_password || ''
  let score = 0
  if (value.length >= 8) score += 1
  if (/[A-Z]/.test(value) && /[a-z]/.test(value)) score += 1
  if (/\d/.test(value) && /[^A-Za-z0-9]/.test(value)) score += 1
  return { score, class: score <= 1 ? 'weak' : score === 2 ? 'mid' : 'strong' }
})

const rules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, max: 64, message: '密码长度需为 8-64 位', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value && (!/[A-Za-z]/.test(value) || !/\d/.test(value))) callback(new Error('密码需同时包含字母与数字'))
        else callback()
      },
      trigger: 'blur'
    }
  ],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.value.new_password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur'
    }
  ]
}

async function submit() {
  await formRef.value.validate()
  loading.value = true
  try {
    await auth.changePassword({
      old_password: form.value.old_password,
      new_password: form.value.new_password
    })
    ElMessage.success('密码修改成功，请使用新密码登录')
    router.replace('/login')
  } finally {
    loading.value = false
  }
}

async function logout() {
  await auth.logout()
  router.replace('/login')
}
</script>
