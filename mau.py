import pandas as pd
import psycopg2

# 1. Kết nối database Neon
DATABASE_URL = "postgresql://neondb_owner:npg_knMXRhS06HbT@ep-fancy-block-az7pz4uf.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&connect_timeout=30"

# 2. Đọc file Excel template
file_path = 'template_nhap_gia GIA RAI.xlsx'
df = pd.read_excel(file_path)

regions = [col for col in df.columns if col != 'ten_xe']

# 3. Kết nối CSDL
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

success_count = 0
new_xe_count = 0

for _, row in df.iterrows():
    ten_xe = str(row['ten_xe']).strip()
    if not ten_xe or pd.isna(ten_xe):
        continue

    # Kiểm tra hoặc thêm mới xe vào bảng `xe`
    cur.execute("SELECT id FROM xe WHERE ten_xe = %s", (ten_xe,))
    xe_row = cur.fetchone()
    
    if xe_row:
        xe_id = xe_row[0]
    else:
        cur.execute("INSERT INTO xe (ten_xe) VALUES (%s) RETURNING id", (ten_xe,))
        xe_id = cur.fetchone()[0]
        new_xe_count += 1
        print(f"✨ Tự động thêm xe mới: '{ten_xe}'")

    # Duyệt qua các cột khu vực trong file Excel
    for reg in regions:
        gia = row[reg]
        if pd.notna(gia) and str(gia).strip() != '' and float(gia) > 0:
            # Lấy id của khu vực nhỏ thuộc NS2 khớp chính xác với tên cột Excel
            query_region_id = """
                SELECT kn.id 
                FROM khu_vuc_nho_bl kn
                JOIN khu_vuc_lon_bl kl ON kl.id = kn.khu_vuc_lon_id
                WHERE kl.ma_khu_vuc = 'NS2' AND kn.ten_khu_vuc_nho = %s
            """
            cur.execute(query_region_id, (reg.strip(),))
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
                print(f"⚠️ Cảnh báo: Không tìm thấy vùng nhỏ '{reg}' trong CSDL cho NS2.")

conn.commit()
cur.close()
conn.close()

print(f"\n🎉 Nạp dữ liệu hoàn tất!")
print(f"- Tổng số bản ghi giá đã cập nhật: {success_count}")
print(f"- Số xe mới được thêm vào DB: {new_xe_count}")