import pandas as pd
import psycopg2

# 1. Kết nối database Neon
DATABASE_URL = "postgresql://neondb_owner:npg_knMXRhS06HbT@ep-fancy-block-az7pz4uf.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&connect_timeout=30"

# 2. Đọc file Excel
df = pd.read_excel('template_nhap_gia GIA RAI.xlsx', sheet_name=0)
excel_regions = df.columns[1:].tolist()
excel_xe = df['ten_xe'].unique().tolist()

# 3. Kết nối DB để lấy danh sách thực tế
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Lấy danh sách tên xe trong DB
cur.execute("SELECT ten_xe FROM xe;")
db_xe = set(row[0] for row in cur.fetchall())

# Lấy danh sách khu vực nhỏ trong DB thuộc NSM1
cur.execute("""
    SELECT kn.ten_khu_vuc_nho 
    FROM khu_vuc_nho_bl kn 
    JOIN khu_vuc_lon_bl kl ON kl.id = kn.khu_vuc_lon_id 
    WHERE kl.ma_khu_vuc = 'NSM1';
""")
db_regions = set(row[0] for row in cur.fetchall())

cur.close()
conn.close()

# 4. Kiểm tra và báo cáo
print("================ CHẨN ĐOÁN DỮ LIỆU ================")
print(f" Tổng số xe trong Excel: {len(excel_xe)}")
print(f" Tổng số khu vực trong Excel: {len(excel_regions)}")
print(f" Tổng số xe trong DB: {len(db_xe)}")
print(f" Tổng số khu vực NSM1 trong DB: {len(db_regions)}")

print("\n--- KIỂM TRA KHU VỰC (Cột trong Excel vs DB) ---")
for reg in excel_regions:
    if reg not in db_regions:
        print(f"❌ Khu vực Excel: '{reg}' -> KHÔNG CÓ TRONG DB cho NSM1")
    else:
        print(f"✅ Khu vực: '{reg}' khớp.")

print("\n--- KIỂM TRA TÊN XE (Excel vs DB) ---")
missing_xe_count = 0
for x in excel_xe:
    if x not in db_xe:
        missing_xe_count += 1
        print(f"❌ Xe Excel: '{x}' -> KHÔNG CÓ TRONG DB")

print(f"\n👉 Tổng số tên xe không khớp: {missing_xe_count}/{len(excel_xe)}")
print("==================================================")