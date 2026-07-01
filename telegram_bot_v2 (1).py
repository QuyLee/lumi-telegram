import os
import re
import json
import logging
import asyncio
import requests
import tempfile
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from openai import OpenAI
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not DEEPSEEK_API_KEY:
    print("❌ LỖI: Chưa có DEEPSEEK_API_KEY trong file .env")
    exit()
if not TELEGRAM_TOKEN:
    print("❌ LỖI: Chưa có TELEGRAM_BOT_TOKEN trong file .env")
    exit()

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

user_data = {}
TEMP_DIR = "temp_files"
os.makedirs(TEMP_DIR, exist_ok=True)

# ═══════════════════════════════════════════════
# HELPER: GỌI AI
# ═══════════════════════════════════════════════

def ai(prompt, temperature=0.7, max_tokens=4000):
    """Wrapper gọi DeepSeek API"""
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

def tao_file_txt(noi_dung, ten_file):
    file_path = os.path.join(TEMP_DIR, ten_file)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(noi_dung)
    return file_path

def lay_noi_dung_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            tag.decompose()
        text = re.sub(r'\s+', ' ', soup.get_text())
        return text[:15000]
    except:
        return None

def init_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            'noi_dung': None, 'kich_ban': None, 'tieu_de': None,
            'tieu_de_raw': None, 'seo': None, 'thumbnail': None,
            'prompt_anh': None, 'lich_dang': [], 'checklist': {}
        }

# ═══════════════════════════════════════════════
# MODULE 1: VIẾT KỊCH BẢN
# ═══════════════════════════════════════════════

def module_viet_kich_ban(noi_dung, huong_dan="", kich_ban_mau=""):
    try:
        phan_tich = ""
        if kich_ban_mau:
            phan_tich = f"""PHÂN TÍCH KỊCH BẢN MẪU:
---
{kich_ban_mau[:3000]}
---
Học cấu trúc, giọng văn, nhịp điệu. KHÔNG sao chép nội dung.
"""
        hd = f"HƯỚNG DẪN CHỈNH SỬA: {huong_dan}\n\n" if huong_dan else ""
        prompt = f"""Bạn là biên kịch kênh YouTube "Tiệm Truyện Nhỏ Nhỏ".

{phan_tich}

NỘI DUNG: {noi_dung[:8000]}

{hd}YÊU CẦU:
1. Văn bản thuần, không gạch đầu dòng, không ký hiệu
2. Cấu trúc: Hook → Phát triển → Cao trào → Kết luận
3. Mỗi đoạn 3-5 câu, mỗi câu 10-18 từ
4. Tông: Triết lý, lạnh, kiểm soát, có trọng lượng
5. Tránh: "và rồi", "thế là", "lúc đó", "thực ra thì"
6. Độ dài: 800-1500 chữ
7. Dùng dấu "," và ":" để tạo nhịp nghỉ cho TTS
{"8. KHÔNG SAO CHÉP nội dung gốc" if kich_ban_mau else ""}

CHỈ VIẾT VĂN BẢN KỊCH BẢN, KHÔNG GÌ THÊM:"""
        result = ai(prompt, 0.7, 4000)
        result = re.sub(r'^```[\s\S]*?\n', '', result)
        result = re.sub(r'\n```$', '', result)
        return result
    except Exception as e:
        return f"[Lỗi] {str(e)}"

# ═══════════════════════════════════════════════
# MODULE 2: TIÊU ĐỀ
# ═══════════════════════════════════════════════

def module_tao_tieu_de(kich_ban):
    try:
        prompt = f"""Tạo 5 TIÊU ĐỀ YOUTUBE cho kịch bản này.

Kịch bản: {kich_ban[:2000]}

Yêu cầu: Dưới 100 ký tự, gây tò mò, có từ khoá SEO.

Định dạng:
===TIEU_DE_1===
[tiêu đề]
===PHAN_TICH_1===
Điểm mạnh: ...
Viral: X/10

===TIEU_DE_2===
...
(lặp đến tiêu đề 5)

===KET_LUAN===
Khuyến nghị chọn số..."""
        return ai(prompt, 0.8)
    except Exception as e:
        return f"[Lỗi] {str(e)}"

# ═══════════════════════════════════════════════
# MODULE 3: SEO
# ═══════════════════════════════════════════════

def module_viet_seo(kich_ban, tieu_de):
    try:
        prompt = f"""Viết SEO YouTube.

TIÊU ĐỀ: {tieu_de}
KỊCH BẢN: {kich_ban[:2000]}

===MO_TA===
150-200 từ, hấp dẫn, có CTA
===TAG===
15-20 tag, phân cách bằng dấu phẩy
===HASHTAG===
5-7 hashtag"""
        return ai(prompt, 0.7)
    except Exception as e:
        return f"[Lỗi] {str(e)}"

# ═══════════════════════════════════════════════
# MODULE 4: THUMBNAIL
# ═══════════════════════════════════════════════

def module_prompt_thumbnail(kich_ban, tieu_de):
    try:
        prompt = f"""Tạo 1 PROMPT vẽ thumbnail YouTube (1 đoạn văn liền mạch).

TIÊU ĐỀ: {tieu_de}
NỘI DUNG: {kich_ban[:500]}

Yêu cầu:
- Nhân vật: CHỊ LUMI (ngôi sao 5 cánh, vàng ấm, mắt to, má hồng, váy voan)
- Phong cách: cinematic, god rays, tương phản, emotional
- Background: Bầu trời đêm, trăng vàng, sao lấp lánh
- Tỷ lệ 16:9, KHÔNG có chữ

1 ĐOẠN VĂN DUY NHẤT:"""
        result = ai(prompt, 0.8)
        return ' '.join(result.strip().split())
    except Exception as e:
        return f"[Lỗi] {str(e)}"

# ═══════════════════════════════════════════════
# MODULE 5: PROMPT ẢNH
# ═══════════════════════════════════════════════

def module_prompt_anh(kich_ban, so_anh_mong_muon=None):
    try:
        so_chu = len(kich_ban)
        so_anh = so_anh_mong_muon if so_anh_mong_muon else max(5, min(50, int(so_chu / 150)))
        prompt = f"""Tạo đúng {so_anh} PROMPT ẢNH MINH HOẠ theo thứ tự tình tiết.

Kịch bản: {kich_ban[:6000]}

Yêu cầu:
1. Đúng {so_anh} ảnh, theo thứ tự thời gian kịch bản
2. Phong cách: 3D CHIBI, ngộ nghĩnh, đáng yêu
3. Màu sắc: Pastel, ấm áp
4. Nhân vật: CHỊ LUMI (ngôi sao 5 cánh vàng, mắt to, má hồng, váy voan)
5. Tỷ lệ 16:9, KHÔNG có chữ
6. Mỗi prompt đủ chi tiết (bối cảnh, cảm xúc, ánh sáng)

JSON array, đúng {so_anh} phần tử:
[{{"so_thu_tu": 1, "tinh_tiet": "...", "prompt": "..."}}]
CHỈ TRẢ VỀ JSON:"""
        content = ai(prompt, 0.8, 8000)
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        return json.loads(json_match.group() if json_match else content)
    except Exception as e:
        return f"[Lỗi] {str(e)}"

# ═══════════════════════════════════════════════
# MODULE 6 (MỚI): CHECKLIST VIDEO
# ═══════════════════════════════════════════════

CHECKLIST_MAC_DINH = {
    "📝 Tiền sản xuất": [
        "Viết kịch bản (Module 1)",
        "Chọn tiêu đề (Module 2)",
        "Tạo SEO (Module 3)",
        "Tạo prompt thumbnail (Module 4)",
        "Tạo prompt ảnh minh hoạ (Module 5)",
    ],
    "🎙️ Sản xuất": [
        "Thu âm TTS / giọng đọc",
        "Tạo ảnh minh hoạ từ prompts",
        "Tạo thumbnail",
        "Dựng video (ghép ảnh + audio)",
        "Thêm nhạc nền",
        "Thêm phụ đề (tuỳ chọn)",
    ],
    "📤 Đăng bài": [
        "Upload video lên YouTube",
        "Điền tiêu đề + mô tả + tag từ Module 3",
        "Thêm thumbnail",
        "Đặt lịch đăng hoặc đăng ngay",
        "Đăng bài kèm link lên Facebook/TikTok",
        "Pin comment chứa link/CTA",
    ]
}

def lay_checklist(user_id):
    init_user(user_id)
    if not user_data[user_id].get('checklist'):
        user_data[user_id]['checklist'] = {
            cat: {item: False for item in items}
            for cat, items in CHECKLIST_MAC_DINH.items()
        }
    return user_data[user_id]['checklist']

def format_checklist(checklist):
    lines = ["📋 CHECKLIST SẢN XUẤT VIDEO\n"]
    tong = sum(v for cat in checklist.values() for v in cat.values())
    max_t = sum(len(cat) for cat in checklist.values())
    lines.append(f"Tiến độ: {tong}/{max_t} việc ✅\n")
    for cat, items in checklist.items():
        lines.append(f"\n{cat}")
        for item, done in items.items():
            lines.append(f"  {'✅' if done else '⬜'} {item}")
    return "\n".join(lines)

# ═══════════════════════════════════════════════
# MODULE 7 (MỚI): LỊCH ĐĂNG BÀI
# ═══════════════════════════════════════════════

def tao_lich_dang(so_video_tuan=3):
    """Tạo lịch đăng video cho 4 tuần tới"""
    thu_tot = {
        3: ["Thứ 3", "Thứ 5", "Thứ 7"],
        2: ["Thứ 4", "Thứ 7"],
        1: ["Thứ 7"],
    }.get(so_video_tuan, ["Thứ 3", "Thứ 5", "Thứ 7"])

    lich = []
    hom_nay = datetime.now()
    ngay = hom_nay
    dem = 0
    while dem < so_video_tuan * 4:
        ten_thu = ["Thứ 2","Thứ 3","Thứ 4","Thứ 5","Thứ 6","Thứ 7","Chủ nhật"][ngay.weekday()]
        if ten_thu in thu_tot:
            lich.append({
                "ngay": ngay.strftime("%d/%m/%Y"),
                "thu": ten_thu,
                "gio": "20:00",
                "tieu_de": f"Video #{dem+1}",
                "trang_thai": "🔲 Chưa có nội dung"
            })
            dem += 1
        ngay += timedelta(days=1)
    return lich

def format_lich(lich_dang):
    if not lich_dang:
        return "📅 Chưa có lịch đăng. Dùng /lich để tạo lịch."
    lines = ["📅 LỊCH ĐĂNG VIDEO\n"]
    tuan = 0
    for i, v in enumerate(lich_dang):
        if i % 3 == 0:
            tuan += 1
            lines.append(f"\n─── TUẦN {tuan} ───")
        lines.append(f"{v['thu']} {v['ngay']} {v['gio']}")
        lines.append(f"  {v['trang_thai']}")
        if v['tieu_de'] != f"Video #{i+1}":
            lines.append(f"  📌 {v['tieu_de']}")
    return "\n".join(lines)

# ═══════════════════════════════════════════════
# PIPELINE TỰ ĐỘNG: CHẠY 1 → 5
# ═══════════════════════════════════════════════

async def chay_pipeline_day_du(query, user_id, noi_dung, kich_ban_mau=""):
    """Chạy toàn bộ 5 module, trả kết quả gộp vào 1 file ZIP-style text"""
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    ket_qua = {}

    # Module 1
    await query.message.reply_text("⏳ [1/5] Đang viết kịch bản...")
    kich_ban = module_viet_kich_ban(noi_dung, "", kich_ban_mau)
    if kich_ban.startswith("[Lỗi]"):
        await query.message.reply_text(f"❌ Module 1 lỗi: {kich_ban}")
        return
    user_data[user_id]['kich_ban'] = kich_ban
    ket_qua['kich_ban'] = kich_ban

    fp = tao_file_txt(kich_ban, f"1_kich_ban_{ts}.txt")
    with open(fp, 'rb') as f:
        await query.message.reply_document(document=f, filename=os.path.basename(fp),
            caption=f"✅ [1/5] KỊCH BẢN · {len(kich_ban)} chữ\n💡 /sua [góp ý] để chỉnh")

    # Module 2
    await query.message.reply_text("⏳ [2/5] Đang tạo tiêu đề...")
    raw_tieu_de = module_tao_tieu_de(kich_ban)
    user_data[user_id]['tieu_de_raw'] = raw_tieu_de

    # Tự chọn tiêu đề 1
    tieu_de = ""
    for line in raw_tieu_de.split('\n'):
        if "===TIEU_DE_1===" in line:
            continue
        if "===PHAN_TICH" in line or "===TIEU_DE_2" in line:
            break
        if line.strip():
            tieu_de = line.strip()
            break
    tieu_de = tieu_de or "Tiêu đề video"
    user_data[user_id]['tieu_de'] = tieu_de

    fp = tao_file_txt(raw_tieu_de, f"2_tieu_de_{ts}.txt")
    with open(fp, 'rb') as f:
        await query.message.reply_document(document=f, filename=os.path.basename(fp),
            caption=f"✅ [2/5] 5 TIÊU ĐỀ\n📌 Tạm chọn: {tieu_de[:60]}\n💡 Dùng /chon_tieu_de để đổi")

    # Module 3
    await query.message.reply_text("⏳ [3/5] Đang viết SEO...")
    seo = module_viet_seo(kich_ban, tieu_de)
    user_data[user_id]['seo'] = seo
    fp = tao_file_txt(seo, f"3_seo_{ts}.txt")
    with open(fp, 'rb') as f:
        await query.message.reply_document(document=f, filename=os.path.basename(fp),
            caption="✅ [3/5] SEO (mô tả + tag + hashtag)")

    # Module 4
    await query.message.reply_text("⏳ [4/5] Đang tạo prompt thumbnail...")
    thumbnail = module_prompt_thumbnail(kich_ban, tieu_de)
    user_data[user_id]['thumbnail'] = thumbnail
    fp = tao_file_txt(thumbnail, f"4_thumbnail_{ts}.txt")
    with open(fp, 'rb') as f:
        await query.message.reply_document(document=f, filename=os.path.basename(fp),
            caption="✅ [4/5] PROMPT THUMBNAIL")

    # Module 5
    so_anh = max(5, min(50, int(len(kich_ban) / 150)))
    await query.message.reply_text(f"⏳ [5/5] Đang tạo {so_anh} prompt ảnh minh hoạ...")
    prompt_anh = module_prompt_anh(kich_ban, so_anh)
    user_data[user_id]['prompt_anh'] = prompt_anh

    if isinstance(prompt_anh, list):
        fp = tao_file_txt(json.dumps(prompt_anh, ensure_ascii=False, indent=2), f"5_prompt_anh_{ts}.json")
        cap = f"✅ [5/5] {len(prompt_anh)} PROMPT ẢNH MINH HOẠ"
    else:
        fp = tao_file_txt(str(prompt_anh), f"5_prompt_anh_{ts}.txt")
        cap = "✅ [5/5] PROMPT ẢNH MINH HOẠ"
    with open(fp, 'rb') as f:
        await query.message.reply_document(document=f, filename=os.path.basename(fp), caption=cap)

    # Tự động tick checklist
    cl = lay_checklist(user_id)
    for item in list(cl.get("📝 Tiền sản xuất", {}).keys()):
        cl["📝 Tiền sản xuất"][item] = True

    # Tóm tắt
    await query.message.reply_text(
        f"🎉 HOÀN THÀNH! Đã tạo đủ tài liệu cho 1 video.\n\n"
        f"📌 Tiêu đề đã chọn tạm:\n{tieu_de}\n\n"
        f"📋 Checklist tiền sản xuất đã được tick tự động!\n\n"
        f"Bước tiếp theo:\n"
        f"• /checklist – Xem tiến độ sản xuất\n"
        f"• /chon_tieu_de – Đổi tiêu đề khác\n"
        f"• /sua [góp ý] – Sửa kịch bản\n"
        f"• /lich – Xem lịch đăng video"
    )

# ═══════════════════════════════════════════════
# MENU CHÍNH
# ═══════════════════════════════════════════════

def menu_chinh_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 TẠO VIDEO MỚI (1→5 tự động)", callback_data="auto_all")],
        [
            InlineKeyboardButton("📝 Kịch bản", callback_data="m1"),
            InlineKeyboardButton("📊 Tiêu đề", callback_data="m2"),
        ],
        [
            InlineKeyboardButton("🔍 SEO", callback_data="m3"),
            InlineKeyboardButton("🎨 Thumbnail", callback_data="m4"),
            InlineKeyboardButton("🖼️ Ảnh", callback_data="m5"),
        ],
        [
            InlineKeyboardButton("📋 Checklist", callback_data="checklist"),
            InlineKeyboardButton("📅 Lịch đăng", callback_data="lich_xem"),
        ],
        [InlineKeyboardButton("🔍 Dùng phong cách đối thủ", callback_data="doi_thu_menu")],
    ])

async def hien_thi_menu(update_or_query, user_id, is_query=False):
    u = user_data.get(user_id, {})
    so_chu_nd = len(u.get('noi_dung') or '')
    so_chu_kb = len(u.get('kich_ban') or '')
    td = (u.get('tieu_de') or '')[:40]

    status = (
        f"📊 Nội dung: {'✅ ' + str(so_chu_nd) + ' chữ' if so_chu_nd else '❌ Chưa có'}\n"
        f"📝 Kịch bản: {'✅ ' + str(so_chu_kb) + ' chữ' if so_chu_kb else '❌ Chưa có'}\n"
        f"📌 Tiêu đề: {'✅ ' + td if td else '❌ Chưa chọn'}\n"
        f"🔍 SEO: {'✅' if u.get('seo') else '❌'} · "
        f"🎨 Thumbnail: {'✅' if u.get('thumbnail') else '❌'} · "
        f"🖼️ Ảnh: {'✅ ' + str(len(u.get('prompt_anh') or [])) if isinstance(u.get('prompt_anh'), list) else '❌'}"
    )
    text = f"🌟 TIỆM TRUYỆN NHỎ NHỎ\n\n{status}\n\n📤 Gửi nội dung hoặc chọn module:"

    if is_query:
        await update_or_query.message.reply_text(text, reply_markup=menu_chinh_keyboard())
    else:
        await update_or_query.message.reply_text(text, reply_markup=menu_chinh_keyboard())

# ═══════════════════════════════════════════════
# XỬ LÝ FILE & TIN NHẮN
# ═══════════════════════════════════════════════

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    file = update.message.document
    if not file.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Chỉ hỗ trợ file .txt")
        return
    msg = await update.message.reply_text(f"📥 Đang đọc {file.file_name}...")
    try:
        file_obj = await file.get_file()
        fp = os.path.join(TEMP_DIR, f"upload_{file.file_name}")
        await file_obj.download_to_drive(fp)
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        if len(content) < 50:
            await msg.edit_text("❌ File quá ngắn (< 50 ký tự)")
            return
        user_data[user_id]['noi_dung'] = content
        user_data[user_id]['kich_ban'] = None
        user_data[user_id]['tieu_de'] = None
        await msg.delete()
        await update.message.reply_text(
            f"✅ Đã đọc file: {file.file_name}\n"
            f"📊 {len(content)} chữ\n\n"
            f"Chọn thao tác:"
        , reply_markup=menu_chinh_keyboard())
    except Exception as e:
        await msg.edit_text(f"❌ Lỗi: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    text = update.message.text
    msg = await update.message.reply_text("🔄 Đang xử lý...")
    try:
        if text.startswith(('http://', 'https://')):
            await msg.edit_text("🌐 Đang đọc nội dung từ web...")
            content = lay_noi_dung_url(text)
            if not content or len(content) < 100:
                await msg.edit_text("❌ Không thể đọc URL này")
                return
        else:
            content = text
        if len(content) < 50:
            await msg.edit_text("❌ Nội dung quá ngắn")
            return
        user_data[user_id]['noi_dung'] = content
        user_data[user_id]['kich_ban'] = None
        user_data[user_id]['tieu_de'] = None
        await msg.delete()
        await update.message.reply_text(
            f"✅ Đã nhận nội dung ({len(content)} chữ)\n\nChọn thao tác:",
            reply_markup=menu_chinh_keyboard()
        )
    except Exception as e:
        await msg.edit_text(f"❌ Lỗi: {str(e)}")

# ═══════════════════════════════════════════════
# XỬ LÝ CALLBACK
# ═══════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    init_user(user_id)
    data = query.data
    u = user_data[user_id]

    def need_content():
        return not u.get('noi_dung')

    def need_kich_ban():
        return not u.get('kich_ban')

    # ── TỰ ĐỘNG TẤT CẢ ──────────────────────────
    if data == "auto_all":
        if need_content():
            await query.edit_message_text("❌ Chưa có nội dung!\n\n💡 Gửi nội dung hoặc file .txt trước.")
            return
        await query.edit_message_text("🚀 Bắt đầu tạo đủ 5 tài liệu...\n⏱️ Khoảng 2-3 phút, vui lòng đợi.")
        await chay_pipeline_day_du(query, user_id, u['noi_dung'])

    # ── MODULE 1 ──────────────────────────────────
    elif data == "m1":
        if need_content():
            await query.edit_message_text("❌ Chưa có nội dung! Gửi file hoặc text trước.")
            return
        await query.edit_message_text("📝 Đang viết kịch bản... (~30 giây)")
        kb = module_viet_kich_ban(u['noi_dung'])
        if kb.startswith("[Lỗi]"):
            await query.message.reply_text(f"❌ {kb}")
            return
        user_data[user_id]['kich_ban'] = kb
        fp = tao_file_txt(kb, f"kich_ban_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(fp, 'rb') as f:
            await query.message.reply_document(document=f, filename=os.path.basename(fp),
                caption=f"✅ KỊCH BẢN · {len(kb)} chữ\n💡 /sua [góp ý] để chỉnh sửa")
        await hien_thi_menu(query, user_id, is_query=True)

    # ── MODULE 2 ──────────────────────────────────
    elif data == "m2":
        nguon = u.get('kich_ban') or u.get('noi_dung')
        if not nguon:
            await query.edit_message_text("❌ Chưa có nội dung!")
            return
        await query.edit_message_text("📊 Đang tạo 5 tiêu đề...")
        raw = module_tao_tieu_de(nguon)
        user_data[user_id]['tieu_de_raw'] = raw
        fp = tao_file_txt(raw, f"tieu_de_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(fp, 'rb') as f:
            await query.message.reply_document(document=f, filename=os.path.basename(fp),
                caption="📊 5 TIÊU ĐỀ + PHÂN TÍCH")
        # Nút chọn nhanh
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📌 Chọn tiêu đề #{i}", callback_data=f"td_{i}")] for i in range(1,6)
        ] + [[InlineKeyboardButton("⏭️ Bỏ qua", callback_data="td_skip")]])
        await query.message.reply_text("Chọn tiêu đề muốn dùng:", reply_markup=keyboard)

    elif data.startswith("td_"):
        so = data.split("_")[1]
        if so == "skip":
            await query.edit_message_text("⏭️ Bỏ qua chọn tiêu đề.")
            await hien_thi_menu(query, user_id, is_query=True)
            return
        raw = u.get('tieu_de_raw', '')
        tieu_de = ""
        dem = False
        for line in raw.split('\n'):
            if f"===TIEU_DE_{so}===" in line:
                dem = True
                continue
            if dem and line.strip() and not line.startswith("==="):
                tieu_de = line.strip()
                break
        if tieu_de:
            user_data[user_id]['tieu_de'] = tieu_de
            await query.edit_message_text(f"✅ Đã chọn tiêu đề #{so}:\n\n📌 {tieu_de}")
        else:
            await query.edit_message_text(f"❌ Không tìm thấy tiêu đề #{so}")
        await hien_thi_menu(query, user_id, is_query=True)

    # ── MODULE 3 ──────────────────────────────────
    elif data == "m3":
        nguon = u.get('kich_ban') or u.get('noi_dung')
        if not nguon:
            await query.edit_message_text("❌ Chưa có nội dung!")
            return
        await query.edit_message_text("🔍 Đang viết SEO...")
        tieu_de = u.get('tieu_de') or "Tiệm Truyện Nhỏ Nhỏ"
        seo = module_viet_seo(nguon, tieu_de)
        user_data[user_id]['seo'] = seo
        fp = tao_file_txt(seo, f"seo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(fp, 'rb') as f:
            await query.message.reply_document(document=f, filename=os.path.basename(fp),
                caption=f"✅ SEO\n📌 Tiêu đề: {tieu_de[:60]}")
        await hien_thi_menu(query, user_id, is_query=True)

    # ── MODULE 4 ──────────────────────────────────
    elif data == "m4":
        nguon = u.get('kich_ban') or u.get('noi_dung')
        if not nguon:
            await query.edit_message_text("❌ Chưa có nội dung!")
            return
        await query.edit_message_text("🎨 Đang tạo prompt thumbnail...")
        tieu_de = u.get('tieu_de') or "Tiệm Truyện Nhỏ Nhỏ"
        thumb = module_prompt_thumbnail(nguon, tieu_de)
        user_data[user_id]['thumbnail'] = thumb
        fp = tao_file_txt(thumb, f"thumbnail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(fp, 'rb') as f:
            await query.message.reply_document(document=f, filename=os.path.basename(fp),
                caption="✅ PROMPT THUMBNAIL")
        await hien_thi_menu(query, user_id, is_query=True)

    # ── MODULE 5 ──────────────────────────────────
    elif data == "m5":
        nguon = u.get('kich_ban') or u.get('noi_dung')
        if not nguon:
            await query.edit_message_text("❌ Chưa có nội dung!")
            return
        so_anh = max(5, min(50, int(len(nguon) / 150)))
        await query.edit_message_text(f"🖼️ Đang tạo {so_anh} prompt ảnh...")
        result = module_prompt_anh(nguon, so_anh)
        user_data[user_id]['prompt_anh'] = result
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        if isinstance(result, list):
            fp = tao_file_txt(json.dumps(result, ensure_ascii=False, indent=2), f"prompt_anh_{ts}.json")
            cap = f"✅ {len(result)} PROMPT ẢNH MINH HOẠ"
        else:
            fp = tao_file_txt(str(result), f"prompt_anh_{ts}.txt")
            cap = "✅ PROMPT ẢNH MINH HOẠ"
        with open(fp, 'rb') as f:
            await query.message.reply_document(document=f, filename=os.path.basename(fp), caption=cap)
        await hien_thi_menu(query, user_id, is_query=True)

    # ── CHECKLIST ─────────────────────────────────
    elif data == "checklist":
        cl = lay_checklist(user_id)
        text = format_checklist(cl)
        # Tạo nút tick từng hạng mục
        btns = []
        for cat, items in cl.items():
            for item, done in items.items():
                short = item[:25]
                icon = "✅" if done else "⬜"
                btns.append([InlineKeyboardButton(
                    f"{icon} {short}", callback_data=f"cl_toggle|{cat}|{item}"
                )])
        btns.append([
            InlineKeyboardButton("🔄 Reset tất cả", callback_data="cl_reset"),
            InlineKeyboardButton("🔙 Menu", callback_data="menu")
        ])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("cl_toggle|"):
        _, cat, item = data.split("|", 2)
        cl = lay_checklist(user_id)
        if cat in cl and item in cl[cat]:
            cl[cat][item] = not cl[cat][item]
        # Re-render
        text = format_checklist(cl)
        btns = []
        for c, items in cl.items():
            for it, done in items.items():
                short = it[:25]
                icon = "✅" if done else "⬜"
                btns.append([InlineKeyboardButton(
                    f"{icon} {short}", callback_data=f"cl_toggle|{c}|{it}"
                )])
        btns.append([
            InlineKeyboardButton("🔄 Reset tất cả", callback_data="cl_reset"),
            InlineKeyboardButton("🔙 Menu", callback_data="menu")
        ])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(btns))

    elif data == "cl_reset":
        user_data[user_id]['checklist'] = {}
        cl = lay_checklist(user_id)
        await query.edit_message_text(
            "🔄 Đã reset checklist!\n\n" + format_checklist(cl),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Mở checklist", callback_data="checklist"),
                InlineKeyboardButton("🔙 Menu", callback_data="menu")
            ]])
        )

    # ── LỊCH ĐĂNG ─────────────────────────────────
    elif data == "lich_xem":
        lich = user_data[user_id].get('lich_dang', [])
        if not lich:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("3 video/tuần", callback_data="lich_tao_3")],
                [InlineKeyboardButton("2 video/tuần", callback_data="lich_tao_2")],
                [InlineKeyboardButton("1 video/tuần", callback_data="lich_tao_1")],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
            ])
            await query.edit_message_text(
                "📅 Chưa có lịch đăng.\n\nBạn muốn đăng bao nhiêu video/tuần?",
                reply_markup=keyboard
            )
        else:
            await query.edit_message_text(
                format_lich(lich),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Tạo lịch mới", callback_data="lich_menu")],
                    [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
                ])
            )

    elif data == "lich_menu":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("3 video/tuần (Thứ 3/5/7)", callback_data="lich_tao_3")],
            [InlineKeyboardButton("2 video/tuần (Thứ 4/7)", callback_data="lich_tao_2")],
            [InlineKeyboardButton("1 video/tuần (Thứ 7)", callback_data="lich_tao_1")],
            [InlineKeyboardButton("🔙 Quay lại", callback_data="lich_xem")],
        ])
        await query.edit_message_text("📅 Chọn tần suất đăng bài:", reply_markup=keyboard)

    elif data.startswith("lich_tao_"):
        so = int(data.split("_")[-1])
        lich = tao_lich_dang(so)
        user_data[user_id]['lich_dang'] = lich
        await query.edit_message_text(
            format_lich(lich),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Đổi tần suất", callback_data="lich_menu")],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
            ])
        )

    # ── ĐỐI THỦ ──────────────────────────────────
    elif data == "doi_thu_menu":
        await query.edit_message_text(
            "🔍 DÙNG PHONG CÁCH ĐỐI THỦ\n\n"
            "Gửi kịch bản đối thủ bằng 1 trong 2 cách:\n\n"
            "1️⃣ /doi_thu [URL YouTube đối thủ] – lấy tự động từ phụ đề\n\n"
            "2️⃣ Gửi file .txt chứa kịch bản đối thủ, rồi nhấn nút dưới:\n",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Dùng file TXT đã gửi làm mẫu", callback_data="doi_thu_dung_file")],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
            ])
        )

    elif data == "doi_thu_dung_file":
        noi_dung = u.get('noi_dung')
        if not noi_dung:
            await query.edit_message_text("❌ Chưa có file. Gửi file .txt trước!")
            return
        await query.edit_message_text(
            f"✅ Sẽ dùng file đã gửi ({len(noi_dung)} chữ) làm kịch bản mẫu.\n\n"
            "📝 Nhập chủ đề video mới bạn muốn viết:\n"
            "(Gửi tin nhắn text bình thường)"
        )
        user_data[user_id]['_mode'] = 'doi_thu_cho_chu_de'
        user_data[user_id]['_kich_ban_mau'] = noi_dung

    elif data == "menu":
        await hien_thi_menu(query, user_id, is_query=True)

# ═══════════════════════════════════════════════
# XỬ LÝ TIN NHẮN CÓ MODE ĐẶC BIỆT
# ═══════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    text = update.message.text
    u = user_data[user_id]

    # Mode: chờ chủ đề để viết kịch bản theo phong cách đối thủ
    if u.get('_mode') == 'doi_thu_cho_chu_de':
        chu_de = text
        kich_ban_mau = u.get('_kich_ban_mau', '')
        user_data[user_id]['_mode'] = None
        msg = await update.message.reply_text(
            f"🔍 Đang viết kịch bản theo phong cách đối thủ...\n"
            f"📌 Chủ đề: {chu_de[:80]}\n⏱️ ~30-60 giây..."
        )
        try:
            kb = module_viet_kich_ban(chu_de, "", kich_ban_mau)
            if kb.startswith("[Lỗi]"):
                await msg.edit_text(f"❌ {kb}")
                return
            user_data[user_id]['kich_ban'] = kb
            user_data[user_id]['noi_dung'] = chu_de
            fp = tao_file_txt(kb, f"kich_ban_motip_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(fp, 'rb') as f:
                await msg.delete()
                await update.message.reply_document(document=f, filename=os.path.basename(fp),
                    caption=f"✅ KỊCH BẢN THEO PHONG CÁCH ĐỐI THỦ\n📊 {len(kb)} chữ")
            await update.message.reply_text(
                "✅ Xong! Tiếp theo bạn muốn làm gì?",
                reply_markup=menu_chinh_keyboard()
            )
        except Exception as e:
            await msg.edit_text(f"❌ Lỗi: {str(e)}")
        return

    # Xử lý thông thường
    msg = await update.message.reply_text("🔄 Đang xử lý...")
    try:
        if text.startswith(('http://', 'https://')):
            await msg.edit_text("🌐 Đang đọc nội dung từ web...")
            content = lay_noi_dung_url(text)
            if not content or len(content) < 100:
                await msg.edit_text("❌ Không thể đọc URL này")
                return
        else:
            content = text
        if len(content) < 50:
            await msg.edit_text("❌ Nội dung quá ngắn")
            return
        user_data[user_id]['noi_dung'] = content
        user_data[user_id]['kich_ban'] = None
        user_data[user_id]['tieu_de'] = None
        await msg.delete()
        await update.message.reply_text(
            f"✅ Đã nhận nội dung ({len(content)} chữ)\n\nChọn thao tác:",
            reply_markup=menu_chinh_keyboard()
        )
    except Exception as e:
        await msg.edit_text(f"❌ Lỗi: {str(e)}")

# ═══════════════════════════════════════════════
# LỆNH SLASH
# ═══════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    await update.message.reply_text(
        "🌟 TIỆM TRUYỆN NHỎ NHỎ – v2.0\n\n"
        "📤 Gửi nội dung (text, URL, file .txt) để bắt đầu.\n"
        "Bot sẽ tự động tạo đủ kịch bản, tiêu đề, SEO, thumbnail và prompt ảnh!\n\n"
        "Lệnh nhanh:\n"
        "/menu – Mở menu chính\n"
        "/sua [góp ý] – Sửa kịch bản\n"
        "/checklist – Xem tiến độ sản xuất\n"
        "/lich – Quản lý lịch đăng\n"
        "/doi_thu [URL] – Phân tích YouTube đối thủ\n"
        "/chon_tieu_de – Xem và chọn lại tiêu đề\n",
        reply_markup=menu_chinh_keyboard()
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    await hien_thi_menu(update, user_id)

async def sua_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    gop_y = update.message.text.replace('/sua', '').strip()
    if not gop_y:
        await update.message.reply_text("❌ Ví dụ: /sua làm kịch bản cảm xúc hơn và dài hơn")
        return
    u = user_data[user_id]
    noi_dung = u.get('noi_dung')
    if not noi_dung:
        await update.message.reply_text("❌ Chưa có nội dung gốc!")
        return
    msg = await update.message.reply_text(f"📝 Đang sửa kịch bản: 『{gop_y}』\n⏱️ ~30 giây...")
    try:
        kb = module_viet_kich_ban(noi_dung, gop_y)
        if kb.startswith("[Lỗi]"):
            await msg.edit_text(f"❌ {kb}")
            return
        user_data[user_id]['kich_ban'] = kb
        fp = tao_file_txt(kb, f"kich_ban_sua_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(fp, 'rb') as f:
            await msg.delete()
            await update.message.reply_document(document=f, filename=os.path.basename(fp),
                caption=f"✅ KỊCH BẢN ĐÃ SỬA · {len(kb)} chữ\n💡 Góp ý: {gop_y}")
        await update.message.reply_text("✅ Xong! Tiếp theo:", reply_markup=menu_chinh_keyboard())
    except Exception as e:
        await msg.edit_text(f"❌ Lỗi: {str(e)}")

async def checklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    cl = lay_checklist(user_id)
    await update.message.reply_text(
        format_checklist(cl),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Tick/untick từng việc", callback_data="checklist"),
            InlineKeyboardButton("🔙 Menu", callback_data="menu")
        ]])
    )

async def lich_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    lich = user_data[user_id].get('lich_dang', [])
    if not lich:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("3 video/tuần", callback_data="lich_tao_3")],
            [InlineKeyboardButton("2 video/tuần", callback_data="lich_tao_2")],
            [InlineKeyboardButton("1 video/tuần", callback_data="lich_tao_1")],
        ])
        await update.message.reply_text("📅 Bạn muốn đăng bao nhiêu video/tuần?", reply_markup=keyboard)
    else:
        await update.message.reply_text(
            format_lich(lich),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Tạo lịch mới", callback_data="lich_menu"),
                InlineKeyboardButton("🔙 Menu", callback_data="menu")
            ]])
        )

async def doi_thu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Phân tích YouTube đối thủ qua URL"""
    user_id = update.effective_user.id
    init_user(user_id)
    text = update.message.text.replace('/doi_thu', '').strip()
    parts = text.split(None, 1)
    if not parts:
        await update.message.reply_text(
            "❌ Cách dùng:\n"
            "/doi_thu [URL YouTube]\n\n"
            "Ví dụ:\n/doi_thu https://youtube.com/watch?v=xxx"
        )
        return
    url = parts[0]
    chu_de_goi_y = parts[1] if len(parts) > 1 else ""
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ URL không hợp lệ!")
        return
    msg = await update.message.reply_text("🌐 Đang lấy phụ đề video...")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        patterns = [r'youtube\.com/watch\?v=([^&]+)', r'youtu\.be/([^?]+)']
        video_id = None
        for p in patterns:
            m = re.search(p, url)
            if m:
                video_id = m.group(1)
                break
        if not video_id:
            await msg.edit_text("❌ Không lấy được video ID từ URL!")
            return
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['vi', 'en'])
        kich_ban_mau = " ".join([t['text'] for t in transcript])
        if len(kich_ban_mau) < 100:
            await msg.edit_text("❌ Phụ đề quá ngắn!")
            return
        user_data[user_id]['_kich_ban_mau'] = kich_ban_mau
        if chu_de_goi_y:
            await msg.edit_text(f"✅ Đã lấy phụ đề ({len(kich_ban_mau)} ký tự)\n📝 Đang viết kịch bản...")
            kb = module_viet_kich_ban(chu_de_goi_y, "", kich_ban_mau)
            if kb.startswith("[Lỗi]"):
                await msg.edit_text(f"❌ {kb}")
                return
            user_data[user_id]['kich_ban'] = kb
            fp = tao_file_txt(kb, f"kich_ban_motip_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            with open(fp, 'rb') as f:
                await msg.delete()
                await update.message.reply_document(document=f, filename=os.path.basename(fp),
                    caption=f"✅ KỊCH BẢN THEO PHONG CÁCH ĐỐI THỦ · {len(kb)} chữ")
            await update.message.reply_text("✅ Xong!", reply_markup=menu_chinh_keyboard())
        else:
            await msg.edit_text(
                f"✅ Đã lấy phụ đề từ video ({len(kich_ban_mau)} ký tự)!\n\n"
                "📝 Bây giờ gửi chủ đề bạn muốn viết (tin nhắn bình thường)"
            )
            user_data[user_id]['_mode'] = 'doi_thu_cho_chu_de'
    except ImportError:
        await msg.edit_text(
            "❌ Thiếu thư viện!\npip install youtube-transcript-api\nRồi restart bot."
        )
    except Exception as e:
        await msg.edit_text(
            f"❌ Không lấy được phụ đề: {str(e)[:100]}\n\n"
            "💡 Thay thế: Gửi file .txt kịch bản đối thủ, rồi vào menu → Dùng phong cách đối thủ"
        )

async def chon_tieu_de_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    raw = user_data[user_id].get('tieu_de_raw')
    if not raw:
        await update.message.reply_text("❌ Chưa có danh sách tiêu đề. Chạy Module 2 trước!")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📌 Tiêu đề #{i}", callback_data=f"td_{i}")] for i in range(1,6)
    ] + [[InlineKeyboardButton("⏭️ Bỏ qua", callback_data="td_skip")]])
    fp = tao_file_txt(raw, f"tieu_de_xem_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(fp, 'rb') as f:
        await update.message.reply_document(document=f, filename=os.path.basename(fp),
            caption="📊 Xem lại 5 tiêu đề:")
    await update.message.reply_text("Chọn tiêu đề muốn dùng:", reply_markup=keyboard)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_user(user_id)
    for key in ['kich_ban', 'tieu_de', 'seo', 'thumbnail', 'prompt_anh', '_mode']:
        user_data[user_id][key] = None
    await update.message.reply_text("✅ Đã reset phiên làm việc (giữ nội dung gốc).", reply_markup=menu_chinh_keyboard())

# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════

def main():
    print("=" * 50)
    print("🚀 TIỆM TRUYỆN NHỎ NHỎ – v2.0")
    print("=" * 50)
    print("✅ 5 Module sản xuất")
    print("✅ Pipeline tự động 1→5")
    print("✅ Checklist sản xuất")
    print("✅ Lịch đăng video")
    print("✅ Phân tích đối thủ")
    print("=" * 50)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("sua", sua_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("checklist", checklist_command))
    app.add_handler(CommandHandler("lich", lich_command))
    app.add_handler(CommandHandler("doi_thu", doi_thu_command))
    app.add_handler(CommandHandler("chon_tieu_de", chon_tieu_de_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("✅ Bot sẵn sàng!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
