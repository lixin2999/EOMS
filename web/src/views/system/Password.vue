<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>修改密码</h2>
        <p>修改成功后当前会话立即失效，需要使用新密码重新登录；其他设备上的登录状态也会一并清除。</p>
      </div>
    </div>

    <div class="split-2" style="align-items: start">
      <div class="card">
        <div class="card-title"><h3>账号信息</h3></div>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="登录账号">{{ auth.user.username || '-' }}</el-descriptions-item>
          <el-descriptions-item label="姓名">{{ auth.user.real_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="部门">{{ auth.user.dept_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="角色">{{ roleText }}</el-descriptions-item>
          <el-descriptions-item label="最近登录">
            {{ auth.user.last_login_at ? datetime(auth.user.last_login_at) : '从未登录' }}
          </el-descriptions-item>
          <el-descriptions-item label="密码状态">
            <el-tag v-if="auth.firstLogin" type="warning" size="small" effect="plain">需修改（首登或已被重置）</el-tag>
            <el-tag v-else type="success" size="small" effect="plain">正常</el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          type="info"
          :closable="false"
          style="margin-top: 14px"
          title="管理员重置密码后，用户下次登录也会被强制要求修改密码。"
        />
      </div>

      <div class="card">
        <div class="card-title"><h3>设置新密码</h3></div>
        <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
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
          <el-form-item label="确认密码" prop="confirm">
            <el-input v-model="form.confirm" type="password" show-password autocomplete="new-password" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="loading" @click="submit">确认修改并重新登录</el-button>
            <el-button @click="resetForm">重置</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { datetime } from '@/utils/format'

const router = useRouter()
const auth = useAuthStore()
const formRef = ref()
const loading = ref(false)
const form = ref({ old_password: '', new_password: '', confirm: '' })

const roleText = computed(() => (auth.user.roles || []).map((role) => role.name).join(' / ') || '未分配角色')

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
    },
    {
      validator: (_rule, value, callback) => {
        if (value && value === form.value.old_password) callback(new Error('新密码不能与原密码相同'))
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

function resetForm() {
  form.value = { old_password: '', new_password: '', confirm: '' }
  formRef.value?.clearValidate()
}

async function submit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await auth.changePassword({
      old_password: form.value.old_password,
      new_password: form.value.new_password
    })
    ElMessage.success('密码已修改，请使用新密码重新登录')
    router.replace('/login')
  } finally {
    loading.value = false
  }
}
</script>
