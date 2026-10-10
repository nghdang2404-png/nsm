"""
Chức năng TÍNH GÓP XE (Jacss / FE) cho app Nam Sương.

Cách gắn vào app.py (thêm 2 dòng, đặt SAU khi đã khai báo app, db, Setting, admin_required,
ví dụ ngay trước dòng `if __name__ == "__main__":`):

    from tinh_gop import dang_ky_tinh_gop
    dang_ky_tinh_gop(app, db, Setting, admin_required)

Cấu hình lãi suất lưu trong bảng Setting (key = 'tinh_gop_config', dạng JSON) nên admin sửa được
ở trang /admin/tinh-gop mà không cần sửa code. Chưa có cấu hình -> dùng DEFAULT_CONFIG bên dưới.

Công thức (đúng như file Excel "BẢNG TÍNH GÓP"): lãi phẳng trên dư nợ gốc ban đầu
    khoản vay      = giá xe - trả trước
    góp mỗi tháng  = (khoản vay x lãi%/tháng x số tháng + khoản vay) / số tháng
Phần tính nằm ở trình duyệt (tinh_gop.html) nên không tốn request mỗi lần gõ số.
"""
import json
import re
import unicodedata

from flask import jsonify, render_template, request, session
from sqlalchemy import text

KEY_CONFIG = 'tinh_gop_config'

# Lãi suất tính theo %/tháng. "lai" là danh sách lựa chọn, phần tử ĐẦU TIÊN là mặc định.
DEFAULT_CONFIG = {
    "jacss": {
        "ten": "Jacss",
        "min_tra_truoc": 0,  # % trả trước tối thiểu (0 = không cảnh báo). Sửa ở trang admin.
        "ky_han": [
            {"thang": 6,  "lai": [0.99]},
            {"thang": 9,  "lai": [0.99, 0.79]},
            {"thang": 12, "lai": [0.79]},
            {"thang": 15, "lai": [0.79, 0.69]},
            {"thang": 18, "lai": [0.69]},
            {"thang": 24, "lai": [0.69]},
            {"thang": 36, "lai": [0.69]},
        ],
    },
    # FE: lấy theo file Excel 2503_BẢNG_TÍNH_GÓP.xlsx. Mỗi dòng xe có lãi mặc định và kỳ hạn tối đa.
    "fe": {
        "ten": "FE",
        "min_tra_truoc": 10,
        "lai_tuy_chon": [0.79, 0.99, 1.19, 1.35],
        "ky_han": [6, 9, 12, 15, 18, 24, 36],
        "xe": [
            {"ten": "Wave Alpha",   "match": ["wavealpha"],            "loai_tru": [],          "lai": 0.79, "toi_da": 36},
            {"ten": "Blade",        "match": ["blade"],                "loai_tru": ["airblade"], "lai": 1.19, "toi_da": 15},
            {"ten": "Wave RSX",     "match": ["waversx"],              "loai_tru": [],          "lai": 1.19, "toi_da": 15},
            {"ten": "Future",       "match": ["future"],               "loai_tru": [],          "lai": 0.79, "toi_da": 24},
            {"ten": "Vision",       "match": ["vision"],               "loai_tru": [],          "lai": 0.79, "toi_da": 24},
            {"ten": "Air Blade 125","match": ["airblade125"],          "loai_tru": [],          "lai": 0.79, "toi_da": 24},
            {"ten": "Air Blade 150","match": ["airblade150"],          "loai_tru": [],          "lai": 1.19, "toi_da": 24},
            {"ten": "Lead",         "match": ["lead"],                 "loai_tru": [],          "lai": 0.79, "toi_da": 24},
            {"ten": "SH Mode",      "match": ["shmode"],               "loai_tru": [],          "lai": 1.19, "toi_da": 24},
            {"ten": "SH125",        "match": ["sh125"],                "loai_tru": [],          "lai": 1.19, "toi_da": 24},
            {"ten": "SH150",        "match": ["sh150"],                "loai_tru": [],          "lai": 1.19, "toi_da": 24},
            {"ten": "Winner X",     "match": ["winnerx"],              "loai_tru": [],          "lai": 0.79, "toi_da": 24},
            {"ten": "Super Cub",    "match": ["supercub", "suppercub"], "loai_tru": [],         "lai": 0.79, "toi_da": 12},
            {"ten": "CBR150",       "match": ["cbr150"],               "loai_tru": [],          "lai": 0.79, "toi_da": 24},
            {"ten": "Rebel 300",    "match": ["rebel300"],             "loai_tru": [],          "lai": 0.79, "toi_da": 24},
        ],
    },
}


def _so(v, default=0.0):
    try:
        if isinstance(v, str):
            v = v.strip().replace(',', '.')
        return float(v)
    except (TypeError, ValueError):
        return default


def _chuan_hoa_khoa(s):
    s = unicodedata.normalize('NFC', str(s or '')).lower()
    return re.sub(r'[\s\-_.]+', '', s)


def _lam_sach(cfg):
    """Kiểm tra + chuẩn hoá cấu hình admin gửi lên. Ném ValueError nếu dữ liệu sai."""
    if not isinstance(cfg, dict):
        raise ValueError("Dữ liệu không hợp lệ.")

    # --- Jacss ---
    j = cfg.get('jacss') or {}
    ky_han_j, da_co = [], set()
    for r in j.get('ky_han', []):
        thang = int(_so(r.get('thang')))
        lai = [round(_so(x), 4) for x in (r.get('lai') or []) if _so(x, -1) >= 0]
        if thang <= 0 or thang > 120:
            raise ValueError(f"Số tháng không hợp lệ: {r.get('thang')}")
        if not lai:
            raise ValueError(f"Kỳ hạn {thang} tháng (Jacss) chưa có lãi suất.")
        if any(x > 10 for x in lai):
            raise ValueError(f"Lãi suất kỳ hạn {thang} tháng (Jacss) quá lớn (>10%/tháng), kiểm tra lại.")
        if thang in da_co:
            raise ValueError(f"Kỳ hạn {thang} tháng (Jacss) bị trùng.")
        da_co.add(thang)
        ky_han_j.append({"thang": thang, "lai": lai})
    if not ky_han_j:
        raise ValueError("Jacss cần ít nhất 1 kỳ hạn.")
    ky_han_j.sort(key=lambda x: x['thang'])

    # --- FE ---
    f = cfg.get('fe') or {}
    lai_tc = sorted({round(_so(x), 4) for x in f.get('lai_tuy_chon', []) if 0 <= _so(x, -1) <= 10})
    if not lai_tc:
        raise ValueError("FE cần ít nhất 1 mức lãi suất tuỳ chọn.")
    ky_han_f = sorted({int(_so(x)) for x in f.get('ky_han', []) if 0 < _so(x) <= 120})
    if not ky_han_f:
        raise ValueError("FE cần ít nhất 1 kỳ hạn.")
    xe_f = []
    for x in f.get('xe', []):
        ten = str(x.get('ten') or '').strip()
        match = [_chuan_hoa_khoa(m) for m in (x.get('match') or []) if _chuan_hoa_khoa(m)]
        if not ten:
            continue
        if not match:
            match = [_chuan_hoa_khoa(ten)]
        xe_f.append({
            "ten": ten,
            "match": match,
            "loai_tru": [_chuan_hoa_khoa(m) for m in (x.get('loai_tru') or []) if _chuan_hoa_khoa(m)],
            "lai": round(_so(x.get('lai')), 4),
            "toi_da": int(_so(x.get('toi_da'), ky_han_f[-1])) or ky_han_f[-1],
        })

    def pct(v, default):
        p = _so(v, default)
        return min(max(p, 0), 90)

    return {
        "jacss": {"ten": "Jacss", "min_tra_truoc": pct(j.get('min_tra_truoc'), 0), "ky_han": ky_han_j},
        "fe": {"ten": "FE", "min_tra_truoc": pct(f.get('min_tra_truoc'), 10),
               "lai_tuy_chon": lai_tc, "ky_han": ky_han_f, "xe": xe_f},
    }


def dang_ky_tinh_gop(app, db, Setting, admin_required):
    def doc_config():
        try:
            s = Setting.query.filter_by(key=KEY_CONFIG).first()
            if s and s.value:
                return _lam_sach(json.loads(s.value))
        except Exception as e:  # cấu hình hỏng -> dùng mặc định, không làm sập trang
            print("Lỗi đọc cấu hình tính góp:", e)
        return DEFAULT_CONFIG

    @app.route('/api/tinh-gop-config')
    def api_tinh_gop_config():
        if 'username' not in session:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập."}), 401
        return jsonify({"success": True, "config": doc_config()})

    @app.route('/admin/tinh-gop')
    @admin_required
    def admin_tinh_gop_page():
        return render_template('admin_tinh_gop.html', config=doc_config())

    @app.route('/admin/api/tinh-gop-config', methods=['POST'])
    @admin_required
    def admin_luu_tinh_gop_config():
        try:
            moi = _lam_sach(request.get_json(silent=True) or {})
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400

        cu = doc_config()
        s = Setting.query.filter_by(key=KEY_CONFIG).first()
        gia_tri = json.dumps(moi, ensure_ascii=False)
        if s:
            s.value = gia_tri
        else:
            db.session.add(Setting(key=KEY_CONFIG, value=gia_tri))
        db.session.commit()

        try:  # ghi vào "Lịch sử hệ thống" như các thay đổi khác
            db.session.execute(text(
                "INSERT INTO history_logs (username, action, target_id, old_value, new_value) "
                "VALUES (:u, :a, :t, :o, :n)"),
                {"u": session.get('username'), "a": "Sửa lãi suất tính góp", "t": "tinh_gop",
                 "o": json.dumps(cu, ensure_ascii=False)[:900], "n": gia_tri[:900]})
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print("Không ghi được lịch sử tính góp:", e)
        return jsonify({"success": True, "config": moi})
