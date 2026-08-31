import pandas as pd
import psycopg2

# 1. Kết nối database Neon
DATABASE_URL = "postgresql://neondb_owner:npg_knMXRhS06HbT@ep-fancy-block-az7pz4uf.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&connect_timeout=30"

# 2. Đọc file Excel template
file_path = 'template_nhap_gia GIA RAI.xlsx'
df = pd.read_excel(file_path)

# Tên cột khu vực trong Excel cần nạp
target_excel_col = 'Sóc Trăng, TP Cần Thơ'

# Tên tương ứng trong CSDL (bạn có thể điều chỉnh nếu trong DB lưu là 'Sóc Trăng, Cần Thơ')
db_region_name = 'Sóc Trăng cũ, TP Cần Thơ' 
# Hoặc nếu trong DB bạn muốn lưu chuẩn là 'Sóc Trăng, Cần Thơ', hãy đổi biến trên thành 'Sóc Trăng, Cần Thơ'

# 3. Kết nối CSDL và thực thi cập nhật
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

success_count = 0
not_found_col_count = 0
new_xe_count = 0

# Kiểm tra xem cột có tồn tại trong file Excel không
if target_excel_col not in df.columns:
    print(f"❌ Lỗi: Không tìm thấy cột '{target_excel_col}' trong file Excel!")
else:
    for _, row in df.iterrows():
        ten_xe = str(row['ten_xe']).strip()
        if not ten_xe or pd.isna(ten_xe) or ten_xe == 'nan':
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
        if pd.notna(gia) and str(gia).strip() != '' and float(gia) > 0:
            
            # Lấy id khu vực nhỏ thuộc NS2
            query_region_id = """
                SELECT kn.id 
                FROM khu_vuc_nho_bl kn
                JOIN khu_vuc_lon_bl kl ON kl.id = kn.khu_vuc_lon_id
                WHERE kl.ma_khu_vuc = 'NS2' AND (kn.ten_khu_vuc_nho = %s OR kn.ten_khu_vuc_nho = 'Sóc Trăng, Cần Thơ')
            """
            cur.execute(query_region_id, (db_region_name,))
            reg_row = cur.fetchone()
            
            if reg_row:
                khu_vuc_nho_id = reg_row[0]
                
                # Upsert giá vào bảng gia_giay_to_xe_bl
                upsert_query = """
                    INSERT INTO gia_giay_to_xe_bl (xe_id, khu_vuc_nho_id, gia)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (xe_id, khu_vuc_nho_id) 
                    DO UPDATE SET gia = EXCLUDED.gia;
                """
                cur.execute(upsert_query, (xe_id, khu_vuc_nho_id, float(gia)))
                success_count += 1
            else:
                not_found_col_count += 1
                print(f"⚠️ Cảnh báo: Không tìm thấy vùng nhỏ cho 'Sóc Trăng' trong CSDL thuộc khu vực NS2.")

conn.commit()
cur.close()
conn.close()

print(f"\n🎉 Cập nhật giá Sóc Trăng, TP Cần Thơ cho NS2 hoàn tất!")
print(f"- Tổng số bản ghi giá đã cập nhật: {success_count}")
print(f"- Số xe mới được thêm vào DB: {new_xe_count}")
if not_found_col_count > 0:
    print(f"- Số cảnh báo không tìm thấy vùng trong DB: {not_found_col_count}")