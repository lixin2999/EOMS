<template>
  <div class="login-page">
    <section class="login-hero">
      <div class="company-content">
        <div class="login-brand">
          <img class="brand-mark" src="/brand/dongyan-logo.jpg" alt="东研智联 Logo" />
          <div class="brand-copy">
            <span>东研智联科技企业运营管理系统</span>
            <small>武汉东研智联科技有限公司</small>
          </div>
        </div>

        <div class="company-intro">
          <div class="company-kicker"><span />公司简介</div>
          <h1>数字化与智能化<br />技术服务<span>企业</span></h1>
          <p>
            武汉东研智联科技有限公司是武汉东研智慧设计研究院有限公司的全资子公司，专注数字化与智能化技术服务。依托武汉经济技术开发区“中国车谷”的产业政策与区位优势，持续深耕智能网联车路协同、低空经济、智慧园区节能减碳等领域。
          </p>
          <p>
            公司以 BIM + GIS + 点云 + 设备集成 + 工艺需求 + AI 为技术底座，开展软硬一体化产品与弱电系统集成研发应用，为试验场数字化建造、自动驾驶测试管理和车路云一体化提供综合技术服务。
          </p>
          <div class="company-tags">
            <span>全资子公司</span>
            <span>中国车谷</span>
            <span>BIM + GIS + AI</span>
          </div>

          <div class="company-business">
            <article class="company-business-item">
              <img src="/brand/business-test-field.webp" alt="智能网联汽车试验场" loading="lazy" />
              <div>
                <strong>汽车试验场业务</strong>
                <span>EPC 设计、数字化建造与运维</span>
              </div>
            </article>
            <article class="company-business-item">
              <img src="/brand/business-autonomous-driving.webp" alt="自动驾驶测试" loading="lazy" />
              <div>
                <strong>自动驾驶测试类</strong>
                <span>下线检测、虚拟仿真、标定与无人测试</span>
              </div>
            </article>
            <article class="company-business-item">
              <img src="/brand/business-road-cloud.webp" alt="车路云一体化" loading="lazy" />
              <div>
                <strong>车路云一体化</strong>
                <span>场景规划、系统设计与落地实施</span>
              </div>
            </article>
            <article class="company-business-item">
              <img src="/brand/business-low-altitude.webp" alt="低空经济业务" loading="lazy" />
              <div>
                <strong>低空经济业务</strong>
                <span>试验场建设、适航审定与仿真测试</span>
              </div>
            </article>
          </div>
        </div>
      </div>
      <div class="login-copyright">© 2026 武汉东研智联科技有限公司</div>
    </section>

    <section class="login-panel">
      <div class="login-form">
        <div class="login-mobile-hint">
          <img class="brand-mark" src="/brand/dongyan-logo.jpg" alt="东研智联 Logo" />
          <span>东研智联科技企业运营管理系统</span>
        </div>
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
