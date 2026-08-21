"""
Visual Diff Engine per NK TAS 3.0 / CRV 3.0.
Confronta due immagini (baseline vs patched) e calcola il delta dei pixel,
generando una maschera overlay visiva con evidenziazione in rosso dei pixel modificati.
"""

import sys
import json
import os

try:
    from PIL import Image, ImageChops, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def compute_visual_diff(baseline_path: str, patched_path: str, output_diff_path: str) -> dict:
    """
    Calcola la differenza visiva tra due immagini.
    Restituisce un dizionario con diff_percentage e status.
    """
    if not os.path.exists(baseline_path) or not os.path.exists(patched_path):
        return {
            "status": "ERROR",
            "message": "File di input baseline o patched non trovato su disco.",
            "diff_percentage": 0.0
        }
    
    if not PIL_AVAILABLE:
        return {
            "status": "FALLBACK_DOM_ONLY",
            "message": "Pillow (PIL) non disponibile nel venv. Utilizzare fallback DOM Reader.",
            "diff_percentage": 0.0
        }

    try:
        img1 = Image.open(baseline_path).convert("RGBA")
        img2 = Image.open(patched_path).convert("RGBA")

        # Uniforma le dimensioni prendendo il massimo tra le due
        width = max(img1.width, img2.width)
        height = max(img1.height, img2.height)

        if img1.size != (width, height):
            base1 = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            base1.paste(img1, (0, 0))
            img1 = base1

        if img2.size != (width, height):
            base2 = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            base2.paste(img2, (0, 0))
            img2 = base2

        # Diff pixel-by-pixel
        diff = ImageChops.difference(img1, img2)
        bbox = diff.getbbox()
        
        # Conteggio pixel differenti (soglia di tolleranza su canale alpha/RGB)
        pixels = list(diff.getdata())
        different_pixels = sum(1 for p in pixels if any(channel > 15 for channel in p[:3]))
        total_pixels = width * height
        diff_percentage = round((different_pixels / total_pixels) * 100, 2)

        # Genera overlay visivo evidenziando le differenze in rosso
        overlay = img2.copy()
        highlight = Image.new("RGBA", (width, height), (255, 0, 0, 160)) # Rosso semi-trasparente
        mask = diff.convert("L").point(lambda p: 255 if p > 15 else 0)
        overlay.paste(highlight, (0, 0), mask)

        os.makedirs(os.path.dirname(output_diff_path), exist_ok=True)
        overlay.save(output_diff_path, "PNG")

        return {
            "status": "SUCCESS",
            "diff_percentage": diff_percentage,
            "different_pixels": different_pixels,
            "total_pixels": total_pixels,
            "bounding_box": list(bbox) if bbox else None,
            "output_diff_path": output_diff_path
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Eccezione durante il calcolo del visual diff: {str(e)}",
            "diff_percentage": 0.0
        }


if __name__ == "__main__":
    if len(sys.argv) >= 4:
        b_path = sys.argv[1]
        p_path = sys.argv[2]
        out_path = sys.argv[3]
        result = compute_visual_diff(b_path, p_path, out_path)
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"status": "INFO", "usage": "python visual_diff_engine.py baseline.png patched.png diff.png"}))
