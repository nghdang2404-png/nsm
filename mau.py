import os
import pandas as pd
import psycopg2

# 1. Kết nối database Supabase
# Lấy chuỗi kết nối từ biến môi trường để không lộ mật khẩu trong file.
# Supabase: Project > Connect > Session pooler (cổng 5432), dạng:
# postgresql://postgres.<project-ref>:<mat-khau>@aws-0-<region>.pooler.supabase.com:5432/postgres
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("❌ Chưa đặt biến môi trường DATABASE_URL (chuỗi kết nối Supabase).")

# 2. Đọc file Excel template
file_path = 'template_nhap_gia GIA RAI.xlsx'
df = pd.read_excel(file_path)

# Tên cột khu vực trong Excel cần nạp
target_excel_col = 'Sóc Trăng, TP Cần Thơ'

# Tên tương ứng trong CSDL (đổi thành 'Sóc Trăng, Cần Thơ' nếu DB lưu tên này)
db_region_name = 'Sóc Trăng cũ, TP Cần Thơ'

# Kiểm tra cột trước khi mở kết nối
if target_excel_col not in df.columns:
    raise SystemExit(f"❌ Lỗi: Không tìm thấy cột '{target_excel_col}' trong file Excel!")
if 'ten_xe' not in df.columns:
    raise SystemExit("❌ Lỗi: Không tìm thấy cột 'ten_xe' trong file Excel!")

# 3. Kết nối CSDL và thực thi cập nhật
conn = psycopg2.connect(DATABASE_URL, connect_timeout=30, sslmode="require")
cur = conn.cursor()

success_count = 0
not_found_col_count = 0
new_xe_count = 0

try:
    # Lấy id khu vực nhỏ thuộc NS2 một lần duy nhất (không cần truy vấn lặp lại cho từng xe)
    query_region_id = """
        SELECT kn.id
        FROM khu_vuc_nho_bl kn
        JOIN khu_vuc_lon_bl kl ON kl.id = kn.khu_vuc_lon_id
        WHERE kl.ma_khu_vuc = 'NS2'
          AND (kn.ten_khu_vuc_nho = %s OR kn.ten_khu_vuc_nho = 'Sóc Trăng, Cần Thơ')
    """
    cur.execute(query_region_id, (db_region_name,))
    reg_row = cur.fetchone()
    khu_vuc_nho_id = reg_row[0] if reg_row else None

    if khu_vuc_nho_id is None:
        print("⚠️ Cảnh báo: Không tìm thấy vùng nhỏ cho 'Sóc Trăng' trong CSDL thuộc khu vực NS2.")

    upsert_query = """
        INSERT INTO gia_giay_to_xe_bl (xe_id, khu_vuc_nho_id, gia)
        VALUES (%s, %s, %s)
        ON CONFLICT (xe_id, khu_vuc_nho_id)
        DO UPDATE SET gia = EXCLUDED.gia;
    """

    for _, row in df.iterrows():
        raw_name = row['ten_xe']
        if pd.isna(raw_name):
            continue
        ten_xe = str(raw_name).strip()
        if not ten_xe or ten_xe.lower() == 'nan':
            continue

        # Kiểm tra hoặc tự động thêm xe mới vào bảng `xe`
        cur.execute("SELECT id FROM xe WHERE ten_xe = %s", (ten_xe,))
        xe_row = cur.fetchone()

        if xe_row:
            xe_id = xe_row[0]
        else:
            cur.execute("INSERT INTO xe (ten_xe) VALUES (%s) RETURNING id", (ten_xe,))
            xe_id = cur.fetchone()[0]
            new_xe_count += 1
            print(f"✨ Tự động thêm xe mới: '{ten_xe}'")

        # Lấy giá trị của cột Sóc Trăng, TP Cần Thơ
        gia = row[target_excel_col]
        if pd.notna(gia) and str(gia).strip() != '':
            try:
                gia_so = float(gia)
            except (TypeError, ValueError):
                print(f"⚠️ Bỏ qua '{ten_xe}': giá không hợp lệ ({gia!r})")
                continue

            if gia_so > 0:
                if khu_vuc_nho_id is not None:
                    cur.execute(upsert_query, (xe_id, khu_vuc_nho_id, gia_so))
                    success_count += 1
                else:
                    not_found_col_count += 1

    conn.commit()

except Exception as e:
    conn.rollback()
    print(f"❌ Có lỗi, đã hoàn tác toàn bộ thay đổi: {e}")
    raise
finally:
    cur.close()
    conn.close()

print(f"\n🎉 Cập nhật giá Sóc Trăng, TP Cần Thơ cho NS2 hoàn tất!")
print(f"- Tổng số bản ghi giá đã cập nhật: {success_count}")
print(f"- Số xe mới được thêm vào DB: {new_xe_count}")
if not_found_col_count > 0:
    print(f"- Số bản ghi bị bỏ qua vì không tìm thấy vùng trong DB: {not_found_col_count}")