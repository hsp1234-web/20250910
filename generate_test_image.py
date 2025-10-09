from PIL import Image, ImageDraw, ImageFont

# --- 設定 ---
FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
IMAGE_WIDTH = 800
IMAGE_HEIGHT = 600
BACKGROUND_COLOR = "white"
TEXT_COLOR = "black"
OUTPUT_FILENAME = "test_ocr_image.png"

# 我們要寫入圖片的文字內容
TEXT_TO_WRITE = [
    (50, 50, "本地AI處理進度", 40),
    (50, 150, "ID: 1", 24),
    (50, 190, "標題: 四月小作文, 龍巖", 24),
    (50, 230, "作者: 477-0696872過兒", 24),
    (50, 270, "時間: 2025-04-06 00:22", 24),
    (550, 160, "下載完成", 28),
    (50, 350, "ID: 3", 24),
    (50, 390, "標題: Sean 四月小作文-敬鵬 2355", 24),
    (50, 430, "作者: 508-0324115", 24),
    (50, 470, "時間: 2025-04-06 17:28", 24),
    (550, 400, "下載失敗", 28),
]

def generate_image():
    """
    使用 Pillow 生成一張包含指定繁體中文文字的測試圖片。
    """
    try:
        # 建立一個白色的畫布
        image = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(image)

        print(f"正在生成圖片 '{OUTPUT_FILENAME}'...")

        # 遍歷文字列表並將其繪製到圖片上
        for x, y, text, size in TEXT_TO_WRITE:
            # 載入字體，Pillow 可以自動從 .ttc 集合中選擇合適的字形
            font = ImageFont.truetype(FONT_PATH, size)
            draw.text((x, y), text, font=font, fill=TEXT_COLOR)

        # 儲存圖片
        image.save(OUTPUT_FILENAME)
        print(f"✅ 成功生成測試圖片: {OUTPUT_FILENAME}")
        return True

    except FileNotFoundError:
        print(f"❌ 錯誤：找不到字體檔案 '{FONT_PATH}'。")
        print("請確認 'fonts-noto-cjk' 套件已正確安裝。")
        return False
    except Exception as e:
        print(f"❌ 生成圖片時發生未預期的錯誤: {e}")
        return False

if __name__ == "__main__":
    generate_image()