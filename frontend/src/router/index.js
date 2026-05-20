import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import VideoDetail from '../views/VideoDetail.vue'
import AddVideo from '../views/AddVideo.vue'
import Settings from '../views/Settings.vue'

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard },
  { path: '/video/:id', name: 'VideoDetail', component: VideoDetail },
  { path: '/add', name: 'AddVideo', component: AddVideo },
  { path: '/settings', name: 'Settings', component: Settings },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
