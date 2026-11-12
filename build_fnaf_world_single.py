#!/usr/bin/env python3
"""Pack FNaF World Refreshed into one offline HTML file."""
from __future__ import annotations
import argparse
import base64
import html
import json
import re
import sys
from pathlib import Path

GAME = "fnaf-world-refreshed"

BOOTSTRAP = r"""
(function () {
  "use strict";
  const urls = new Map();
  function fileKey(value) {
    try {
      const path = new URL(value, document.baseURI).pathname;
      return decodeURIComponent(path.slice(path.lastIndexOf("/") + 1));
    } catch (_) {
      const text = String(value || "").split(/[?#]/)[0];
      return text.slice(text.lastIndexOf("/") + 1);
    }
  }
  function embeddedURL(value) {
    const key = fileKey(value);
    if (urls.has(key)) return urls.get(key);
    const id = window.__FW_INDEX && window.__FW_INDEX[key];
    if (!id) return value;
    const node = document.getElementById(id);
    if (!node) return value;
    const encoded = node.textContent.trim();
    const mime = node.getAttribute("data-mime") || "application/octet-stream";
    node.remove();
    delete window.__FW_INDEX[key];
    const binary = atob(encoded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blobURL = URL.createObjectURL(new Blob([bytes], {type:mime}));
    urls.set(key, blobURL);
    return blobURL;
  }
  function patch(proto) {
    if (!proto) return;
    const d = Object.getOwnPropertyDescriptor(proto, "src");
    if (!d || !d.set || !d.get || !d.configurable) return;
    Object.defineProperty(proto, "src", {
      configurable:true, enumerable:d.enumerable,
      get:function(){return d.get.call(this);},
      set:function(value){d.set.call(this, embeddedURL(value));}
    });
  }
  patch(window.HTMLImageElement && HTMLImageElement.prototype);
  patch(window.HTMLMediaElement && HTMLMediaElement.prototype);
  const open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    const args = Array.prototype.slice.call(arguments, 2);
    return open.apply(this, [method, embeddedURL(url)].concat(args));
  };
  const canPlay = HTMLMediaElement.prototype.canPlayType;
  HTMLMediaElement.prototype.canPlayType = function(type) {
    if (/^audio\/ogg(?:\s*;|$)/i.test(String(type))) return "";
    return canPlay.call(this, type);
  };
})();
"""

HEAD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="mobile-web-app-capable" content="yes">
<title>FNaF World Refreshed — Offline</title>
<style>
html,body{margin:0;width:100%;height:100%;background:#000;overflow:hidden}
body{display:flex;align-items:center;justify-content:center}
#game{width:min(100vw,166.6667vh);height:auto;max-height:100vh;aspect-ratio:5/3}
#MMFCanvas{display:block;width:100%;height:100%;object-fit:contain}
</style></head><body>
<div id="game"><canvas id="MMFCanvas" width="800" height="480">Canvas unsupported.</canvas></div>
<script>
"""

TAIL = r"""
window.addEventListener("load", function () {
  try { new Runtime("MMFCanvas", "resources/fnaf-world-refreshed.cch"); }
  catch (e) {
    document.body.innerHTML = "<pre style='color:white;padding:20px'>" + String(e) + "</pre>";
    console.error(e);
  }
}, false);
</script></body></html>
"""

def resources(root: Path) -> list[Path]:
    folder = root / "resources"
    required = [folder / f"{GAME}.cch"] + [folder / f"{GAME}.cc{i}" for i in range(1, 15)]
    missing = [p.name for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing Clickteam data chunks: " + ", ".join(missing))
    files = required + sorted(folder.glob("*.png")) + sorted(folder.glob("*.mp3"))
    names = [p.name for p in files]
    if len(names) != len(set(names)):
        raise RuntimeError("Duplicate resource filenames found.")
    return files

def pack_asset(path: Path, quality: int) -> tuple[bytes, str]:
    ext = path.suffix.lower()
    if ext == ".png":
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Install Pillow with: python3 -m pip install Pillow") from exc
        import io
        with Image.open(path) as im:
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            buffer = io.BytesIO()
            im.save(buffer, "WEBP", quality=quality, method=6, exact=True)
            return buffer.getvalue(), "image/webp"
    mime = {".mp3":"audio/mpeg", ".cch":"application/octet-stream"}.get(ext, "application/octet-stream")
    return path.read_bytes(), mime

def main() -> int:
    parser = argparse.ArgumentParser(description="Build an offline, single-file FNaF World HTML.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("FNAF-World-Refreshed-Single.html"))
    parser.add_argument("--quality", type=int, default=88, choices=range(60, 101))
    args = parser.parse_args()
    root = args.repo.resolve()
    runtime = root / "src" / "Runtime.js"
    if not runtime.is_file():
        print("Could not find src/Runtime.js in --repo.", file=sys.stderr)
        return 2
    files = resources(root)
    runtime_js = re.sub(r"</script", r"<\\/script", runtime.read_text(encoding="utf-8"), flags=re.I)
    ids = {p.name: f"fw-{i:04d}" for i, p in enumerate(files, 1)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    total_raw = total_b64 = 0
    with args.output.open("w", encoding="utf-8", newline="\n") as out:
        out.write(HEAD + BOOTSTRAP + "\n</script>\n<script>\n" + runtime_js + "\n</script>\n")
        out.write("<script>window.__FW_INDEX=" + json.dumps(ids, separators=(",", ":")) + ";</script>\n")
        for i, path in enumerate(files, 1):
            raw, mime = pack_asset(path, args.quality)
            encoded = base64.b64encode(raw).decode("ascii")
            out.write('<script type="application/octet-stream" id="fw-' + f'{i:04d}' +
                      '" data-mime="' + html.escape(mime, quote=True) + '">' +
                      encoded + '</script>\n')
            total_raw += len(raw)
            total_b64 += len(encoded)
            if i % 50 == 0 or i == len(files):
                print(f"Packed {i}/{len(files)} assets; payload {total_b64/1048576:.1f} MiB")
        out.write(TAIL)
    size = args.output.stat().st_size
    print(f"Created {args.output.resolve()} ({size/1048576:.1f} MiB)")
    print("All runtime and game resources are embedded; no external game-asset requests are used.")
    print("A single file does not remove the RAM required for decoded game textures.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
