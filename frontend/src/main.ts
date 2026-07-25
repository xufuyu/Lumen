import { createApp } from 'vue'
import './assets/fa-all.css'
import './style.css'
import App from './App.vue'
import { router } from './router'
import { i18n } from './i18n'
import './install' // register beforeinstallprompt listener early

createApp(App).use(router).use(i18n).mount('#app')
