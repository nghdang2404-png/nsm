def is_bac_lieu(khu_vuc):
    """Kiểm tra xem khu vực người dùng có thuộc Bạc Liêu hay không (hỗ trợ có dấu và không dấu)."""
    kv = (khu_vuc or '').lower()
    return 'bạc liêu' in kv or 'bac lieu' in kv

def lay_gia_theo_vung(xe, khu_vuc_user):
    """
    Trích xuất giá hiển thị và giá làm giấy tờ (phường/xã) của xe
    dựa theo khu vực làm việc của người dùng (Bạc Liêu hoặc Cà Mau).
    """
    if is_bac_lieu(khu_vuc_user):
        return {
            'gia_hien_thi': getattr(xe, 'gia_bl_cao', 0) or 0,
            'gia_gt_phuong': getattr(xe, 'gia_gt_phuong_bl', 0) or 0,
            'gia_gt_xa': getattr(xe, 'gia_gt_xa_bl', 0) or 0,
            'gia_thap': getattr(xe, 'gia_bl_thap', 0) or 0,
            'gia_trung': getattr(xe, 'gia_bl_trung', 0) or 0,
            'gia_cao': getattr(xe, 'gia_bl_cao', 0) or 0
        }
    else:
        return {
            'gia_hien_thi': getattr(xe, 'gia_cm_cao', 0) or 0,
            'gia_gt_phuong': getattr(xe, 'gia_gt_phuong_cm', 0) or 0,
            'gia_gt_xa': getattr(xe, 'gia_gt_xa_cm', 0) or 0,
            'gia_thap': getattr(xe, 'gia_cm_thap', 0) or 0,
            'gia_trung': getattr(xe, 'gia_cm_trung', 0) or 0,
            'gia_cao': getattr(xe, 'gia_cm_cao', 0) or 0
        }

def format_xe_data_home(xe, khu_vuc_user):
    """
    Đóng gói dữ liệu đối tượng Xe thành Dictionary 
    để chuẩn bị hiển thị ra giao diện home.html.
    """
    gia_info = lay_gia_theo_vung(xe, khu_vuc_user)
    
    return {
        'loai_xe': xe.loai_xe,
        'ten_xe': xe.ten_xe,
        'phien_ban': xe.phien_ban,
        'gia_hien_thi': gia_info['gia_hien_thi'],
        'gia_giay_to_phuong': gia_info['gia_gt_phuong'],
        'gia_giay_to_xa': gia_info['gia_gt_xa'], 
        'gia_thap': gia_info['gia_thap'],
        'gia_trung': gia_info['gia_trung'],
        'gia_cao': gia_info['gia_cao'],
        'ns1': getattr(xe, 'ns1', 0) or 0, 
        'ns2': getattr(xe, 'ns2', 0) or 0,
        'ns3': getattr(xe, 'ns3', 0) or 0, 
        'ns4': getattr(xe, 'ns4', 0) or 0, 
        'ns5': getattr(xe, 'ns5', 0) or 0, 
        'nsm1': getattr(xe, 'nsm1', 0) or 0,
        'hinh_anh': xe.hinh_anh,
        'mau_xe': [m.to_dict(khu_vuc_user=khu_vuc_user) for m in xe.mau_xe]
    }