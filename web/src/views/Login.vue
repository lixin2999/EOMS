<template>
  <div class="login-page">
    <section class="login-hero">
      <div>
        <div class="login-brand">
          <div class="brand-mark">E</div>
          <span>EOMS 企业运营管理系统</span>
        </div>
        <div style="margin-top: 72px">
          <h1>让审批、项目与经营数据<br />在同一条链路上<span>自动流动</span></h1>
          <p>
            从日常报销、请假、用印审批，到项目全生命周期、供应商与合同管理，再到成本核算与经营报表，
            统一数据域、统一口径、统一留痕，消除 Excel 台账与数据孤岛。
          </p>
          <div class="login-points">
            <div class="login-point">
              <strong>可配置四级审批流</strong>
              <span>阈值升级、节点加签会签、转办催办与全流程留痕</span>
            </div>
            <div class="login-point">
              <strong>项目全周期经营</strong>
              <span>立项、WBS、里程碑、变更、验收、归档与项目损益</span>
            </div>
            <div class="login-point">
              <strong>成本与现金流口径统一</strong>
              <span>报销、付款、收款、计收自动归集，报表与台账同源</span>
            </div>
            <div class="login-point">
              <strong>数据域与敏感信息保护</strong>
              <span>多角色权限并集收敛、字段级脱敏与全量审计日志</span>
            </div>
          </div>
        </div>
      </div>
      <div style="font-size: 12px; color: #64748b">© 2026 EOMS · 企业运营管理平台</div>
    </section>

    <section class="login-panel">
      <div class="login-form">
        <div class="login-mobile-hint">EOMS 企业运营管理系统</div>
        <h2>登录工作台</h2>
        <div class="sub">使用企业账号登录，所有操作均会记录审计日志</div>

        <el-form ref="formRef" :model="form" :rules="rules" size="large" @keyup.enter="submit">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="账号" :prefix-icon="User" autocomplete="username" />
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="密码"
              :prefix-icon="Lock"
              show-password
              autocomplete="current-password"
            />
          </el-form-item>
          <el-form-item prop="captcha_code">
            <div class="captcha-row">
              <el-input v-model="form.captcha_code" placeholder="图形验证码" :prefix-icon="Key" maxlength="6" />
              <img
                v-if="captcha.image"
                :src="captcha.image"
                class="captcha-img"
                alt="验证码"
                title="点击刷新验证码"
                @click="loadCaptcha"
              />
              <div v-else class="captcha-img" style="display: grid; place-items: center; color: #94a3b8" @click="loadCaptcha">
                加载中
              </div>
            </div>
          </el-form-item>
          <el-button type="primary" size="large" style="width: 100%; margin-top: 4px" :loading="auth.loading" @click="submit">
            登 录
          </el-button>
        </el-form>

        <div v-if="isDev" class="login-tip">
          演示账号：<span class="mono">admin</span>（管理员，首次登录需改密）、
          <span class="mono">director</span> / <span class="mono">manager</span> / <span class="mono">leader</span> /
          <span class="mono">pm</span> / <span class="mono">finance</span> / <span class="mono">purchase</span> /
          <span class="mono">employee</span> / <span class="mono">auditor</span>，统一密码
          <span class="mono">Eoms@2026</span>。
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Key, Lock, User } from '@element-plus/icons-vue'
import { authApi } from '@/api'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const formRef = ref()
const captcha = reactive({ id: '', image: '' })
const isDev = import.meta.env.DEV
const form = reactive({ username: '', password: '', captcha_code: '' })

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  captcha_code: [{ required: true, message: '请输入验证码', trigger: 'blur' }]
}

async function loadCaptcha() {
  try {
    const data = await authApi.captcha()
    captcha.id = data.captcha_id
    captcha.image = data.image
    form.captcha_code = ''
  } catch {
    /* 错误提示由拦截器处理 */
  }
}

async function submit() {
  await formRef.value.validate()
  try {
    await auth.login({
      username: form.username.trim(),
      password: form.password,
      captcha_id: captcha.id,
      captcha_code: form.captcha_code
    })
    ElMessage.success(`欢迎回来，${auth.user.real_name || auth.user.username}`)
    if (auth.firstLogin) {
      router.replace('/change-password')
      return
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    router.replace(redirect)
  } catch {
    loadCaptcha()
  }
}

onMounted(loadCaptcha)
</script>
