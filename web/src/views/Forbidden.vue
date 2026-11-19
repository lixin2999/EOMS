<template>
  <div style="min-height: 100vh; display: grid; place-items: center; background: #f3f5f9">
    <el-result icon="warning" title="403" sub-title="抱歉，您没有访问该页面的权限。">
      <template #extra>
        <el-button type="primary" @click="$router.replace('/dashboard')">返回工作台</el-button>
      </template>
    </el-result>
  </div>
</template>
