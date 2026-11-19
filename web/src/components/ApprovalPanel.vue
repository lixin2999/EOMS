<template>
  <div v-loading="loading" class="approval-panel">
    <template v-if="data">
      <div class="panel-head">
        <div>
          <div class="panel-title">
            {{ data.instance.title }}
            <status-tag :value="data.instance.status" />
          </div>
          <div class="panel-sub">
            发起人：{{ data.instance.initiator_name || '-' }} ·
            当前节点：{{ currentNodeName }} ·
            发起时间：{{ datetime(data.instance.start_at) }}
          </div>
        </div>
        <el-tag v-if="myTask" type="warning" effect="dark" round>待我审批</el-tag>
      </div>

      <el-steps :active="activeStep" align-center finish-status="success" class="node-steps">
        <el-step
          v-for="node in nodes"
          :key="node.code"
          :title="node.name"
          :description="node.condition && node.condition.min_amount ? `≥ ${money(node.condition.min_amount)} 触发` : ''"
        />
      </el-steps>

      <div v-if="data.instance.status === 'RUNNING'" class="action-box">
        <el-input
          v-model="comment"
          type="textarea"
          :rows="2"
          maxlength="500"
          show-word-limit
          placeholder="审批意见（驳回时必填）"
        />
        <div class="action-buttons">
          <template v-if="myTask">
            <el-button type="success" :loading="acting" @click="act('APPROVE')">同意</el-button>
            <el-button type="danger" plain :loading="acting" @click="openDialog('reject')">驳回</el-button>
            <el-button plain :loading="acting" @click="openDialog('transfer')">转办</el-button>
            <el-button plain :loading="acting" @click="openDialog('addsign')">加签</el-button>
          </template>
          <el-button v-if="isInitiator" plain :loading="acting" @click="act('WITHDRAW')">撤回</el-button>
          <el-button v-if="myTask" plain :loading="acting" @click="act('URGE')">催办</el-button>
          <el-button plain @click="openDialog('cc')">抄送</el-button>
        </div>
      </div>

      <div class="section-title">审批任务</div>
      <el-table :data="data.tasks" size="small" border>
        <el-table-column prop="node_name" label="节点" min-width="110" />
        <el-table-column prop="assignee_name" label="处理人" min-width="100" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="taskTag(row.status)">{{ taskLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="comment" label="意见" min-width="180" show-overflow-tooltip />
        <el-table-column label="到达时间" width="150">
          <template #default="{ row }">{{ datetime(row.arrive_at) }}</template>
        </el-table-column>
        <el-table-column label="处理时间" width="150">
          <template #default="{ row }">{{ datetime(row.finish_at) }}</template>
        </el-table-column>
      </el-table>

      <div class="section-title">流转记录</div>
      <div v-if="!data.records.length" class="empty">暂无流转记录</div>
      <el-timeline v-else>
        <el-timeline-item
          v-for="record in data.records"
          :key="record.id"
          :timestamp="datetime(record.created_at)"
          placement="top"
          :type="record.action === 'REJECT' ? 'danger' : record.action === 'APPROVE' ? 'success' : 'primary'"
        >
          <div style="font-weight: 600">
            {{ record.node_name || record.node_code }} · {{ record.operator_name || '系统' }}
            <el-tag size="small" style="margin-left: 8px">{{ actionLabel(record.action) }}</el-tag>
          </div>
          <div class="muted" style="margin-top: 4px">{{ record.comment || '无意见' }}</div>
        </el-timeline-item>
      </el-timeline>

      <div v-if="data.ccs && data.ccs.length" class="section-title">抄送</div>
      <div v-if="data.ccs && data.ccs.length" class="tag-row">
        <span v-for="cc in data.ccs" :key="cc.id" class="chip">{{ cc.user_name || `用户 #${cc.user_id}` }}</span>
      </div>
    </template>

    <el-dialog v-model="dialog.visible" :title="dialog.title" width="440px" append-to-body>
      <el-form label-width="90px">
        <template v-if="dialog.type === 'transfer'">
          <el-form-item label="转办给">
            <el-select v-model="dialog.targetUserId" filterable style="width: 100%" placeholder="选择处理人">
              <el-option
                v-for="user in meta.userOptions"
                :key="user.id"
                :label="`${user.real_name}（${user.username}）`"
                :value="user.id"
              />
            </el-select>
          </el-form-item>
        </template>
        <template v-if="dialog.type === 'addsign'">
          <el-form-item label="加签人">
            <el-select v-model="dialog.targetUserIds" multiple filterable style="width: 100%" placeholder="选择加签人">
              <el-option
                v-for="user in meta.userOptions"
                :key="user.id"
                :label="`${user.real_name}（${user.username}）`"
                :value="user.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="会签模式">
            <el-radio-group v-model="dialog.mode">
              <el-radio value="ANY">任一人处理</el-radio>
              <el-radio value="ALL">全部处理</el-radio>
            </el-radio-group>
          </el-form-item>
        </template>
        <template v-if="dialog.type === 'cc'">
          <el-form-item label="抄送人">
            <el-select v-model="dialog.targetUserIds" multiple filterable style="width: 100%" placeholder="选择抄送人">
              <el-option
                v-for="user in meta.userOptions"
                :key="user.id"
                :label="`${user.real_name}（${user.username}）`"
                :value="user.id"
              />
            </el-select>
          </el-form-item>
        </template>
        <template v-if="dialog.type === 'reject'">
          <el-form-item label="退回节点">
            <el-select v-model="dialog.backTo" clearable style="width: 100%" placeholder="默认退回发起人">
              <el-option v-for="node in approvalNodes" :key="node.code" :label="node.name" :value="node.code" />
            </el-select>
          </el-form-item>
          <el-form-item label="驳回原因">
            <el-input v-model="comment" type="textarea" :rows="3" placeholder="请说明驳回原因" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialog.visible = false">取消</el-button>
          <el-button type="primary" :loading="acting" @click="confirmDialog">确认</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { workflowApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useMetaStore } from '@/stores/meta'
import StatusTag from '@/components/StatusTag.vue'
import { datetime, money } from '@/utils/format'
import { WORKFLOW_ACTIONS } from '@/utils/constants'

const props = defineProps({
  instanceId: { type: Number, default: null }
})
const emit = defineEmits(['changed'])

const auth = useAuthStore()
const meta = useMetaStore()
const loading = ref(false)
const acting = ref(false)
const data = ref(null)
const comment = ref('')
const dialog = ref({
  visible: false,
  type: '',
  title: '',
  targetUserId: null,
  targetUserIds: [],
  mode: 'ANY',
  backTo: null
})

const nodes = computed(() => (data.value?.definition?.nodes_json?.nodes || []).filter((node) => node.type !== 'START' && node.type !== 'END'))
const approvalNodes = computed(() => nodes.value.filter((node) => node.type === 'APPROVAL'))
const activeStep = computed(() => {
  if (!data.value) return 0
  if (data.value.instance.status !== 'RUNNING') return nodes.value.length
  const index = nodes.value.findIndex((node) => node.code === data.value.instance.current_node)
  return index < 0 ? 0 : index
})
const myTask = computed(() =>
  (data.value?.tasks || []).find(
    (task) =>
      task.status === 'PENDING' &&
      (task.assignee_id === auth.user.id || (task.candidate_ids || []).includes(auth.user.id))
  )
)
const isInitiator = computed(() => data.value?.instance?.initiator_id === auth.user.id)
const currentNodeName = computed(() => {
  if (!data.value) return '-'
  const node = nodes.value.find((item) => item.code === data.value.instance.current_node)
  return node?.name || data.value.instance.current_node || '-'
})

function taskLabel(status) {
  return { PENDING: '待处理', APPROVED: '已同意', REJECTED: '已驳回', TRANSFERRED: '已转办', SKIPPED: '已跳过', CANCELED: '已取消' }[status] || status
}

function taskTag(status) {
  return { PENDING: 'warning', APPROVED: 'success', REJECTED: 'danger', TRANSFERRED: 'info' }[status] || 'info'
}

function actionLabel(action) {
  return WORKFLOW_ACTIONS[action] || action || '-'
}

async function load() {
  if (!props.instanceId) {
    data.value = null
    return
  }
  loading.value = true
  try {
    data.value = await workflowApi.instance(props.instanceId)
  } finally {
    loading.value = false
  }
}

async function act(action) {
  if (!data.value) return
  if (action === 'REJECT' && !comment.value.trim()) {
    ElMessage.warning('请填写驳回原因')
    return
  }
  acting.value = true
  try {
    await workflowApi.action(data.value.instance.id, {
      action,
      task_id: myTask.value?.id || null,
      comment: comment.value || null
    })
    ElMessage.success('操作成功')
    comment.value = ''
    await load()
    emit('changed')
  } finally {
    acting.value = false
  }
}

function openDialog(type) {
  const titles = { transfer: '转办', addsign: '加签', cc: '抄送', reject: '驳回' }
  dialog.value = {
    visible: true,
    type,
    title: titles[type] || '操作',
    targetUserId: null,
    targetUserIds: [],
    mode: 'ANY',
    backTo: null
  }
}

async function confirmDialog() {
  if (!data.value) return
  const type = dialog.value.type
  acting.value = true
  try {
    if (type === 'reject') {
      if (!comment.value.trim()) {
        ElMessage.warning('请填写驳回原因')
        return
      }
      await workflowApi.action(data.value.instance.id, {
        action: 'REJECT',
        task_id: myTask.value?.id || null,
        comment: comment.value,
        back_to: dialog.value.backTo || null
      })
    } else if (type === 'transfer') {
      if (!dialog.value.targetUserId) {
        ElMessage.warning('请选择转办人')
        return
      }
      await workflowApi.action(data.value.instance.id, {
        action: 'TRANSFER',
        task_id: myTask.value?.id || null,
        comment: comment.value || null,
        target_user_id: dialog.value.targetUserId
      })
    } else if (type === 'addsign') {
      if (!dialog.value.targetUserIds.length) {
        ElMessage.warning('请选择加签人')
        return
      }
      await workflowApi.action(data.value.instance.id, {
        action: 'ADD_SIGN',
        task_id: myTask.value?.id || null,
        comment: comment.value || null,
        target_user_ids: dialog.value.targetUserIds,
        mode: dialog.value.mode
      })
    } else if (type === 'cc') {
      if (!dialog.value.targetUserIds.length) {
        ElMessage.warning('请选择抄送人')
        return
      }
      await workflowApi.action(data.value.instance.id, {
        action: 'CC',
        comment: comment.value || null,
        cc_user_ids: dialog.value.targetUserIds
      })
    }
    ElMessage.success('操作成功')
    dialog.value.visible = false
    comment.value = ''
    await load()
    emit('changed')
  } finally {
    acting.value = false
  }
}

onMounted(async () => {
  await meta.ensure()
  await load()
})

watch(() => props.instanceId, () => load())

defineExpose({ reload: load })
</script>

<style scoped>
.approval-panel {
  min-height: 120px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.panel-title {
  font-size: 16px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-sub {
  color: #6b7280;
  font-size: 12.5px;
  margin-top: 6px;
}

.node-steps {
  margin-bottom: 18px;
}

.action-box {
  background: #f8fafc;
  border: 1px solid #e6e9f0;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 6px;
}

.action-buttons {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}
</style>
