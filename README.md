# ComfyUI-TYOS-LlamaSwap

A custom ComfyUI node for working with **llama-swap** through an OpenAI-compatible API, with support for text, images, video, audio, reusable system prompts, token presets, and optional duration guidance.

The goal is simple: connect ComfyUI directly to a local or remote llama-swap server and use vision-language / multimodal models without leaving the workflow.

## Current version

**v0.9**

## Main node

`TYOS Llama-Swap Vision Node`

Category:

`TYOS/AI`

## What it can do

- Connect to any llama-swap server exposing an OpenAI-compatible `/v1` API.
- Discover available models with **Refresh Models**.
- Send a separate **System Prompt** and **User Prompt**.
- Save and switch between reusable system-prompt presets.
- Keep temporary edits temporary until you explicitly press **Save System Prompt**.
- Send multiple media inputs to multimodal models.
- Control generation length with token presets or a custom value.
- Add an optional video-duration instruction.
- Free ComfyUI VRAM before/after the request.
- Ask llama-swap to unload the selected model after generation.

## Multimodal inputs

The node supports up to:

- **9 images**
- **3 videos**
- **3 audio inputs**
- **12 total media items maximum**

The total media limit is shared.

Examples:

```text
9 images + 3 videos = 12 ✅
9 images + 2 videos + 1 audio = 12 ✅
7 images + 3 videos + 2 audio = 12 ✅
9 images + 3 videos + 1 audio = 13 ❌
```

Each media item is labeled before it is sent to the model:

```text
[Image 1]
[Image 2]
[Video 1]
[Audio 1]
```

This helps multimodal models keep references separated.

> Actual image, video, and audio understanding depends on the selected model and its llama-swap configuration.

## Image support

Images are converted to **lossless PNG** data URLs before being sent to the model.

For image understanding, use a vision-capable model and configure any required projector / mmproj file in llama-swap.

## Video support

The node accepts native ComfyUI `VIDEO` inputs.

Up to **3 videos** can be connected at once.

The node sends the video data to the OpenAI-compatible multimodal request without intentionally reducing it to a single frame.

Video support still depends on the selected model and backend.

## Audio support

The node accepts ComfyUI `AUDIO` inputs.

Audio is converted to WAV before being sent.

Up to **3 audio inputs** can be connected at once.

Use an audio-capable multimodal model if you expect the model to understand sound or speech.

## Token control

Built-in token modes:

| Mode | Max tokens |
| --- | ---: |
| Low | 512 |
| Mid | 2048 |
| High | 8192 |
| Max | 12288 |
| Custom | 1 to 65536 |

`Custom` lets you enter your own maximum generation value.

The actual usable limit still depends on the selected model and llama-swap backend.

## Duration control

The node includes:

- `use_duration`
- `duration_seconds`
- `duration_in`

When duration is enabled, the node adds a timing instruction to the request so video prompts can be written for a specific duration.

`duration_in` can accept integer or floating-point numeric values.

Examples:

```text
5
5.5
8.25
10
```

When `use_duration` is disabled, no duration instruction is sent.

## System Prompt presets

Saved presets are stored locally in:

```text
system_prompts.json
```

You can:

- choose a saved preset
- edit the current system prompt freely
- use the edited text without saving it
- press **Save System Prompt** only when you want to keep it permanently

When saving, the node asks for a preset name.

If that name already exists, it asks before overwriting it.

### Privacy

Your personal:

```text
system_prompts.json
```

is intended to stay local and is ignored by Git.

The public repository should only contain:

```text
system_prompts.example.json
```

with a safe default preset.

This keeps your private prompts out of the repository.

## llama-swap connection

Default API base:

```text
http://127.0.0.1:4726/v1
```

If llama-swap is running on another machine, change it to that machine's address, for example:

```text
http://192.168.x.x:4726/v1
```

Then press:

`Refresh Models`

and select the model from the dropdown.

## VRAM controls

### `free_comfyui_vram`

When enabled, the node asks ComfyUI to unload models and clear its soft cache around the llama-swap request.

Useful when ComfyUI and llama-swap share the same GPU.

### `unload_on_run`

When enabled, the node asks llama-swap to unload the selected model after the response is complete.

Disable it if you want the model to stay loaded for faster repeated requests.

## Outputs

The node returns:

```text
response   STRING
used_model STRING
```

`response` can be connected directly to other ComfyUI text/prompt nodes.

## Installation

Clone the repository into:

```text
ComfyUI/custom_nodes/
```

Example:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Tyosx/ComfyUI-TYOS-LlamaSwap.git
```

Install the Python requirement if needed:

```bash
pip install -r ComfyUI-TYOS-LlamaSwap/requirements.txt
```

Then:

1. Restart ComfyUI completely.
2. Hard refresh the browser with `Ctrl+F5`.
3. Search for **TYOS Llama-Swap Vision Node**.

## Updating

If you install a version that includes the updater, you can run:

```text
update.bat
```

The updater is designed to preserve your local saved system prompts.

For safety, close ComfyUI before updating, then restart it and press `Ctrl+F5`.

## Requirements

- ComfyUI
- Python `requests`
- llama-swap
- An OpenAI-compatible model configuration
- A vision-capable model for images/video
- An audio-capable model for audio understanding

## Compatibility notes

This project does **not** add its own reasoning/thinking mode.

The node sends standard OpenAI-compatible chat-completions style requests to llama-swap.

Backend support for specific multimodal message formats can vary by llama.cpp / llama-swap version and model family.

## Repository structure

```text
ComfyUI-TYOS-LlamaSwap/
├── __init__.py
├── README.md
├── CHANGELOG.md
├── LICENSE
├── requirements.txt
├── system_prompts.example.json
├── updater.py
├── update.bat
└── web/
    └── js/
        └── tyos_llamaswap_vision_node.js
```

## License

MIT

## Project

**ComfyUI-TYOS-LlamaSwap**

Built for local multimodal workflows where ComfyUI handles the pipeline and llama-swap handles the language / vision model.
