<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import Chart from 'chart.js/auto'

const loading = ref(true)
const errorMessage = ref('')
const syncMessage = ref('')
const syncing = ref(false)
const branches = ref([])
const branchId = ref(0)
const summary = ref({})
const errors = ref({ items: [], page: 1, pages: 1, total: 0 })
const topErrors = ref([])
const timeline = ref([])
const selected = ref(null)
const page = ref(1)
const q = ref('')
const days = ref(30)
const timelineCanvas = ref(null)
const topCanvas = ref(null)
let timelineChart
let topChart

const api = async (url, options = {}) => {
  const response = await fetch(url, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

const formatDate = (value) => {
  if (!value) return '-'
  return new Intl.DateTimeFormat('es-AR', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(new Date(value))
}

const displayValue = (value) => {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

const pageLabel = computed(() => `${errors.value.page} / ${errors.value.pages}`)
const currentBranch = computed(() => branches.value.find((item) => item.id_sucursal === branchId.value))

async function loadBranches() {
  const data = await api('/api/branches')
  branches.value = [{ id_sucursal: 0, nombre: 'Casa Central', local: true }, ...data.items]
}

function buildRemoteDashboard(items) {
  const now = new Date()
  const since = new Date(now)
  since.setDate(since.getDate() - days.value)
  const filteredByDays = items.filter((item) => {
    if (!item.fecha_hora) return false
    return new Date(item.fecha_hora) >= since
  })
  const term = q.value.trim().toLowerCase()
  const filtered = term
    ? filteredByDays.filter((item) => [
        item.mensaje, item.nom_error, item.metodo, item.objeto,
        item.formulario, item.control, item.codigo_fuente,
      ].some((value) => String(value || '').toLowerCase().includes(term)))
    : filteredByDays

  filtered.sort((a, b) => new Date(b.fecha_hora || 0) - new Date(a.fecha_hora || 0))
  const total = filtered.length
  const pageSize = 25
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (page.value > pages) page.value = pages
  const start = (page.value - 1) * pageSize

  errors.value = {
    items: filtered.slice(start, start + pageSize),
    page: page.value,
    page_size: pageSize,
    total,
    pages,
  }

  const today = now.toISOString().slice(0, 10)
  summary.value = {
    hoy: filteredByDays.filter((item) => String(item.fecha_hora || '').slice(0, 10) === today).length,
    total: filteredByDays.length,
    tipos_error: new Set(filteredByDays.map((item) => item.nro_error)).size,
    equipos: new Set(filteredByDays.map((item) => item.maquina).filter(Boolean)).size,
    version_actual: filteredByDays[0]?.version_sistema || '-',
  }

  const perDay = new Map()
  const perError = new Map()
  for (const item of filteredByDays) {
    const day = String(item.fecha_hora || '').slice(0, 10)
    if (day) perDay.set(day, (perDay.get(day) || 0) + 1)
    const key = String(item.nro_error ?? '-')
    perError.set(key, (perError.get(key) || 0) + 1)
  }
  timeline.value = [...perDay.entries()].sort().map(([fecha, cantidad]) => ({ fecha, cantidad }))
  topErrors.value = [...perError.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([valor, cantidad]) => ({ valor, cantidad }))
}

async function loadDashboard() {
  loading.value = true
  errorMessage.value = ''
  try {
    if (branchId.value === 0) {
      const query = new URLSearchParams({ page: String(page.value), page_size: '25' })
      if (q.value.trim()) query.set('q', q.value.trim())
      const [summaryData, errorsData, timelineData, topData] = await Promise.all([
        api(`/api/dashboard/summary?days=${days.value}`),
        api(`/api/errors?${query}`),
        api(`/api/dashboard/timeline?days=${Math.min(days.value, 365)}`),
        api(`/api/dashboard/top?field=nro_error&days=${days.value}&limit=8`),
      ])
      summary.value = summaryData
      errors.value = errorsData
      timeline.value = timelineData.items
      topErrors.value = topData.items
    } else {
      const remoteData = await api(`/api/branches/${branchId.value}/errors`)
      buildRemoteDashboard(remoteData.items)
    }
    await nextTick()
    renderCharts()
  } catch (err) {
    errorMessage.value = err.message
  } finally {
    loading.value = false
  }
}

async function syncCurrentBranch() {
  if (branchId.value === 0) return
  syncing.value = true
  syncMessage.value = ''
  errorMessage.value = ''
  try {
    const result = await api(`/api/sync/${branchId.value}`, { method: 'POST' })
    syncMessage.value = `Sincronización completada: ${result.imported} error(es) nuevo(s).`
    await loadBranches()
    await loadDashboard()
  } catch (err) {
    errorMessage.value = err.message
  } finally {
    syncing.value = false
  }
}

function renderCharts() {
  timelineChart?.destroy()
  topChart?.destroy()
  if (timelineCanvas.value) {
    timelineChart = new Chart(timelineCanvas.value, {
      type: 'line',
      data: {
        labels: timeline.value.map((item) => item.fecha),
        datasets: [{ label: 'Errores', data: timeline.value.map((item) => item.cantidad), tension: 0.28, fill: true }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    })
  }
  if (topCanvas.value) {
    topChart = new Chart(topCanvas.value, {
      type: 'bar',
      data: {
        labels: topErrors.value.map((item) => item.valor),
        datasets: [{ label: 'Cantidad', data: topErrors.value.map((item) => item.cantidad) }],
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    })
  }
}

async function openError(item) {
  if (branchId.value !== 0) {
    selected.value = item
    return
  }
  try {
    selected.value = await api(`/api/errors/${item._id}`)
  } catch {
    selected.value = item
  }
}

function search() { page.value = 1; loadDashboard() }
function previousPage() { if (page.value > 1) { page.value -= 1; loadDashboard() } }
function nextPage() { if (page.value < errors.value.pages) { page.value += 1; loadDashboard() } }

watch(days, () => { page.value = 1; loadDashboard() })
watch(branchId, () => { page.value = 1; q.value = ''; syncMessage.value = ''; loadDashboard() })

onMounted(async () => {
  try {
    await loadBranches()
  } catch (err) {
    errorMessage.value = err.message
  }
  await loadDashboard()
})
</script>

<template>
  <main class="shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">FASA</p>
        <h1>Monitor de errores</h1>
        <p class="muted">Visual FoxPro · MySQL · diagnóstico de producción</p>
      </div>
      <div class="toolbar">
        <select v-model.number="branchId" aria-label="Sucursal">
          <option v-for="branch in branches" :key="branch.id_sucursal" :value="branch.id_sucursal">
            {{ branch.nombre }}
          </option>
        </select>
        <select v-model.number="days" aria-label="Período">
          <option :value="7">7 días</option>
          <option :value="30">30 días</option>
          <option :value="90">90 días</option>
          <option :value="365">1 año</option>
        </select>
        <button v-if="branchId !== 0" :disabled="syncing" @click="syncCurrentBranch">
          {{ syncing ? 'Sincronizando...' : 'Sincronizar ahora' }}
        </button>
        <button class="secondary" @click="loadDashboard">Actualizar</button>
      </div>
    </header>

    <div v-if="branchId !== 0" class="sync-panel">
      <div>
        <strong>{{ currentBranch?.nombre }}</strong>
        <span>Servidor: {{ currentBranch?.servidor || '-' }}:{{ currentBranch?.puerto || 3306 }}</span>
      </div>
      <div>
        <span>Última sincronización</span>
        <strong>{{ formatDate(currentBranch?.sync?.last_success_at) }}</strong>
      </div>
      <div>
        <span>Último ID remoto</span>
        <strong>{{ currentBranch?.sync?.last_remote_id ?? 0 }}</strong>
      </div>
    </div>

    <div v-if="syncMessage" class="success">{{ syncMessage }}</div>
    <div v-if="errorMessage" class="alert">{{ errorMessage }}</div>

    <section class="cards">
      <article class="metric"><span>Hoy</span><strong>{{ summary.hoy ?? 0 }}</strong></article>
      <article class="metric"><span>Período</span><strong>{{ summary.total ?? 0 }}</strong></article>
      <article class="metric"><span>Tipos de error</span><strong>{{ summary.tipos_error ?? 0 }}</strong></article>
      <article class="metric"><span>Equipos</span><strong>{{ summary.equipos ?? 0 }}</strong></article>
      <article class="metric accent"><span>Versión actual</span><strong>{{ summary.version_actual || '-' }}</strong></article>
    </section>

    <section class="charts">
      <article class="panel chart-panel">
        <div class="panel-title"><div><h2>Errores por día</h2><p>Volumen de incidencias en el período seleccionado</p></div></div>
        <div class="chart-wrap"><canvas ref="timelineCanvas"></canvas></div>
      </article>
      <article class="panel chart-panel">
        <div class="panel-title"><div><h2>Errores más frecuentes</h2><p>Agrupados por número de error VFP</p></div></div>
        <div class="chart-wrap"><canvas ref="topCanvas"></canvas></div>
      </article>
    </section>

    <section class="panel">
      <div class="panel-title table-heading">
        <div><h2>Últimos errores · {{ currentBranch?.nombre || 'Casa Central' }}</h2><p>{{ errors.total ?? 0 }} registros encontrados</p></div>
        <form class="search" @submit.prevent="search">
          <input v-model="q" type="search" placeholder="Buscar mensaje, método, objeto, código..." />
          <button>Buscar</button>
        </form>
      </div>
      <div class="table-scroll">
        <table>
          <thead><tr><th>Fecha</th><th>Error</th><th>Mensaje</th><th>Formulario / control</th><th>Usuario</th><th>Equipo</th><th>Versión</th></tr></thead>
          <tbody>
            <tr v-for="item in errors.items" :key="item._id || item.id_error" @click="openError(item)">
              <td class="nowrap">{{ formatDate(item.fecha_hora) }}</td>
              <td><span class="badge">{{ displayValue(item.nro_error) }}</span></td>
              <td class="message-cell">{{ item.mensaje || item.nom_error }}</td>
              <td><strong>{{ displayValue(item.formulario) }}</strong><small>{{ displayValue(item.control || item.metodo) }}</small></td>
              <td>{{ displayValue(item.usuario) }}</td><td>{{ displayValue(item.maquina) }}</td><td>{{ displayValue(item.version_sistema) }}</td>
            </tr>
            <tr v-if="!loading && !errors.items.length"><td colspan="7" class="empty">No hay errores para mostrar.</td></tr>
          </tbody>
        </table>
      </div>
      <footer class="pager">
        <button class="secondary" :disabled="page <= 1" @click="previousPage">Anterior</button>
        <span>Página {{ pageLabel }}</span>
        <button class="secondary" :disabled="page >= errors.pages" @click="nextPage">Siguiente</button>
      </footer>
    </section>

    <div v-if="selected" class="modal-backdrop" @click.self="selected = null">
      <article class="modal">
        <header class="modal-header"><div><p class="eyebrow">Detalle de incidencia</p><h2>Error {{ selected.nro_error }}</h2></div><button class="icon-btn" @click="selected = null">×</button></header>
        <div class="detail-grid">
          <div><span>Fecha</span><strong>{{ formatDate(selected.fecha_hora) }}</strong></div><div><span>Versión</span><strong>{{ displayValue(selected.version_sistema) }}</strong></div>
          <div><span>Usuario</span><strong>{{ displayValue(selected.usuario) }}</strong></div><div><span>Equipo</span><strong>{{ displayValue(selected.maquina) }}</strong></div>
          <div><span>Formulario</span><strong>{{ displayValue(selected.formulario) }}</strong></div><div><span>Control</span><strong>{{ displayValue(selected.control) }}</strong></div>
          <div><span>Método</span><strong>{{ displayValue(selected.metodo) }}</strong></div><div><span>Línea</span><strong>{{ displayValue(selected.linea) }}</strong></div>
          <div><span>Objeto</span><strong>{{ displayValue(selected.objeto) }}</strong></div><div><span>Alias</span><strong>{{ displayValue(selected.alias_actual) }}</strong></div>
          <div><span>RECNO</span><strong>{{ displayValue(selected.recno) }}</strong></div><div><span>DataSession</span><strong>{{ displayValue(selected.datasession) }}</strong></div>
        </div>
        <section class="detail-section"><h3>Mensaje</h3><pre>{{ selected.mensaje || selected.nom_error }}</pre></section>
        <section class="detail-section"><h3>Código fuente</h3><pre>{{ selected.codigo_fuente || 'No disponible' }}</pre></section>
        <section class="detail-section"><h3>Call stack</h3><pre>{{ selected.call_stack || 'No disponible' }}</pre></section>
        <section class="detail-section"><h3>AERROR / información adicional</h3><pre>{{ selected.info_extra || 'No disponible' }}</pre></section>
        <section class="detail-section"><h3>Tablas abiertas</h3><pre>{{ selected.tablas_abiertas || 'No disponible' }}</pre></section>
      </article>
    </div>
  </main>
</template>
