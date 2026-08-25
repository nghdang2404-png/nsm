import os
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# --- CẤU HÌNH COOKIE ĐỂ GIỮ PHIÊN TRÊN ĐIỆN THOẠI ---
app.permanent_session_lifetime = timedelta(days=30)  # Giữ phiên đăng nhập trong 30 ngày
app.config['SESSION_COOKIE_NAME'] = 'namsuong_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_knMXRhS06HbT@ep-fancy-block-az7pz4uf.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&connect_timeout=30'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True, 'pool_recycle': 300}

db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), default='user')
    bo_phan = db.Column(db.String(100))
    khu_vuc = db.Column(db.String(100))

class Xe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loai_xe = db.Column(db.String(50))
    ten_xe = db.Column(db.String(100), unique=True, nullable=False)
    phien_ban = db.Column(db.String(100))
    
    gia_cm_thap = db.Column(db.Float, default=0)
    gia_cm_trung = db.Column(db.Float, default=0)
    gia_cm_cao = db.Column(db.Float, default=0)
    
    gia_bl_thap = db.Column(db.Float, default=0)
    gia_bl_trung = db.Column(db.Float, default=0)
    gia_bl_cao = db.Column(db.Float, default=0)

    gia_gt_phuong_cm = db.Column(db.Float, default=0)
    gia_gt_xa_cm = db.Column(db.Float, default=0)
    gia_gt_phuong_bl = db.Column(db.Float, default=0)
    gia_gt_xa_bl = db.Column(db.Float, default=0)
    
    ns1 = db.Column(db.Integer, default=0); ns2 = db.Column(db.Integer, default=0)
    ns3 = db.Column(db.Integer, default=0); ns4 = db.Column(db.Integer, default=0)
    ns5 = db.Column(db.Integer, default=0); nsm1 = db.Column(db.Integer, default=0)
    hinh_anh = db.Column(db.String(200), default='')
    mau_xe = db.relationship('XeMau', backref='xe', cascade='all, delete-orphan')

class XeMau(db.Model):
    __tablename__ = 'xe_mau'
    id = db.Column(db.Integer, primary_key=True)
    xe_id = db.Column(db.Integer, db.ForeignKey('xe.id'), nullable=False)
    ten_mau = db.Column(db.String(50), nullable=False)
    chenh_lech_cm = db.Column(db.Float, default=0)
    chenh_lech_bl = db.Column(db.Float, default=0)
    hinh_anh_mau = db.Column(db.String(200), default='')

    # --- ĐÃ BỔ SUNG CÁC CỘT TỒN KHO CHO TỪNG MÀU ---
    ns1 = db.Column(db.Integer, default=0)
    ns2 = db.Column(db.Integer, default=0)
    ns3 = db.Column(db.Integer, default=0)
    ns4 = db.Column(db.Integer, default=0)
    ns5 = db.Column(db.Integer, default=0)
    nsm1 = db.Column(db.Integer, default=0)

    def to_dict(self, khu_vuc_user=None):
        is_bl = 'bạc liêu' in (khu_vuc_user or '').lower()
        chenh_lech_vung = self.chenh_lech_bl if is_bl else self.chenh_lech_cm
        return {
            'ten_mau': self.ten_mau, 
            'chenh_lech_gia': chenh_lech_vung,
            'ds_ma_mau': lay_danh_sach_ma_mau(self.ten_mau),
            'hinh_anh_mau': self.hinh_anh_mau,
            # --- ĐÃ TRUYỀN DỮ LIỆU TỒN KHO SANG JAVASCRIPT GIAO DIỆN ---
            'ns1': self.ns1 or 0,
            'ns2': self.ns2 or 0,
            'ns3': self.ns3 or 0,
            'ns4': self.ns4 or 0,
            'ns5': self.ns5 or 0,
            'nsm1': self.nsm1 or 0
        }

# --- HELPER FUNCTIONS & DECORATORS ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session.get('role') != 'admin':
            flash("Bạn không có quyền truy cập trang quản trị!", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def save_image(file):
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename
    return ''

def lay_danh_sach_ma_mau(ten_mau):
    if not ten_mau: return ['#cccccc']
    bang_mau = {
        'đỏ': '#ff0000', 'do': '#ff0000',
        'đen': '#000000', 'den': '#000000', 'đen nhám': '#222222', 'den nham': '#222222', 'nhám': '#222222', 'nham': '#222222',
        'trắng': '#ffffff', 'trang': '#ffffff', 'trắng ngọc': '#f8f9fa', 'trang ngoc': '#f8f9fa', 'ngọc': '#f8f9fa', 'ngoc': '#f8f9fa',
        'xanh': '#0000ff', 'xanh dương': '#0056b3', 'xanh duong': '#0056b3', 'xanh đậm': '#001f3f', 'xanh dam': '#001f3f', 'đậm': '#001f3f', 'dam': '#001f3f',
        'bạc': '#c0c0c0', 'bac': '#c0c0c0', 'xám': '#808080', 'xam': '#808080', 'xám xi măng': '#6c757d', 'xam xi mang': '#6c757d', 'xi': '#6c757d', 'măng': '#6c757d',
        'vàng': '#ffc107', 'vang': '#ffc107', 'cam': '#fd7e14', 'hồng': '#e83e8c', 'hong': '#e83e8c', 'xám mờ': '#555555'
    }
    text = ten_mau.lower().strip()
    danh_sach_kq = []
    for tu_khoa, ma in sorted(bang_mau.items(), key=lambda x: len(x[0]), reverse=True):
        if tu_khoa in text and len(tu_khoa.split()) > 1:
            if ma not in danh_sach_kq: danh_sach_kq.append(ma)
            text = text.replace(tu_khoa, ' ')
    tu_list = text.split()
    for tu in tu_list:
        if tu in bang_mau:
            ma_hex = bang_mau[tu]
            if ma_hex not in danh_sach_kq: danh_sach_kq.append(ma_hex)
        elif tu.startswith('#'):
            if tu not in danh_sach_kq: danh_sach_kq.append(tu)
    return danh_sach_kq if danh_sach_kq else ['#cccccc']

def safe_float(val, default=0.0):
    try:
        if pd.isna(val): return default
        if isinstance(val, (int, float)): return float(val)
        s = str(val).replace('.', '').replace(',', '').strip()
        return float(s) if s else default
    except Exception:
        return default

def safe_int(val, default=0):
    try:
        if pd.isna(val): return default
        if isinstance(val, (int, float)): return int(val)
        s = str(val).replace('.', '').replace(',', '').strip()
        return int(float(s)) if s else default
    except Exception:
        return default

# --- ROUTES AUTH & USER ---
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username")).first()
        if user and check_password_hash(user.password, request.form.get("password")):
            session.clear()
            session.permanent = True 
            session['username'] = user.username
            session['role'] = user.role
            session['vung'] = user.khu_vuc or 'Cà Mau'
            return redirect(url_for('home'))
        flash("Sai thông tin đăng nhập!", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/home")
def home():
    if 'username' not in session: return redirect(url_for('login'))
    
    current_user = User.query.filter_by(username=session['username']).first()
    khu_vuc_user = (current_user.khu_vuc or session.get('vung', 'Cà Mau')).strip()
    
    search_query = request.args.get('search', '')
    loai_filter = request.args.get('loai', '')
    
    query = Xe.query
    if search_query:
        query = query.filter((Xe.ten_xe.ilike(f'%{search_query}%')) | (Xe.phien_ban.ilike(f'%{search_query}%')))
    if loai_filter:
        query = query.filter_by(loai_xe=loai_filter)
        
    danh_sach_xe = query.order_by(Xe.loai_xe.asc(), Xe.ten_xe.asc()).all()
    danh_sach_loai = [l[0] for l in db.session.query(Xe.loai_xe).distinct().all() if l[0]]
    data = [format_xe_data_home(xe, khu_vuc_user) for xe in danh_sach_xe]
        
    return render_template(
        "home.html", 
        danh_sach_xe=data, 
        search_query=search_query, 
        loai_filter=loai_filter, 
        danh_sach_loai=danh_sach_loai, 
        username=session.get('username'),
        user_vung=khu_vuc_user
    )

# --- ADMIN ROUTES ---
@app.route("/admin")
@admin_required
def admin_panel():
    search_query = request.args.get('search', '')
    loai_filter = request.args.get('loai', '')
    
    query = Xe.query
    if search_query:
        query = query.filter((Xe.ten_xe.ilike(f'%{search_query}%')) | (Xe.phien_ban.ilike(f'%{search_query}%')))
    if loai_filter:
        query = query.filter_by(loai_xe=loai_filter)
        
    danh_sach_xe = query.order_by(Xe.id.desc()).all()
    danh_sach_loai = [l[0] for l in db.session.query(Xe.loai_xe).distinct().all() if l[0]]
    
    return render_template("admin.html", danh_sach_xe=danh_sach_xe, search_query=search_query, loai_filter=loai_filter, danh_sach_loai=danh_sach_loai, username=session.get('username'))

@app.route("/admin/users")
@admin_required
def manage_users():
    users = User.query.all()
    return render_template("manage_users.html", users=users, username=session.get('username'))

@app.route("/register", methods=["GET", "POST"])
@app.route("/admin/register", methods=["GET", "POST"])
@admin_required
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        bo_phan = request.form.get("bo_phan", "")
        khu_vuc = request.form.get("khu_vuc", "Cà Mau")
        
        is_admin = request.form.get("is_admin")
        role = "admin" if is_admin == "yes" else request.form.get("role", "user")

        if confirm_password and password != confirm_password:
            flash("Mật khẩu xác nhận không trùng khớp!", "danger")
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash(f"Tài khoản '{username}' đã tồn tại!", "danger")
            return redirect(url_for('register'))

        new_user = User(
            username=username, 
            password=generate_password_hash(password), 
            role=role, 
            bo_phan=bo_phan, 
            khu_vuc=khu_vuc
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash("Tạo tài khoản người dùng thành công!", "success")
        return redirect(url_for('manage_users'))
        
    return render_template("register.html", username=session.get('username'))

@app.route("/admin/users/edit/<int:id>", methods=["POST"])
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    new_password = request.form.get("password")
    if new_password:
        user.password = generate_password_hash(new_password)
        
    user.bo_phan = request.form.get("bo_phan")
    user.khu_vuc = request.form.get("khu_vuc")
    user.role = 'admin' if request.form.get("is_admin") == 'yes' else 'user'
    
    db.session.commit()
    flash(f"Cập nhật tài khoản {user.username} thành công!", "success")
    return redirect(url_for('manage_users'))

@app.route("/admin/users/delete/<int:id>")
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.username == session.get('username'):
        flash("Không thể xóa tài khoản của chính bạn!", "danger")
        return redirect(url_for('manage_users'))
        
    db.session.delete(user)
    db.session.commit()
    flash("Đã xóa tài khoản thành công!", "success")
    return redirect(url_for('manage_users'))

# --- QUẢN LÝ XE & MÀU ---
@app.route("/admin/add", methods=["POST"])
@admin_required
def add_xe():
    ten_xe_nhap = request.form.get("ten_xe", "").strip()
    if Xe.query.filter_by(ten_xe=ten_xe_nhap).first():
        flash(f"Lỗi: Tên xe '{ten_xe_nhap}' đã tồn tại!", "danger")
        return redirect(url_for('admin_panel'))

    try:
        new_xe = Xe(
            loai_xe=request.form.get("loai_xe"), 
            ten_xe=ten_xe_nhap,
            phien_ban=request.form.get("phien_ban"), 
            
            gia_cm_thap=float(request.form.get("gia_cm_thap") or 0),
            gia_cm_trung=float(request.form.get("gia_cm_trung") or 0),
            gia_cm_cao=float(request.form.get("gia_cm_cao") or 0),
            gia_bl_thap=float(request.form.get("gia_bl_thap") or 0),
            gia_bl_trung=float(request.form.get("gia_bl_trung") or 0),
            gia_bl_cao=float(request.form.get("gia_bl_cao") or 0),
            
            gia_gt_phuong_cm=float(request.form.get("gia_gt_phuong_cm") or 0),
            gia_gt_xa_cm=float(request.form.get("gia_gt_xa_cm") or 0),
            gia_gt_phuong_bl=float(request.form.get("gia_gt_phuong_bl") or 0),
            gia_gt_xa_bl=float(request.form.get("gia_gt_xa_bl") or 0),

            ns1=int(request.form.get("ns1") or 0), ns2=int(request.form.get("ns2") or 0),
            ns3=int(request.form.get("ns3") or 0), ns4=int(request.form.get("ns4") or 0),
            ns5=int(request.form.get("ns5") or 0), nsm1=int(request.form.get("nsm1") or 0),
            hinh_anh=save_image(request.files.get('hinh_anh'))
        )
        db.session.add(new_xe)
        db.session.flush()
        
        ten_maus = request.form.getlist("ten_mau[]")
        chenh_lechs_cm = request.form.getlist("chenh_lech_cm[]")
        chenh_lechs_bl = request.form.getlist("chenh_lech_bl[]")
        anh_maus = request.files.getlist("hinh_anh_mau[]")
        
        for i in range(len(ten_maus)):
            if ten_maus[i].strip():
                c_cm = float(chenh_lechs_cm[i]) if (i < len(chenh_lechs_cm) and chenh_lechs_cm[i]) else 0
                c_bl = float(chenh_lechs_bl[i]) if (i < len(chenh_lechs_bl) and chenh_lechs_bl[i]) else 0
                db.session.add(XeMau(
                    xe_id=new_xe.id, 
                    ten_mau=ten_maus[i].strip(), 
                    chenh_lech_cm=c_cm,
                    chenh_lech_bl=c_bl,
                    hinh_anh_mau=save_image(anh_maus[i] if i < len(anh_maus) else None)
                ))
                
        db.session.commit()
        flash("Thêm xe mới thành công!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Có lỗi xảy ra: {str(e)}", "danger")

    return redirect(url_for('admin_panel'))

@app.route("/admin/edit/<int:id>", methods=["POST"])
@admin_required
def edit_xe(id):
    xe = Xe.query.get_or_404(id)
    ten_xe_moi = request.form.get("ten_xe", "").strip()
    if ten_xe_moi and ten_xe_moi != xe.ten_xe and Xe.query.filter_by(ten_xe=ten_xe_moi).first():
        flash(f"Lỗi: Tên xe '{ten_xe_moi}' đã tồn tại!", "danger")
        return redirect(url_for('admin_panel'))

    try:
        xe.loai_xe = request.form.get("loai_xe")
        xe.ten_xe = ten_xe_moi
        xe.phien_ban = request.form.get("phien_ban")
        
        xe.gia_cm_thap = float(request.form.get("gia_cm_thap") or 0)
        xe.gia_cm_trung = float(request.form.get("gia_cm_trung") or 0)
        xe.gia_cm_cao = float(request.form.get("gia_cm_cao") or 0)
        xe.gia_bl_thap = float(request.form.get("gia_bl_thap") or 0)
        xe.gia_bl_trung = float(request.form.get("gia_bl_trung") or 0)
        xe.gia_bl_cao = float(request.form.get("gia_bl_cao") or 0)

        xe.gia_gt_phuong_cm = float(request.form.get("gia_gt_phuong_cm") or 0)
        xe.gia_gt_xa_cm = float(request.form.get("gia_gt_xa_cm") or 0)
        xe.gia_gt_phuong_bl = float(request.form.get("gia_gt_phuong_bl") or 0)
        xe.gia_gt_xa_bl = float(request.form.get("gia_gt_xa_bl") or 0)

        xe.ns1 = int(request.form.get("ns1") or 0); xe.ns2 = int(request.form.get("ns2") or 0)
        xe.ns3 = int(request.form.get("ns3") or 0); xe.ns4 = int(request.form.get("ns4") or 0)
        xe.ns5 = int(request.form.get("ns5") or 0); xe.nsm1 = int(request.form.get("nsm1") or 0)
        
        if request.files.get('hinh_anh') and request.files.get('hinh_anh').filename != '':
            xe.hinh_anh = save_image(request.files.get('hinh_anh'))
        
        for mau in xe.mau_xe:
            mau.ten_mau = request.form.get(f"edit_ten_mau_{mau.id}", mau.ten_mau)
            mau.chenh_lech_cm = float(request.form.get(f"edit_chenh_lech_cm_{mau.id}") or 0)
            mau.chenh_lech_bl = float(request.form.get(f"edit_chenh_lech_bl_{mau.id}") or 0)
            if request.files.get(f"edit_hinh_anh_mau_{mau.id}") and request.files.get(f"edit_hinh_anh_mau_{mau.id}").filename != '': 
                mau.hinh_anh_mau = save_image(request.files.get(f"edit_hinh_anh_mau_{mau.id}"))
            
        new_tens = request.form.getlist("new_ten_mau[]")
        new_cms = request.form.getlist("new_chenh_lech_cm[]")
        new_bls = request.form.getlist("new_chenh_lech_bl[]")
        new_anhs = request.files.getlist("new_hinh_anh_mau[]")
        
        for i in range(len(new_tens)):
            if new_tens[i].strip():
                c_cm = float(new_cms[i]) if (i < len(new_cms) and new_cms[i]) else 0
                c_bl = float(new_bls[i]) if (i < len(new_bls) and new_bls[i]) else 0
                db.session.add(XeMau(
                    xe_id=xe.id, 
                    ten_mau=new_tens[i].strip(), 
                    chenh_lech_cm=c_cm,
                    chenh_lech_bl=c_bl,
                    hinh_anh_mau=save_image(new_anhs[i] if i < len(new_anhs) else None)
                ))

        db.session.commit()
        flash("Cập nhật thông tin xe thành công!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Có lỗi xảy ra: {str(e)}", "danger")

    return redirect(url_for('admin_panel'))

@app.route("/admin/delete/<int:id>", methods=["GET"])
@admin_required
def delete_xe(id):
    try:
        db.session.delete(Xe.query.get_or_404(id))
        db.session.commit()
        flash("Đã xóa xe thành công!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Không thể xóa xe: {str(e)}", "danger")
    return redirect(url_for('admin_panel'))

@app.route("/admin/delete-mau/<int:id>", methods=["GET"])
@admin_required
def delete_mau(id):
    try:
        db.session.delete(XeMau.query.get_or_404(id))
        db.session.commit()
        flash("Đã xóa màu thành công!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Không thể xóa màu: {str(e)}", "danger")
    return redirect(url_for('admin_panel'))

# --- IMPORT EXCEL ---
@app.route("/admin/import", methods=["POST"])
@admin_required
def import_excel():
    file = request.files.get('file_excel')
    if not file or not file.filename.endswith(('.xlsx', '.xls')):
        flash("Vui lòng chọn tập tin Excel hợp lệ (.xlsx, .xls)!", "danger")
        return redirect(url_for('admin_panel'))

    try:
        df = pd.read_excel(file).fillna(0)
        df.columns = df.columns.str.strip().str.lower()
        
        so_luong_them = 0
        so_luong_cap_nhat = 0

        for _, row in df.iterrows():
            ten_xe_excel = str(row.get('ten_xe', '')).strip()
            if not ten_xe_excel or ten_xe_excel == '0': 
                continue
            
            xe = Xe.query.filter_by(ten_xe=ten_xe_excel).first()
            
            if xe:
                if row.get('loai_xe'): xe.loai_xe = str(row.get('loai_xe')).strip()
                if row.get('phien_ban'): xe.phien_ban = str(row.get('phien_ban')).strip()
                
                xe.gia_cm_thap = safe_float(row.get('gia_cm_thap'), xe.gia_cm_thap)
                xe.gia_cm_trung = safe_float(row.get('gia_cm_trung'), xe.gia_cm_trung)
                xe.gia_cm_cao = safe_float(row.get('gia_cm_cao'), xe.gia_cm_cao)
                
                xe.gia_bl_thap = safe_float(row.get('gia_bl_thap'), xe.gia_bl_thap)
                xe.gia_bl_trung = safe_float(row.get('gia_bl_trung'), xe.gia_bl_trung)
                xe.gia_bl_cao = safe_float(row.get('gia_bl_cao'), xe.gia_bl_cao)
                
                xe.gia_gt_phuong_cm = safe_float(row.get('gia_gt_phuong_cm'), xe.gia_gt_phuong_cm)
                xe.gia_gt_xa_cm = safe_float(row.get('gia_gt_xa_cm'), xe.gia_gt_xa_cm)
                xe.gia_gt_phuong_bl = safe_float(row.get('gia_gt_phuong_bl'), xe.gia_gt_phuong_bl)
                xe.gia_gt_xa_bl = safe_float(row.get('gia_gt_xa_bl'), xe.gia_gt_xa_bl)

                xe.ns1 = safe_int(row.get('ns1'), xe.ns1)
                xe.ns2 = safe_int(row.get('ns2'), xe.ns2)
                xe.ns3 = safe_int(row.get('ns3'), xe.ns3)
                xe.ns4 = safe_int(row.get('ns4'), xe.ns4)
                xe.ns5 = safe_int(row.get('ns5'), xe.ns5)
                xe.nsm1 = safe_int(row.get('nsm1'), xe.nsm1)
                
                so_luong_cap_nhat += 1
            else:
                xe = Xe(
                    loai_xe=str(row.get('loai_xe', '')).strip(),
                    ten_xe=ten_xe_excel,
                    phien_ban=str(row.get('phien_ban', '')).strip(),
                    
                    gia_cm_thap=safe_float(row.get('gia_cm_thap')),
                    gia_cm_trung=safe_float(row.get('gia_cm_trung')),
                    gia_cm_cao=safe_float(row.get('gia_cm_cao')),
                    
                    gia_bl_thap=safe_float(row.get('gia_bl_thap')),
                    gia_bl_trung=safe_float(row.get('gia_bl_trung')),
                    gia_bl_cao=safe_float(row.get('gia_bl_cao')),
                    
                    gia_gt_phuong_cm=safe_float(row.get('gia_gt_phuong_cm')),
                    gia_gt_xa_cm=safe_float(row.get('gia_gt_xa_cm')),
                    gia_gt_phuong_bl=safe_float(row.get('gia_gt_phuong_bl')),
                    gia_gt_xa_bl=safe_float(row.get('gia_gt_xa_bl')),

                    ns1=safe_int(row.get('ns1')), ns2=safe_int(row.get('ns2')),
                    ns3=safe_int(row.get('ns3')), ns4=safe_int(row.get('ns4')),
                    ns5=safe_int(row.get('ns5')), nsm1=safe_int(row.get('nsm1'))
                )
                db.session.add(xe)
                db.session.flush()
                so_luong_them += 1

            ten_mau_excel = str(row.get('ten_mau', '')).strip()
            if ten_mau_excel and ten_mau_excel != '0':
                mau_existing = XeMau.query.filter_by(xe_id=xe.id, ten_mau=ten_mau_excel).first()
                cl_cm = safe_float(row.get('chenh_lech_cm'))
                cl_bl = safe_float(row.get('chenh_lech_bl'))
                
                # Cập nhật tồn kho theo màu nếu có trong file Excel
                m_ns1 = safe_int(row.get('mau_ns1', row.get('ns1', 0)))
                m_ns2 = safe_int(row.get('mau_ns2', row.get('ns2', 0)))
                m_ns3 = safe_int(row.get('mau_ns3', row.get('ns3', 0)))
                m_ns4 = safe_int(row.get('mau_ns4', row.get('ns4', 0)))
                m_ns5 = safe_int(row.get('mau_ns5', row.get('ns5', 0)))
                m_nsm1 = safe_int(row.get('mau_nsm1', row.get('nsm1', 0)))

                if mau_existing:
                    mau_existing.chenh_lech_cm = cl_cm
                    mau_existing.chenh_lech_bl = cl_bl
                    mau_existing.ns1 = m_ns1
                    mau_existing.ns2 = m_ns2
                    mau_existing.ns3 = m_ns3
                    mau_existing.ns4 = m_ns4
                    mau_existing.ns5 = m_ns5
                    mau_existing.nsm1 = m_nsm1
                else:
                    db.session.add(XeMau(
                        xe_id=xe.id,
                        ten_mau=ten_mau_excel,
                        chenh_lech_cm=cl_cm,
                        chenh_lech_bl=cl_bl,
                        ns1=m_ns1,
                        ns2=m_ns2,
                        ns3=m_ns3,
                        ns4=m_ns4,
                        ns5=m_ns5,
                        nsm1=m_nsm1
                    ))

        db.session.commit()
        flash(f"Thao tác thành công! Thêm mới: {so_luong_them} xe, Cập nhật: {so_luong_cap_nhat} xe.", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi khi xử lý file Excel: {str(e)}", "danger")

    return redirect(url_for('admin_panel'))
from flask import request, jsonify

from flask import request, jsonify

from flask import request, jsonify
# Đảm bảo bạn đã import Xe và MauXe ở đầu file app.py:
# from app.models import Xe, MauXe

@app.route('/api/sync-inventory', methods=['POST'])
def sync_inventory_api():
    try:
        data = request.json
        store_code = data.get('store_code')  # Mã kho (VD: "NS1", "NS2",...)
        rows = data.get('rows', [])          # Danh sách dữ liệu các dòng
        
        if not store_code or not rows:
            return jsonify({"status": "error", "message": "Thiếu dữ liệu"}), 400
            
        # Lấy trước toàn bộ xe và màu hiện có vào bộ nhớ để tối ưu tốc độ (Dùng XeMau thay vì MauXe)
        all_xe = {xe.ten_xe: xe for xe in Xe.query.all()}
        all_mau = {(m.xe_id, m.ten_mau): m for m in XeMau.query.all()}
        
        for item in rows:
            ten_xe = item.get('ten_xe')
            ten_mau = item.get('ten_mau')
            ton_cuoi = item.get('ton_cuoi', 0)
            
            if not ten_xe:
                continue
            
            # Kiểm tra hoặc tạo Tên xe (Lọc trùng tự động)
            if ten_xe not in all_xe:
                xe_obj = Xe(ten_xe=ten_xe, loai_xe="Chưa phân loại")
                db.session.add(xe_obj)
                db.session.flush() 
                all_xe[ten_xe] = xe_obj
            else:
                xe_obj = all_xe[ten_xe]

            # Kiểm tra hoặc tạo Màu xe (Dùng XeMau thay vì MauXe)
            key_mau = (xe_obj.id, ten_mau)
            if key_mau not in all_mau:
                mau_obj = XeMau(xe_id=xe_obj.id, ten_mau=ten_mau)
                db.session.add(mau_obj)
                db.session.flush()
                all_mau[key_mau] = mau_obj
            else:
                mau_obj = all_mau[key_mau]

            # Gán giá trị tồn cuối vào cột kho tương ứng
            if store_code == "NS1":
                mau_obj.ns1 = ton_cuoi
            elif store_code == "NS2":
                mau_obj.ns2 = ton_cuoi
            elif store_code == "NS3":
                mau_obj.ns3 = ton_cuoi
            elif store_code == "NS4":
                mau_obj.ns4 = ton_cuoi
            elif store_code == "NS5":
                mau_obj.ns5 = ton_cuoi
            elif store_code == "NSM1":
                mau_obj.nsm1 = ton_cuoi
                
        # Lưu vào Database 1 lần duy nhất
        db.session.commit()
        return jsonify({"status": "success", "message": f"Đồng bộ thành công kho {store_code}"})
        
    except Exception as e:
        db.session.rollback()
        print("LỖI:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    with app.app_context(): 
        db.create_all()
    app.run(debug=True)