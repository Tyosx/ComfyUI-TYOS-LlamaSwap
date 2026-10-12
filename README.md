# ComfyUI-TYOS-MediaPrompt

**Multimodal prompt generation in ComfyUI through [llama-swap](https://github.com/mostlygeek/llama-swap).**

Connect a local or remote OpenAI-compatible language model to ComfyUI workflows. Analyze images, video, audio, or text and route model responses to other nodes.

> **Release:** v0.9 (multimedia inputs). Supported features depend on your selected model and backend.

## Features

- **Model discovery:** Refresh Models queries the connected llama-swap server.
- **Multimodal inputs:** up to 9 images, 3 video inputs, and 3 audio inputs, with a combined limit of **12 connected media sockets**.
- **Prompt controls:** editable system and user prompts, named system-prompt presets, generation temperature, and maximum tokens.
- **Token presets:** Low (512), Mid (2,048), High (8,192), Max (12,288), or Custom (up to 65,536).
- **Duration guidance:** optional seconds field with a connectable INT/FLOAT number input.
- **Memory management:** optional ComfyUI model unload and llama-swap model unload.
- **Outputs:** model response and selected model ID, both as strings.

## Installation

Clone into ComfyUI's `custom_nodes` directory:

```bash
git clone https://github.com/Tyosx/ComfyUI-TYOS-MediaPrompt.git
```

Install dependencies with **the same Python environment ComfyUI uses**:

```bash
pip install -r ComfyUI-TYOS-MediaPrompt/requirements.txt
```

Restart ComfyUI and refresh its browser page.

**Node display name:** TYOS MediaPrompt  
**Node category:** TYOS/AI

Existing workflows remain compatible with the previous internal node identifier, `TyosLlamaSwapVisionNode`.

## Setup and use

1. Start llama-swap with an OpenAI-compatible API.
2. Enter its endpoint in `api_base`. The default is `http://127.0.0.1:4726/v1`.
3. Click **Refresh Models** and select a model.
4. Connect any supported media and enter your instructions.
5. Choose a token budget and optionally enable duration guidance.
6. Queue the workflow and connect the `response` output wherever text is needed.

## Media limits

| Media | Inputs | Maximum |
|---|---|---:|
| Images | `image`, `image_2` … `image_9` | 9 |
| Video | `video_1` … `video_3` | 3 |
| Audio | `audio_1` … `audio_3` | 3 |
| **Combined** | Across all connected media inputs | **12** |

Image tensors are encoded as PNG. Audio is converted to PCM WAV. Video stream objects are sent in the multimodal request format implemented by the plugin. **These formats require compatible server and model support.** Not every vision model understands audio or accepts a raw video request.

The current implementation takes the first frame/image from each connected IMAGE batch.

## Saved system prompts

Select a named preset to populate the editable `system_prompt` field. Editing the field does **not** change the saved preset. Use **Save System Prompt** to enter a name and explicitly save it; overwriting a preset requires confirmation.

Saved presets are stored in `system_prompts.json`, created locally from the distributed `system_prompts.example.json`. The local file is ignored by Git. Do not commit custom prompt collections, API credentials, or other local configuration to public repositories.

## Updates

On Windows, close ComfyUI and run `update.bat` to update from the project's GitHub repository. The updater preserves `system_prompts.json`. Restart ComfyUI afterwards.

A Git-based installation can also be updated with `git pull`. Back up saved presets before manually replacing a plugin folder.

## Compatibility and limitations

- Requires ComfyUI, a reachable llama-swap server, and a suitable model configured in that server.
- Image/video/audio understanding depends on the actual model, multimodal projectors, and serving backend.
- The maximum-token control sets a request limit, not a guarantee of output length.
- The duration field adds guidance to the model; it does not change the duration of a rendered video.
- Large video/audio payloads can be memory-intensive. Test your model/server with individual media inputs before using larger batches.

## License

MIT. See [LICENSE](LICENSE).
