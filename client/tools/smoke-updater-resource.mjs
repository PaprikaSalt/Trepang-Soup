import { Update } from "@tauri-apps/plugin-updater";
import { ref, shallowRef } from "vue";

let lastInvoke;
globalThis.window = {
  __TAURI_INTERNALS__: {
    transformCallback: () => 1,
    unregisterCallback: () => {},
    invoke: async (command, args) => {
      lastInvoke = { command, args };
    },
  },
};

const update = new Update({
  rid: 73,
  currentVersion: "1.2.0",
  version: "1.5.1",
  rawJson: {},
});

let deepRefFailureReproduced = false;
try {
  await ref(update).value.downloadAndInstall(() => {});
} catch (error) {
  deepRefFailureReproduced = String(error).includes("Cannot read private member");
}

// shallowRef 必须把原始 Tauri Resource 交还给 downloadAndInstall。
await shallowRef(update).value.downloadAndInstall(() => {});
if (!deepRefFailureReproduced || lastInvoke?.args?.rid !== 73) {
  throw new Error("updater resource proxy regression check failed");
}

console.log(
  JSON.stringify({
    deepRefFailureReproduced,
    shallowRefRid: lastInvoke.args.rid,
    command: lastInvoke.command,
  }),
);
