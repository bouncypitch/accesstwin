"""Photorealize twin renders while keeping their geometry: SD 1.5 (Realistic Vision) img2img with ControlNet depth
(exact depth from the twin) + ControlNet canny (edges of the render). Runs on Apple Silicon (MPS).

    tools/photoreal/.venv/bin/python tools/photoreal/photoreal.py out/04_tour/explainer/hero
"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from diffusers import AutoencoderKL, ControlNetModel, StableDiffusionControlNetImg2ImgPipeline, UniPCMultistepScheduler
from PIL import Image

PROMPT = ("RAW photo, interior of a modern university robotics research laboratory, cream painted walls, white ceiling "
          "with recessed downlights, sealed light grey concrete floor with yellow and black safety floor tape, blue ESD "
          "workbenches with oscilloscopes and monitors, industrial robot arms, steel shelving, colour-coded signs, bright "
          "even daylight, wide angle architectural interior photography, sharp focus, high detail")
NEGATIVE = ("cartoon, 3d render, cgi, video game, illustration, painting, plastic, toy, blurry, lowres, noise, people, "
            "person, crowd, watermark, text artifacts, distorted, warped")

d = Path(sys.argv[1])
dev = "mps" if torch.backends.mps.is_available() else "cpu"
dtype = torch.float16
# Depth only: two ControlNets together produced NaN latents in fp16 on MPS; the img2img init carries the edges.
cn = ControlNetModel.from_pretrained("lllyasviel/control_v11f1p_sd15_depth", torch_dtype=dtype, variant="fp16")
vae = AutoencoderKL.from_pretrained("stabilityai/sd-vae-ft-mse", torch_dtype=dtype)
vae32 = AutoencoderKL.from_pretrained("stabilityai/sd-vae-ft-mse", torch_dtype=torch.float32).to(dev)  # fp16 decode -> NaN on MPS
pipe = StableDiffusionControlNetImg2ImgPipeline.from_pretrained(
    "SG161222/Realistic_Vision_V5.1_noVAE", controlnet=cn, vae=vae, torch_dtype=dtype, safety_checker=None,
    requires_safety_checker=False)
# default PNDM scheduler: DPM++ Karras and UniPC produced NaNs in fp16 on MPS
pipe = pipe.to(dev)
# attention slicing produced NaNs in fp16 on MPS

only = sys.argv[2] if len(sys.argv) > 2 else "stop_*"
for color in sorted(d.glob(f"{only}_color.png")):
    out = color.with_name(color.name.replace("_color", "_photo")).with_suffix(".jpg")
    if out.exists():
        continue
    t = time.time()
    img = Image.open(color).convert("RGB").resize((640, 384))
    depth = Image.open(color.with_name(color.name.replace("_color", "_depth"))).convert("RGB").resize((640, 384))
    edges = cv2.Canny(np.array(img), 80, 180)
    canny = Image.fromarray(np.stack([edges] * 3, -1))
    g = torch.Generator("cpu").manual_seed(7)
    lat = pipe(PROMPT, negative_prompt=NEGATIVE, image=img, control_image=depth, strength=0.62,
               num_inference_steps=24, guidance_scale=6.0, controlnet_conditioning_scale=0.9, generator=g,
               output_type="latent").images
    if torch.isnan(lat).any():
        print(f"{color.name}: NaN latents, skipped", flush=True)
        continue
    with torch.no_grad():
        x = vae32.decode(lat.float() / vae32.config.scaling_factor).sample
    x = ((x[0].clamp(-1, 1) + 1) * 127.5).permute(1, 2, 0).round().byte().cpu().numpy()
    res = Image.fromarray(x).resize((1280, 720), Image.LANCZOS)
    res.save(out, quality=94)
    print(f"{out.name}  {time.time() - t:.0f} s", flush=True)
