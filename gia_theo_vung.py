def is_bac_lieu(khu_vuc):

    kv = (khu_vuc or '').lower()
    return 'bạc liêu' in kv or 'bac lieu' in kv

def lay_gia_theo_vung(xe, khu_vuc_user):

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

def lay_gia_giay_to_khu_vuc_nho_bl(xe_id):

    from app import KhuVucLonBL, GiaGiayToXeBL

    ds_gia = {g.khu_vuc_nho_id: (g.gia or 0) for g in GiaGiayToXeBL.query.filter_by(xe_id=xe_id).all()}
    ds_khu_vuc_lon = KhuVucLonBL.query.order_by(KhuVucLonBL.thu_tu).all()

    ket_qua = []
    for kvl in ds_khu_vuc_lon:
        ket_qua.append({
            'khu_vuc_lon_id': kvl.id,
            'ma_khu_vuc': kvl.ma_khu_vuc,
            'ten_khu_vuc_lon': kvl.ten_khu_vuc,
            'khu_vuc_nho': [
                {
                    'id': kvn.id,
                    'ten_khu_vuc_nho': kvn.ten_khu_vuc_nho,
                    'gia': ds_gia.get(kvn.id, 0)
                } for kvn in sorted(kvl.khu_vuc_nho, key=lambda x: x.thu_tu)
            ]
        })
    return ket_qua

def format_xe_data_home(xe, khu_vuc_user):

    gia_info = lay_gia_theo_vung(xe, khu_vuc_user)
    is_bl = is_bac_lieu(khu_vuc_user)

    return {
        'loai_xe': xe.loai_xe,
        'ten_xe': xe.ten_xe,
        'phien_ban': xe.phien_ban,
        'gia_hien_thi': gia_info['gia_hien_thi'],
        'gia_giay_to_phuong': gia_info['gia_gt_phuong'] if not is_bl else None,
        'gia_giay_to_xa': gia_info['gia_gt_xa'] if not is_bl else None,
        'gia_giay_to_khu_vuc_nho_bl': lay_gia_giay_to_khu_vuc_nho_bl(xe.id) if is_bl else [],
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