<template>
  <div style="min-height: 100vh; display: grid; place-items: center; background: #f3f5f9">
    <el-result icon="info" title="404" sub-title="页面不存在或已被移除。">
      <template #extra>
        <el-button type="primary" @click="$router.replace('/dashboard')">返回工作台</el-button>
      </template>
    </el-result>
  </div>
</template>
