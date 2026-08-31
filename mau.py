import pandas as pd
import psycopg2

# 1. Kết nối database Neon
DATABASE_URL = "postgresql://neondb_owner:npg_knMXRhS06HbT@ep-fancy-block-az7pz4uf.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&connect_timeout=30"

# 2. Đọc file Excel
df = pd.read_excel('template_nhap_gia GIA RAI.xlsx', sheet_name=0)
regions = df.columns[1:].tolist()

# Bảng ánh xạ từ tên cột Excel sang tên khu vực nhỏ trong CSDL của NSM1
excel_to_db_region = {
    'PHƯỜNG BẠC LIÊU- VĨNH TRẠCH- HIỆP THÀNH': 'Phường Bạc Liêu, Vĩnh Trạch, Hiệp Thành',
    'HÒA BÌNH- VĨNH LỢI': 'Hoà Bình, Vĩnh Lợi',
    'PHƯỚC LONG': 'Phước Long',
    'ĐÔNG HẢI': 'Đông Hải',
    'GIÁ RAI': 'Giá Rai',
    'HỒNG DÂN': 'Hồng Dân',
    'SÓC TRĂNG - CẦN THƠ': 'Sóc Trăng, Cần Thơ'
}

# 3. Chuẩn bị kết nối
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Câu lệnh SQL Upsert cho NSM1
query = """
    INSERT INTO gia_giay_to_xe_bl (xe_id, khu_vuc_nho_id, gia)
    SELECT x.id, kn.id, %s
    FROM xe x, khu_vuc_nho_bl kn, khu_vuc_lon_bl kl
    WHERE x.ten_xe = %s AND kn.ten_khu_vuc_nho = %s 
      AND kl.id = kn.khu_vuc_lon_id AND kl.ma_khu_vuc = 'NSM1'
    ON CONFLICT (xe_id, khu_vuc_nho_id) DO UPDATE SET gia = EXCLUDED.gia;
"""

success_count = 0
not_found_count = 0

# 4. Duyệt qua từng dòng trong Excel và đẩy lên DB
for _, row in df.iterrows():
    ten_xe = row['ten_xe']
    for reg in regions:
        gia = row[reg]
        if pd.notna(gia):
            # Lấy tên khu vực tương ứng trong DB từ bảng ánh xạ
            db_region_name = excel_to_db_region.get(reg, reg)
            
            cur.execute(query, (float(gia), ten_xe, db_region_name))
            
            if cur.rowcount > 0:
                success_count += 1
            else:
                not_found_count += 1
                print(f"⚠️ Không tìm thấy xe hoặc khu vực khớp: Xe='{ten_xe}', Khu vực DB='{db_region_name}'")

conn.commit()
cur.close()
conn.close()

print(f"\n🎉 Hoàn tất! Đã cập nhật thành công {success_count} bản ghi cho NSM1.")
if not_found_count > 0:
    print(f"⚠️ Có {not_found_count} bản ghi không khớp. Hãy kiểm tra lại tên xe trong CSDL.")