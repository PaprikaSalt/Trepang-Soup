import { createRouter, createWebHashHistory, type RouteRecordRaw } from "vue-router";

import { adminEnabled } from "../config/features";
import GameRoomView from "../views/GameRoomView.vue";
import HistoryView from "../views/HistoryView.vue";
import HomeView from "../views/HomeView.vue";
import LobbyView from "../views/LobbyView.vue";
import SettlementView from "../views/SettlementView.vue";

const routes: RouteRecordRaw[] = [
  { path: "/", name: "home", component: HomeView },
  { path: "/lobby/:code", name: "lobby", component: LobbyView },
  { path: "/room/:code", name: "room", component: GameRoomView },
  { path: "/settlement/:code", name: "settlement", component: SettlementView },
  { path: "/history", name: "history", component: HistoryView },
];

if (adminEnabled) {
  routes.push({
    path: "/library",
    name: "library",
    component: () => import("../views/LibraryView.vue"),
  });
}

routes.push({ path: "/:pathMatch(.*)*", redirect: "/" });

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.afterEach(() => {
  // The modal focus trap can scroll an overflow-hidden root; reset it after route changes.
  window.requestAnimationFrame(() => {
    window.scrollTo(0, 0);
    document.querySelector<HTMLElement>(".app-shell")?.scrollTo(0, 0);
  });
});

export default router;
