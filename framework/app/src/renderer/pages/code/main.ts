// import './setEnv';
import { createApp } from 'vue';
import App from '@kungfu-trader/kungfu-app/src/renderer/pages/code/App.vue';
import store from '../index/store';
import VueVirtualScroller from 'vue-virtual-scroller';
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css';
import { Input, Button } from 'ant-design-vue';
import 'monaco-editor/min/vs/editor/editor.main.css';
import { useCodeStore } from '@kungfu-trader/kungfu-app/src/renderer/pages/code/store/codeStore';
const app = createApp(App);

app.component('ComFileNode');
app.use(Input).use(Button).use(store).use(VueVirtualScroller);

app.config.globalProperties.$useCodeStore = useCodeStore;

app.mount('#app');

window.fileId = 0;
