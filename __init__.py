WEB_DIRECTORY = "./web/js"
__version__ = "0.9.1"

import base64
import io
import json
import wave
from pathlib import Path
from urllib.parse import quote

import numpy as np
import requests
from PIL import Image

import comfy.model_management as mm

try:
    from server import PromptServer
    from aiohttp import web
except Exception:
    PromptServer = None
    web = None

DEFAULT_API_BASE = "http://127.0.0.1:4726/v1"
DEFAULT_SYSTEM_PROMPT = (
    "You are a precise vision-language assistant. "
    "If images, videos, or audio are provided, analyze the actual media carefully before answering. "
    "Do not hallucinate hidden details. If something is unclear, say so briefly. "
    "When the user asks for prompts, produce strong clean prompts directly. "
    "Return only the requested answer without extra filler unless the user asks for explanation."
)

NODE_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPTS_FILE = NODE_DIR / "system_prompts.json"
SYSTEM_PROMPTS_EXAMPLE_FILE = NODE_DIR / "system_prompts.example.json"


class _AnyNumberType(str):
    def __ne__(self, other):
        return False


NUMBER_INPUT = _AnyNumberType("NUMBER")


def _ensure_system_prompts_file():
    if SYSTEM_PROMPTS_FILE.exists():
        return
    if SYSTEM_PROMPTS_EXAMPLE_FILE.exists():
        try:
            data = json.loads(SYSTEM_PROMPTS_EXAMPLE_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not data:
                data = {"Default": DEFAULT_SYSTEM_PROMPT}
        except Exception:
            data = {"Default": DEFAULT_SYSTEM_PROMPT}
    else:
        data = {"Default": DEFAULT_SYSTEM_PROMPT}
    SYSTEM_PROMPTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_system_prompts():
    _ensure_system_prompts_file()
    try:
        data = json.loads(SYSTEM_PROMPTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("system_prompts.json must contain a JSON object")
        cleaned = {}
        for name, prompt in data.items():
            name = str(name).strip()
            prompt = str(prompt)
            if name:
                cleaned[name] = prompt
        if not cleaned:
            cleaned = {"Default": DEFAULT_SYSTEM_PROMPT}
        return cleaned
    except Exception:
        return {"Default": DEFAULT_SYSTEM_PROMPT}


def _save_system_prompt(name: str, prompt: str):
    name = (name or "").strip()
    if not name:
        raise ValueError("Preset name cannot be empty")
    prompts = _load_system_prompts()
    prompts[name] = str(prompt or "")
    SYSTEM_PROMPTS_FILE.write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return prompts


def _normalize_api_base(url: str) -> str:
    url = (url or DEFAULT_API_BASE).strip().rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def _server_root(api_base: str) -> str:
    api_base = _normalize_api_base(api_base)
    return api_base[:-3].rstrip("/")


def _to_png_data_url(image):
    if image is None:
        return None
    tensor = image[0].detach().cpu()
    arr = np.clip(tensor.numpy() * 255.0, 0, 255).astype(np.uint8)
    if arr.ndim == 3 and arr.shape[-1] == 1:
        pil = Image.fromarray(arr[..., 0], mode="L")
    else:
        pil = Image.fromarray(arr)
    buf = io.BytesIO()
    pil.save(buf, format="PNG", optimize=False, compress_level=0)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _to_wav_base64(audio):
    """Encode a ComfyUI AUDIO value as 16-bit PCM WAV base64."""
    if audio is None:
        return None

    if not isinstance(audio, dict):
        raise RuntimeError("Unsupported AUDIO input. Expected ComfyUI AUDIO data.")

    waveform = audio.get("waveform")
    sample_rate = int(audio.get("sample_rate") or 0)
    if waveform is None or sample_rate <= 0:
        raise RuntimeError("Invalid AUDIO input: missing waveform or sample_rate.")

    tensor = waveform.detach().float().cpu()
    if tensor.ndim == 1:
        tensor = tensor.reshape(1, 1, -1)
    elif tensor.ndim == 2:
        tensor = tensor.unsqueeze(0)
    elif tensor.ndim > 3:
        tensor = tensor.reshape(-1, tensor.shape[-2], tensor.shape[-1])

    if tensor.ndim != 3 or tensor.shape[-1] <= 0:
        raise RuntimeError("Invalid AUDIO tensor shape.")

    sample = tensor[0]
    channels = int(sample.shape[0])
    if channels <= 0:
        raise RuntimeError("AUDIO input has no channels.")

    pcm = (
        sample.clamp(-1.0, 1.0)
        .transpose(0, 1)
        .contiguous()
        .numpy()
    )
    pcm16 = np.round(pcm * 32767.0).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())

    return base64.b64encode(buf.getvalue()).decode("ascii")


def _video_to_base64(video):
    """Read a ComfyUI VIDEO value into base64 without reducing its frames."""
    if video is None:
        return None

    getter = getattr(video, "get_stream_source", None)
    if callable(getter):
        source = getter()
        if isinstance(source, io.BytesIO):
            source.seek(0)
            data = source.read()
        elif isinstance(source, (str, Path)):
            data = Path(source).read_bytes()
        else:
            read = getattr(source, "read", None)
            if not callable(read):
                raise RuntimeError("Unsupported VIDEO stream source.")
            try:
                source.seek(0)
            except Exception:
                pass
            data = read()
        if not data:
            raise RuntimeError("VIDEO input is empty.")
        return base64.b64encode(data).decode("ascii")

    if isinstance(video, (str, Path)):
        data = Path(video).read_bytes()
        return base64.b64encode(data).decode("ascii")

    if isinstance(video, dict):
        for key in ("path", "video_path", "filepath", "filename"):
            value = video.get(key)
            if value and Path(str(value)).is_file():
                data = Path(str(value)).read_bytes()
                return base64.b64encode(data).decode("ascii")

    raise RuntimeError(
        "Unsupported VIDEO input. Connect a native ComfyUI VIDEO output "
        "or a compatible video object/path."
    )


def _append_labeled_media(content, label, media_part):
    content.append({"type": "text", "text": f"[{label}]"})
    content.append(media_part)


def _free_comfy_vram():
    try:
        if hasattr(mm, "unload_all_models"):
            mm.unload_all_models()
        if hasattr(mm, "soft_empty_cache"):
            mm.soft_empty_cache()
    except Exception:
        pass


def _fetch_models(api_base: str):
    url = f"{_normalize_api_base(api_base)}/models"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    payload = r.json()
    models = []
    for item in payload.get("data", []):
        mid = item.get("id")
        if mid:
            models.append(str(mid))
    return models


def _unload_model(api_base: str, model_id: str):
    try:
        url = f"{_server_root(api_base)}/api/models/unload/{quote(model_id, safe='')}"
        requests.post(url, timeout=10)
    except Exception:
        pass


class TyosLlamaSwapVisionNode:
    @classmethod
    def INPUT_TYPES(cls):
        prompts = _load_system_prompts()
        prompt_names = list(prompts.keys()) or ["Default"]
        default_name = "Default" if "Default" in prompt_names else prompt_names[0]
        default_prompt = prompts.get(default_name, DEFAULT_SYSTEM_PROMPT)
        return {
            "required": {
                "api_base": ("STRING", {"default": DEFAULT_API_BASE, "multiline": False}),
                "model_id": (["(click Refresh Models)"], {"default": "(click Refresh Models)"}),
                "system_prompt_preset": (prompt_names, {"default": default_name}),
                "system_prompt": ("STRING", {"default": default_prompt, "multiline": True}),
                "user_prompt": ("STRING", {"default": "", "multiline": True}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.05}),
                "token_mode": (
                    ["Low · 512", "Mid · 2048", "High · 8192", "Max · 12288", "Custom"],
                    {"default": "Mid · 2048"},
                ),
                "custom_max_tokens": ("INT", {"default": 4096, "min": 1, "max": 65536, "step": 1}),
                "use_duration": ("BOOLEAN", {"default": True}),
                "duration_seconds": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 600.0, "step": 0.1}),
                "free_comfyui_vram": ("BOOLEAN", {"default": True}),
                "unload_on_run": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "image": ("IMAGE",),
                "image_2": ("IMAGE",),
                "image_3": ("IMAGE",),
                "image_4": ("IMAGE",),
                "image_5": ("IMAGE",),
                "image_6": ("IMAGE",),
                "image_7": ("IMAGE",),
                "image_8": ("IMAGE",),
                "image_9": ("IMAGE",),

                "video_1": ("VIDEO",),
                "video_2": ("VIDEO",),
                "video_3": ("VIDEO",),

                "audio_1": ("AUDIO",),
                "audio_2": ("AUDIO",),
                "audio_3": ("AUDIO",),

                "duration_in": (NUMBER_INPUT, {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("response", "used_model")
    FUNCTION = "run"
    CATEGORY = "TYOS/AI"

    def run(
        self,
        api_base,
        model_id,
        system_prompt_preset,
        system_prompt,
        user_prompt,
        temperature,
        token_mode,
        custom_max_tokens,
        use_duration,
        duration_seconds,
        free_comfyui_vram,
        unload_on_run,
        image=None,
        image_2=None,
        image_3=None,
        image_4=None,
        image_5=None,
        image_6=None,
        image_7=None,
        image_8=None,
        image_9=None,
        video_1=None,
        video_2=None,
        video_3=None,
        audio_1=None,
        audio_2=None,
        audio_3=None,
        duration_in=None,
    ):
        api_base = _normalize_api_base(api_base)

        token_budgets = {
            "Low · 512": 512,
            "Mid · 2048": 2048,
            "High · 8192": 8192,
            "Max · 12288": 12288,
        }
        effective_max_tokens = int(token_budgets.get(token_mode, int(custom_max_tokens)))
        effective_max_tokens = max(1, min(effective_max_tokens, 65536))

        if use_duration:
            duration = float(duration_in) if duration_in is not None else float(duration_seconds)
            duration = max(0.0, duration)
        else:
            duration = 0.0

        if free_comfyui_vram:
            _free_comfy_vram()

        available_models = _fetch_models(api_base)
        selected_model = str(model_id).strip()
        if selected_model in ("", "(click Refresh Models)"):
            if len(available_models) == 1:
                selected_model = available_models[0]
            else:
                raise RuntimeError(
                    "No model selected. Click Refresh Models and choose a model. "
                    f"Available: {', '.join(available_models)}"
                )

        if selected_model not in available_models:
            if len(available_models) == 1:
                selected_model = available_models[0]
            else:
                raise RuntimeError(
                    f"Selected model '{selected_model}' is not in llama-swap. "
                    f"Available: {', '.join(available_models)}"
                )

        images = [image, image_2, image_3, image_4, image_5, image_6, image_7, image_8, image_9]
        videos = [video_1, video_2, video_3]
        audios = [audio_1, audio_2, audio_3]

        image_count = sum(item is not None for item in images)
        video_count = sum(item is not None for item in videos)
        audio_count = sum(item is not None for item in audios)
        media_count = image_count + video_count + audio_count

        if media_count > 12:
            raise RuntimeError(
                f"Media limit exceeded: {media_count}/12 connected. "
                "Maximums are 9 images, 3 videos, 3 audio files, with 12 media items total."
            )

        user_content = []

        image_index = 0
        for item in images:
            if item is None:
                continue
            image_index += 1
            data_url = _to_png_data_url(item)
            if data_url:
                _append_labeled_media(
                    user_content,
                    f"Image {image_index}",
                    {"type": "image_url", "image_url": {"url": data_url}},
                )

        video_index = 0
        for item in videos:
            if item is None:
                continue
            video_index += 1
            video_b64 = _video_to_base64(item)
            _append_labeled_media(
                user_content,
                f"Video {video_index}",
                {"type": "input_video", "input_video": {"data": video_b64}},
            )

        audio_index = 0
        for item in audios:
            if item is None:
                continue
            audio_index += 1
            audio_b64 = _to_wav_base64(item)
            _append_labeled_media(
                user_content,
                f"Audio {audio_index}",
                {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
            )

        text = (user_prompt or "").strip()
        if not text:
            text = "Analyze the provided media carefully and answer based on what you actually see or hear."

        if duration > 0:
            text = (
                f"Target video duration: {duration:g} seconds. "
                "If the request is for a video prompt, keep the actions, dialogue, pacing, and camera movement realistically achievable within that duration.\n\n"
                + text
            )

        user_content.append({"type": "text", "text": text})

        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": (system_prompt or DEFAULT_SYSTEM_PROMPT).strip() or DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": float(temperature),
            "max_tokens": effective_max_tokens,
            "stream": False,
        }

        response_text = ""
        try:
            r = requests.post(f"{api_base}/chat/completions", json=payload, timeout=600)
            if not r.ok:
                raise RuntimeError(f"llama-swap request failed ({r.status_code}): {r.text}")
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        parts.append(str(item.get("text", "")))
                    else:
                        parts.append(str(item))
                response_text = "".join(parts).strip()
            else:
                response_text = str(content).strip()
        finally:
            if unload_on_run and selected_model:
                _unload_model(api_base, selected_model)
            if free_comfyui_vram:
                _free_comfy_vram()

        status = f"Done · {selected_model}"
        status += f" · media {media_count}/12 ({image_count}I {video_count}V {audio_count}A)"
        status += f" · prompt {system_prompt_preset}"
        status += f" · tokens {effective_max_tokens}"
        if duration > 0:
            status += f" · {duration:g}s"

        return {
            "ui": {
                "status": [status],
                "preview": [response_text[:3000] if response_text else ""],
            },
            "result": (response_text, selected_model),
        }


NODE_CLASS_MAPPINGS = {
    "TyosLlamaSwapVisionNode": TyosLlamaSwapVisionNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TyosLlamaSwapVisionNode": "TYOS MediaPrompt",
}


if PromptServer is not None and web is not None:
    @PromptServer.instance.routes.get("/tyos/llamaswap/vision/models")
    async def tyos_llamaswap_vision_models(request):
        api_base = request.query.get("api_base", DEFAULT_API_BASE)
        try:
            models = _fetch_models(api_base)
            return web.json_response({"ok": True, "models": models})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e), "models": []}, status=500)


    @PromptServer.instance.routes.get("/tyos/llamaswap/vision/prompts")
    async def tyos_llamaswap_vision_prompts(request):
        try:
            prompts = _load_system_prompts()
            return web.json_response({
                "ok": True,
                "names": list(prompts.keys()),
                "prompts": prompts,
            })
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)


    @PromptServer.instance.routes.post("/tyos/llamaswap/vision/prompts/save")
    async def tyos_llamaswap_vision_prompts_save(request):
        try:
            payload = await request.json()
            name = str(payload.get("name", "")).strip()
            prompt = str(payload.get("prompt", ""))
            prompts = _save_system_prompt(name, prompt)
            return web.json_response({
                "ok": True,
                "saved": name,
                "names": list(prompts.keys()),
                "prompts": prompts,
            })
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)


__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
