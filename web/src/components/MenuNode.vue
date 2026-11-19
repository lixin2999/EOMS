<template>
  <el-sub-menu v-if="menu.children && menu.children.length" :index="`group-${menu.id}`">
    <template #title>
      <el-icon><component :is="resolveIcon(menu.icon)" /></el-icon>
      <span>{{ menu.name }}</span>
    </template>
    <menu-node v-for="child in menu.children" :key="child.id" :menu="child" />
  </el-sub-menu>
  <el-menu-item v-else :index="menu.path || `item-${menu.id}`">
    <el-icon><component :is="resolveIcon(menu.icon)" /></el-icon>
    <template #title>{{ menu.name }}</template>
  </el-menu-item>
</template>

<script setup>
defineOptions({ name: 'MenuNode' })

defineProps({
  menu: { type: Object, required: true }
})

const FALLBACK_ICONS = ['Folder', 'Document', 'Grid']

function resolveIcon(icon) {
  if (!icon) return 'Menu'
  const normalized = icon.charAt(0).toUpperCase() + icon.slice(1)
  const known = [
    'Odometer', 'Stamp', 'Money', 'Calendar', 'Document', 'List', 'Connection',
    'Folder', 'OfficeBuilding', 'Tickets', 'Coin', 'DataLine', 'Wallet',
    'CreditCard', 'TrendCharts', 'PieChart', 'BarChart', 'Notebook', 'Setting',
    'Menu', 'User', 'UserFilled', 'Files', 'Grid', 'Management', 'Lock'
  ]
  return known.includes(normalized) ? normalized : FALLBACK_ICONS[0]
}
</script>
