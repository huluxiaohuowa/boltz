import React from "react";
import { createRoot } from "react-dom/client";
import { Editor } from "ketcher-react";
import { StandaloneStructServiceProvider } from "ketcher-standalone";
import "ketcher-react/dist/index.css";

const state = {
  root: null,
  container: null,
  ketcher: null,
  readyPromise: null,
  resolveReady: null,
  rejectReady: null,
  initialMolecule: "",
};

function KetcherHost({ staticResourcesUrl, initialMolecule }) {
  const provider = React.useMemo(() => new StandaloneStructServiceProvider(), []);

  const handleInit = React.useCallback(
    async (ketcher) => {
      state.ketcher = ketcher;
      window.ketcher = ketcher;
      try {
        if (initialMolecule) {
          await ketcher.setMolecule(initialMolecule, { needZoom: true });
        }
        state.resolveReady?.(ketcher);
      } catch (error) {
        state.rejectReady?.(error);
      }
    },
    [initialMolecule],
  );

  return (
    <Editor
      staticResourcesUrl={staticResourcesUrl}
      structServiceProvider={provider}
      onInit={handleInit}
      errorHandler={(message) => {
        console.error("[BoltzKetcher]", message);
      }}
    />
  );
}

function waitForReady() {
  if (state.ketcher) return Promise.resolve(state.ketcher);
  if (!state.readyPromise) {
    state.readyPromise = new Promise((resolve, reject) => {
      state.resolveReady = resolve;
      state.rejectReady = reject;
    });
  }
  return state.readyPromise;
}

async function mount(container, options = {}) {
  if (!container) throw new Error("missing Ketcher container");
  const staticResourcesUrl = options.staticResourcesUrl || "/static/vendor/ketcher";
  if (state.root && state.container === container) {
    return waitForReady();
  }
  state.container = container;
  state.ketcher = null;
  state.readyPromise = new Promise((resolve, reject) => {
    state.resolveReady = resolve;
    state.rejectReady = reject;
  });
  state.root = createRoot(container);
  state.root.render(
    <KetcherHost staticResourcesUrl={staticResourcesUrl} initialMolecule={state.initialMolecule} />,
  );
  return waitForReady();
}

async function setMolecule(structure) {
  state.initialMolecule = structure || "";
  const ketcher = await waitForReady();
  await ketcher.setMolecule(structure || "", { needZoom: true });
}

async function getMolfile() {
  const ketcher = await waitForReady();
  return ketcher.getMolfile();
}

async function getSmiles() {
  const ketcher = await waitForReady();
  return ketcher.getSmiles();
}

async function clear() {
  await setMolecule("");
}

window.BoltzKetcher = {
  mount,
  setMolecule,
  getMolfile,
  getSmiles,
  clear,
  isReady: () => Boolean(state.ketcher),
};
