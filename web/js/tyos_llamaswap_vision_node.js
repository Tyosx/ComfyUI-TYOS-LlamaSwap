import { app } from "../../scripts/app.js";

function widget(node, name) {
  return node?.widgets?.find((item) => item.name === name);
}

function displayText(node, name, initial = "") {
  const field = node.addWidget("text", name, initial, () => {}, { multiline: true });
  field.serialize = false;
  field.options = { ...(field.options || {}), readOnly: true };
  return field;
}

async function requestJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function status(node, message) {
  const field = widget(node, "Status");
  if (field) field.value = message;
  node.setDirtyCanvas?.(true, true);
}

async function refreshModels(node) {
  const api = widget(node, "api_base");
  const model = widget(node, "model_id");
  if (!api || !model) return;
  status(node, "Loading models...");
  try {
    const base = encodeURIComponent(String(api.value || "").trim());
    const data = await requestJSON(`/tyos/llamaswap/vision/models?api_base=${base}`);
    const models = data.models?.length ? data.models : ["(no models found)"];
    model.options = { ...(model.options || {}), values: models };
    if (!models.includes(model.value)) model.value = models[0];
    status(node, `Found ${data.models?.length || 0} model(s)`);
  } catch (error) {
    status(node, `Model discovery: ${error.message}`);
  }
}

function selectPrompt(node, name) {
  const prompt = widget(node, "system_prompt");
  const value = node.__tyosPresets?.[name];
  if (prompt && typeof value === "string") {
    prompt.value = value;
    prompt.callback?.(value);
    node.setDirtyCanvas?.(true, true);
  }
}

function wireSelector(node) {
  const selector = widget(node, "system_prompt_preset");
  if (!selector || selector.__tyosWired) return;
  selector.__tyosWired = true;
  const old = selector.callback;
  selector.callback = function (value) {
    const result = old?.apply(this, arguments);
    selectPrompt(node, value);
    return result;
  };
}

async function reloadPrompts(node, chosen = null, apply = false) {
  const selector = widget(node, "system_prompt_preset");
  if (!selector) return;
  try {
    const data = await requestJSON("/tyos/llamaswap/vision/prompts");
    node.__tyosPresets = data.prompts || {};
    const choices = data.names?.length ? data.names : ["Default"];
    selector.options = { ...(selector.options || {}), values: choices };
    const next = chosen || selector.value;
    selector.value = choices.includes(next) ? next : choices[0];
    wireSelector(node);
    if (apply) selectPrompt(node, selector.value);
    status(node, `Loaded ${choices.length} system-prompt preset(s)`);
  } catch (error) {
    status(node, `Preset loading: ${error.message}`);
  }
}

async function savePrompt(node) {
  const text = String(widget(node, "system_prompt")?.value || "");
  const current = String(widget(node, "system_prompt_preset")?.value || "");
  const suggestion = current && current !== "Default" ? `${current} Copy` : "New Preset";
  const entered = window.prompt("System prompt preset name:", suggestion);
  if (entered === null) return;
  const name = entered.trim();
  if (!name) {
    status(node, "A preset name is required");
    return;
  }
  if (Object.prototype.hasOwnProperty.call(node.__tyosPresets || {}, name)) {
    if (!window.confirm(`Replace existing preset "${name}"?`)) return;
  }
  try {
    await requestJSON("/tyos/llamaswap/vision/prompts/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, prompt: text }),
    });
    await reloadPrompts(node, name, true);
    status(node, `Saved system prompt: ${name}`);
  } catch (error) {
    status(node, `Saving preset: ${error.message}`);
  }
}

app.registerExtension({
  name: "TYOS.MediaPrompt.UI",
  async beforeRegisterNodeDef(nodeType, data) {
    // Preserve the original internal node identifier for older workflows.
    if (data?.name !== "TyosLlamaSwapVisionNode") return;

    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = created?.apply(this, arguments);
      this.addWidget("button", "Refresh Models", null, () => refreshModels(this));
      this.addWidget("button", "Reload System Prompts", null, () => reloadPrompts(this));
      this.addWidget("button", "Save System Prompt", null, () => savePrompt(this));
      displayText(this, "Status", "Ready");
      displayText(this, "Last Response", "");
      const size = this.computeSize?.() || [500, 650];
      this.setSize?.([Math.max(500, size[0]), Math.max(650, size[1])]);
      setTimeout(async () => {
        wireSelector(this);
        await refreshModels(this);
        await reloadPrompts(this);
      }, 0);
      return result;
    };

    const executed = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (data) {
      executed?.apply(this, arguments);
      if (data?.status?.[0]) status(this, data.status[0]);
      const preview = widget(this, "Last Response");
      if (preview && data?.preview?.[0] !== undefined) {
        preview.value = data.preview[0];
      }
      this.setDirtyCanvas?.(true, true);
    };
  },
});
