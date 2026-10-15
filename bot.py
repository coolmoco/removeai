from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler
)
from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import io
import os
import random
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Send me any image (photo or file).\n\n"
        "I will completely strip metadata, break AI fingerprints, "
        "and re-encode it so Instagram, YouTube, TikTok etc. "
        "usually stop showing the AI label.\n\n"
        "• Zero content loss\n"
        "• Quality stays same or better\n"
        "• Works on photos + documents\n\n"
        "Just drop the image.\n\n"
        "For any help contact @pvnuo"
    )
    await update.message.reply_text(text)

async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = None
    try:
        # ⌛ status message
        status_msg = await update.message.reply_text("⌛")

        # Photo ya Document dono se image nikaalo
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
        elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"):
            file = await update.message.document.get_file()
        else:
            await status_msg.edit_text("Sirf image bhejo (photo ya image file).")
            return

        bio = io.BytesIO()
        await file.download_to_memory(bio)
        bio.seek(0)

        img = Image.open(bio).convert("RGB")

        # ---------- Strong cleaning pipeline ----------
        # 1. Pure pixel copy (metadata gone)
        data = list(img.getdata())
        clean = Image.new(img.mode, img.size)
        clean.putdata(data)

        # 2. Micro resize (0.3% - almost invisible, breaks fingerprints)
        w, h = clean.size
        new_w = int(w * 0.997)
        new_h = int(h * 0.997)
        clean = clean.resize((new_w, new_h), Image.Resampling.LANCZOS)
        clean = clean.resize((w, h), Image.Resampling.LANCZOS)

        # 3. Extremely light noise (content safe)
        noise = Image.effect_noise(clean.size, 2)
        noise = noise.convert("L")
        noise = ImageEnhance.Brightness(noise).enhance(0.08)
        clean = Image.blend(clean, noise.convert("RGB"), 0.04)

        # 4. Tiny color channel shift (breaks some detectors)
        r, g, b = clean.split()
        r = ImageEnhance.Brightness(r).enhance(1.002)
        b = ImageEnhance.Brightness(b).enhance(0.998)
        clean = Image.merge("RGB", (r, g, b))

        # 5. Light unsharp (keeps sharpness)
        clean = clean.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=2))

        # 6. High quality re-encode (two passes)
        out = io.BytesIO()
        clean.save(out, format="JPEG", quality=96, optimize=True, progressive=True)
        out.seek(0)

        # Second pass for extra fingerprint break
        clean2 = Image.open(out).convert("RGB")
        out2 = io.BytesIO()
        clean2.save(out2, format="JPEG", quality=95, optimize=True, progressive=True)
        out2.seek(0)

        # Send cleaned image
        await update.message.reply_photo(
            photo=out2,
            caption="Cleaned • Metadata gone • Ready for IG / YT / TikTok"
        )

        # Delete ⌛
        if status_msg:
            await status_msg.delete()

    except Exception as e:
        if status_msg:
            try:
                await status_msg.edit_text(f"Error: {str(e)[:100]}")
            except:
                pass
        else:
            await update.message.reply_text(f"Error: {str(e)[:100]}")

def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, process_image))

    print("Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()