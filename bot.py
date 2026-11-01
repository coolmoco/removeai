from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler
)
from PIL import Image, ImageEnhance, ImageFilter
import io
import os
import random
import subprocess
import tempfile
import uuid
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")


# ==================== HEALTH SERVER ====================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive")

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health server running on port {port}")
    server.serve_forever()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Welcome!\n\n"
        "Just send me any image or video and I will clean it for you.\n"
        "This helps remove metadata and makes the file look unique so platforms treat it as original content.\n\n"
        "What I do:\n"
        "• Remove all metadata\n"
        "• Visible visual + color changes\n"
        "• Re-encode for uniqueness\n\n"
        "For any help contact @pvnuo"
    )
    await update.message.reply_text(text)


def enhance_image(img: Image.Image) -> Image.Image:
    if img.mode != "RGB":
        img = img.convert("RGB")

    original_size = img.size

    angle = random.uniform(0.08, 0.18) * random.choice([-1, 1])
    img = img.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False)
    img = img.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=False)

    w, h = img.size
    factor = random.uniform(0.985, 0.995)
    img = img.resize((int(w * factor), int(h * factor)), Image.Resampling.LANCZOS)
    img = img.resize(original_size, Image.Resampling.LANCZOS)

    noise = Image.effect_noise(img.size, random.uniform(4.0, 7.0))
    noise = noise.convert("L")
    noise = ImageEnhance.Brightness(noise).enhance(random.uniform(0.08, 0.15))
    img = Image.blend(img, noise.convert("RGB"), random.uniform(0.06, 0.11))

    r, g, b = img.split()
    r = ImageEnhance.Brightness(r).enhance(random.uniform(0.97, 1.04))
    g = ImageEnhance.Brightness(g).enhance(random.uniform(0.96, 1.03))
    b = ImageEnhance.Brightness(b).enhance(random.uniform(0.97, 1.04))
    img = Image.merge("RGB", (r, g, b))

    img = ImageEnhance.Color(img).enhance(random.uniform(1.10, 1.22))

    r, g, b = img.split()
    if random.random() > 0.5:
        r = ImageEnhance.Brightness(r).enhance(random.uniform(1.03, 1.07))
        b = ImageEnhance.Brightness(b).enhance(random.uniform(0.94, 0.98))
    else:
        r = ImageEnhance.Brightness(r).enhance(random.uniform(0.94, 0.98))
        b = ImageEnhance.Brightness(b).enhance(random.uniform(1.03, 1.07))
    img = Image.merge("RGB", (r, g, b))

    img = img.filter(ImageFilter.UnsharpMask(radius=1.4, percent=130, threshold=1))
    img = ImageEnhance.Contrast(img).enhance(random.uniform(1.10, 1.20))
    img = ImageEnhance.Sharpness(img).enhance(random.uniform(1.3, 1.7))

    return img


def enhance_video(input_path: str, output_path: str) -> bool:
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                input_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15
        )
        duration = float(probe.stdout.strip())
    except Exception:
        duration = 0

    hue_shift = random.uniform(-8, 8)
    sat = random.uniform(1.12, 1.25)
    contrast = random.uniform(1.10, 1.20)
    brightness = random.uniform(0.02, 0.06)

    if duration > 2.2:
        ss = 0.5
        t = duration - 1.0
        vf = (
            f"trim=start={ss}:duration={t},"
            "setpts=PTS-STARTPTS,"
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
            f"eq=contrast={contrast}:brightness={brightness}:saturation={sat},"
            f"hue=h={hue_shift},"
            "unsharp=5:5:1.0:5:5:0.5,"
            "format=yuv420p"
        )
    else:
        vf = (
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
            f"eq=contrast={contrast}:brightness={brightness}:saturation={sat},"
            f"hue=h={hue_shift},"
            "unsharp=5:5:1.0:5:5:0.5,"
            "format=yuv420p"
        )

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-map_metadata", "-1",
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "21",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-threads", "2",
        output_path
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180
        )
        return (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 4000
        )
    except Exception:
        return False


async def process_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = None
    temp_files = []

    try:
        status = await update.message.reply_text("⌛")

        if update.message.photo or (
            update.message.document
            and update.message.document.mime_type
            and update.message.document.mime_type.startswith("image/")
        ):
            if update.message.photo:
                file = await update.message.photo[-1].get_file()
            else:
                file = await update.message.document.get_file()

            bio = io.BytesIO()
            await file.download_to_memory(bio)
            bio.seek(0)

            img = Image.open(bio)
            clean = enhance_image(img)

            out = io.BytesIO()
            clean.save(out, format="JPEG", quality=91, optimize=True)
            out.seek(0)

            await update.message.reply_photo(photo=out, caption="Ready")

        elif update.message.video or (
            update.message.document
            and update.message.document.mime_type
            and update.message.document.mime_type.startswith("video/")
        ):
            if update.message.video:
                tg_file = update.message.video
            else:
                tg_file = update.message.document

            if tg_file.file_size and tg_file.file_size > 19 * 1024 * 1024:
                await status.edit_text("File too big (max 19 MB)")
                return

            file = await tg_file.get_file()
            uid = uuid.uuid4().hex[:8]

            input_path = os.path.join(tempfile.gettempdir(), f"in_{uid}.mp4")
            output_path = os.path.join(tempfile.gettempdir(), f"out_{uid}.mp4")
            temp_files.extend([input_path, output_path])

            await file.download_to_drive(input_path)

            success = enhance_video(input_path, output_path)
            if not success:
                await status.edit_text("Video processing failed")
                return

            with open(output_path, "rb") as f:
                await update.message.reply_video(
                    video=f,
                    caption="Ready",
                    supports_streaming=True
                )

        else:
            await status.edit_text("Send image or video only")
            return

        try:
            await status.delete()
        except Exception:
            pass

    except Exception as e:
        error_msg = str(e)[:400]
        if status:
            try:
                await status.edit_text(f"Failed: {error_msg}")
            except Exception:
                await update.message.reply_text(f"Failed: {error_msg}")
        else:
            await update.message.reply_text(f"Failed: {error_msg}")

    finally:
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Just send me any image or video and I will modify it for you.\n\n"
        "What I do:\n"
        "• Remove metadata\n"
        "• Make clear visual + color changes so it looks unique\n"
        "• Help reduce AI / unoriginal content detections\n\n"
        "For any help contact @pvnuo"
    )
    await update.message.reply_text(text)


def main():
    # Health server start karo
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    app = (
        Application.builder()
        .token(TOKEN)
        .read_timeout(60)
        .write_timeout(60)
        .connect_timeout(60)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.IMAGE | filters.VIDEO | filters.Document.VIDEO,
        process_media
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot started...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
