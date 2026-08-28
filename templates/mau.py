import pandas as pd

# Cấu trúc cột khớp tuyệt đối với hàm import_excel trong app_4.py
data = {
    'ten_xe': ['Vision Tiêu chuẩn', 'Air Blade 125 Đặc biệt'],
    'loai_xe': ['Xe ga', 'Xe ga'],
    'phien_ban': ['Tiêu chuẩn', 'Đặc biệt'],
    'gia_cm_thap': [30000000, 40500000],
    'gia_cm_trung': [30700000, 41200000],
    'gia_cm_cao': [31500000, 42000000],
    'gia_bl_thap': [29500000, 40000000],
    'gia_bl_trung': [30200000, 40700000],
    'gia_bl_cao': [31000000, 41500000],
    'gia_gt_phuong_cm': [2500000, 3000000],
    'gia_gt_xa_cm': [1200000, 1500000],
    'gia_gt_phuong_bl': [2400000, 2900000],
    'gia_gt_xa_bl': [1100000, 1400000],
    'ns1': [5, 2],
    'ns2': [2, 1],
    'ns3': [0, 0],
    'ns4': [0, 0],
    'ns5': [0, 0],
    'nsm1': [1, 0],
    'ten_mau': ['Đỏ đen', 'Xanh xám mờ'],
    'chenh_lech_cm': [0, 500000],
    'chenh_lech_bl': [0, 500000]
}

df = pd.DataFrame(data)
# Xuất ra file Excel mẫu
df.to_excel('template_nhap_gia.xlsx', index=False)
print("Đã tạo thành công file: template_nhap_gia.xlsx")