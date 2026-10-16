from telegram import Update, MessageEntity
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler
)
from PIL import Image, ImageFilter, ImageEnhance
import io
import os
import random
import subprocess
import tempfile
import uuid
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_parts = []
    entities = []
    current_offset = 0

    def add_text(s: str):
        nonlocal current_offset
        text_parts.append(s)
        current_offset += len(s.encode("utf-16-le")) // 2

    def add_custom(emoji_id: str, placeholder: str = "🔥"):
        nonlocal current_offset
        text_parts.append(placeholder)
        length = len(placeholder.encode("utf-16-le")) // 2
        entities.append(MessageEntity(
            type=MessageEntity.CUSTOM_EMOJI,
            offset=current_offset,
            length=length,
            custom_emoji_id=str(emoji_id)
        ))
        current_offset += length

    add_text("Welcome to AI-Label-Remover\n\n")
    add_text("Send any image or video (photo or file) and I will clean it for posting.\n\n")
    add_text("• Removes metadata & technical fingerprints\n")
    add_text("• High-quality re-encode\n")
    add_text("• Helps reduce AI labels on ")
    add_custom("6203873525116183636")   # X
    add_text(" ")
    add_custom("6201514939530618666")   # Instagram
    add_text(" ")
    add_custom("6204008550298033491")   # TikTok
    add_text(" ")
    add_custom("6237902409268470232")   # YouTube
    add_text("\n\n")
    add_text("Note: No tool can completely remove AI signatures from every file. Results vary by platform and content, but this bot works well on many images & videos.\n\n")
    add_text("For help contact @pvnuo ")
    add_custom("6201528571756815592")   # black hair

    text = "".join(text_parts)
    await update.message.reply_text(text, entities=entities)

async def process_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = None
    temp_files = []

    try:
        status_msg = await update.message.reply_text("⌛")

        if update.message.photo or (update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/")):
            if update.message.photo:
                file = await update.message.photo[-1].get_file()
            else:
                file = await update.message.document.get_file()

            bio = io.BytesIO()
            await file.download_to_memory(bio)
            bio.seek(0)

            img = Image.open(bio).convert("RGB")
            original_size = img.size

            data = list(img.getdata())
            clean = Image.new(img.mode, img.size)
            clean.putdata(data)

            angle = random.uniform(0.03, 0.08) * random.choice([-1, 1])
            clean = clean.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False)
            clean = clean.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=False)

            w, h = clean.size
            factor = random.uniform(0.995, 0.999)
            clean = clean.resize((int(w * factor), int(h * factor)), Image.Resampling.LANCZOS)
            clean = clean.resize(original_size, Image.Resampling.LANCZOS)

            noise = Image.effect_noise(clean.size, random.uniform(0.8, 1.6))
            noise = noise.convert("L")
            noise = ImageEnhance.Brightness(noise).enhance(random.uniform(0.03, 0.07))
            clean = Image.blend(clean, noise.convert("RGB"), random.uniform(0.015, 0.035))

            r, g, b = clean.split()
            r = ImageEnhance.Brightness(r).enhance(random.uniform(0.998, 1.002))
            g = ImageEnhance.Brightness(g).enhance(random.uniform(0.998, 1.002))
            b = ImageEnhance.Brightness(b).enhance(random.uniform(0.998, 1.002))
            clean = Image.merge("RGB", (r, g, b))

            clean = clean.filter(ImageFilter.UnsharpMask(
                radius=random.uniform(0.5, 0.9),
                percent=random.randint(50, 85),
                threshold=2
            ))

            enhancer = ImageEnhance.Contrast(clean)
            clean = enhancer.enhance(random.uniform(1.01, 1.04))

            temp = io.BytesIO()
            clean.save(temp, format="PNG", optimize=True)
            temp.seek(0)
            clean = Image.open(temp).convert("RGB")

            out = io.BytesIO()
            clean.save(out, format="JPEG", quality=97, optimize=True, progressive=True, subsampling=0)
            out.seek(0)

            clean2 = Image.open(out).convert("RGB")
            out2 = io.BytesIO()
            clean2.save(out2, format="JPEG", quality=96, optimize=True, progressive=True, subsampling=0)
            out2.seek(0)

            await update.message.reply_photo(photo=out2, caption="Ready")

        elif update.message.video or (update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("video/")):
            if update.message.video:
                file = await update.message.video.get_file()
            else:
                file = await update.message.document.get_file()

            input_path = os.path.join(tempfile.gettempdir(), f"in_{uuid.uuid4().hex}.mp4")
            output_path = os.path.join(tempfile.gettempdir(), f"out_{uuid.uuid4().hex}.mp4")
            temp_files.extend([input_path, output_path])

            await file.download_to_drive(input_path)

            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-map_metadata", "-1",
                "-c:v", "libx264",
                "-crf", "17",
                "-preset", "medium",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                output_path
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                error_msg = result.stderr[-600:] if result.stderr else "Unknown FFmpeg error"
                raise Exception(f"FFmpeg failed:\n{error_msg}")

            with open(output_path, "rb") as f:
                await update.message.reply_video(
                    video=f,
                    caption="Ready",
                    supports_streaming=True
                )

        else:
            await status_msg.edit_text("Send image or video only.")
            return

        if status_msg:
            await status_msg.delete()

    except Exception as e:
        error_text = str(e)[:900]
        if status_msg:
            try:
                await status_msg.edit_text(f"Failed:\n{error_text}")
            except:
                await update.message.reply_text(f"Failed:\n{error_text}")
        else:
            await update.message.reply_text(f"Failed:\n{error_text}")

    finally:
        for f in temp_files:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except:
                pass

def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .read_timeout(60)
        .write_timeout(60)
        .connect_timeout(60)
        .pool_timeout(60)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.IMAGE | filters.VIDEO | filters.Document.VIDEO,
        process_media
    ))

    print("Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
