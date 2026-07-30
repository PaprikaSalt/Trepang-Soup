import { createRouter, createWebHashHistory } from "vue-router";

import GameRoomView from "../views/GameRoomView.vue";
import HistoryView from "../views/HistoryView.vue";
import HomeView from "../views/HomeView.vue";
import LibraryView from "../views/LibraryView.vue";
import LobbyView from "../views/LobbyView.vue";
import SettlementView from "../views/SettlementView.vue";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/lobby/:code", name: "lobby", component: LobbyView },
    { path: "/room/:code", name: "room", component: GameRoomView },
    { path: "/settlement/:code", name: "settlement", component: SettlementView },
    { path: "/history", name: "history", component: HistoryView },
    { path: "/library", name: "library", component: LibraryView },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.afterEach(() => {
  // The modal focus trap can scroll an overflow-hidden root; reset it after route changes.
  window.requestAnimationFrame(() => {
    window.scrollTo(0, 0);
    document.querySelector<HTMLElement>(".app-shell")?.scrollTo(0, 0);
  });
});

export default router;
