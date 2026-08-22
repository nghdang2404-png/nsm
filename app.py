import os
from flask import Flask, render_template, request, flash, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# Cấu hình đường dẫn lưu ảnh
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Cấu hình Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_knMXRhS06HbT@ep-fancy-block-az7pz4uf.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&connect_timeout=30'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True, 'pool_recycle': 300}

db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Xe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    loai_xe = db.Column(db.String(50))
    # Đặt unique=True để ràng buộc tên xe là duy nhất trong hệ thống
    ten_xe = db.Column(db.String(100), unique=True, nullable=False)
    phien_ban = db.Column(db.String(100))
    gia_xe = db.Column(db.Float); gia_giay_to_phuong = db.Column(db.Float); gia_giay_to_xa = db.Column(db.Float)
    ns1=db.Column(db.Integer, default=0); ns2=db.Column(db.Integer, default=0)
    ns3=db.Column(db.Integer, default=0); ns4=db.Column(db.Integer, default=0)
    ns5=db.Column(db.Integer, default=0); nsm1=db.Column(db.Integer, default=0)
    hinh_anh = db.Column(db.String(200), default='')
    mau_xe = db.relationship('XeMau', backref='xe', cascade='all, delete-orphan')

class XeMau(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    xe_id = db.Column(db.Integer, db.ForeignKey('xe.id'), nullable=False)
    ten_mau = db.Column(db.String(50), nullable=False)
    hinh_anh_mau = db.Column(db.String(200), default='')

    def to_dict(self):
        return {'ten_mau': self.ten_mau, 'hinh_anh_mau': self.hinh_anh_mau}

# --- CÁC HÀM HỖ TRỢ ---
def save_image(file):
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename
    return ''

# --- ROUTE ---
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username")).first()
        if user and check_password_hash(user.password, request.form.get("password")):
            session['username'] = user.username
            return redirect(url_for('home'))
        flash("Sai thông tin đăng nhập!", "danger")
    return render_template("login.html")

@app.route("/home")
def home():
    if 'username' not in session: return redirect(url_for('login'))
    
    # Hỗ trợ tìm kiếm & lọc trên trang chủ
    search_query = request.args.get('search', '')
    loai_filter = request.args.get('loai', '')
    
    query = Xe.query
    if search_query:
        query = query.filter((Xe.ten_xe.ilike(f'%{search_query}%')) | (Xe.phien_ban.ilike(f'%{search_query}%')))
    if loai_filter:
        query = query.filter_by(loai_xe=loai_filter)
        
    # SẮP XẾP: Theo loại xe trước, sau đó đến tên xe từ A-Z
    query = query.order_by(Xe.loai_xe.asc(), Xe.ten_xe.asc())
        
    danh_sach_xe = query.all()
    danh_sach_loai = [l[0] for l in db.session.query(Xe.loai_xe).distinct().all() if l[0]]

    # Chuyển đổi sang dict
    data = []
    for xe in danh_sach_xe:
        data.append({
            'loai_xe': xe.loai_xe, 'ten_xe': xe.ten_xe, 'phien_ban': xe.phien_ban,
            'gia_xe': xe.gia_xe, 'gia_giay_to_phuong': xe.gia_giay_to_phuong,
            'gia_giay_to_xa': xe.gia_giay_to_xa, 'ns1': xe.ns1, 'ns2': xe.ns2,
            'ns3': xe.ns3, 'ns4': xe.ns4, 'ns5': xe.ns5, 'nsm1': xe.nsm1,
            'hinh_anh': xe.hinh_anh,
            'mau_xe': [m.to_dict() for m in xe.mau_xe]
        })
        
    return render_template("home.html", danh_sach_xe=data, search_query=search_query, loai_filter=loai_filter, danh_sach_loai=danh_sach_loai, username=session.get('username'))

@app.route("/admin")
def admin_panel():
    if 'username' not in session: return redirect(url_for('login'))
    
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

@app.route("/admin/add", methods=["POST"])
def add_xe():
    if 'username' not in session: return redirect(url_for('login'))
    
    ten_xe_nhap = request.form.get("ten_xe", "").strip()
    if not ten_xe_nhap:
        flash("Tên xe không được để trống!", "danger")
        return redirect(url_for('admin_panel'))
        
    # Kiểm tra xem tên xe đã tồn tại hay chưa khi thêm thủ công
    xe_ton_tai = Xe.query.filter_by(ten_xe=ten_xe_nhap).first()
    if xe_ton_tai:
        flash(f"Lỗi: Tên xe '{ten_xe_nhap}' đã tồn tại trong hệ thống. Vui lòng nhập tên khác!", "danger")
        return redirect(url_for('admin_panel'))

    filename = save_image(request.files.get('hinh_anh'))
    new_xe = Xe(
        loai_xe=request.form.get("loai_xe"), 
        ten_xe=ten_xe_nhap,
        phien_ban=request.form.get("phien_ban"), 
        gia_xe=float(request.form.get("gia_xe") or 0),
        gia_giay_to_phuong=float(request.form.get("gia_giay_to_phuong") or 0),
        gia_giay_to_xa=float(request.form.get("gia_giay_to_xa") or 0),
        ns1=int(request.form.get("ns1") or 0), ns2=int(request.form.get("ns2") or 0),
        ns3=int(request.form.get("ns3") or 0), ns4=int(request.form.get("ns4") or 0),
        ns5=int(request.form.get("ns5") or 0), nsm1=int(request.form.get("nsm1") or 0),
        hinh_anh=filename
    )
    db.session.add(new_xe)
    db.session.commit()
    
    # Lưu màu
    ten_maus = request.form.getlist("ten_mau[]")
    anh_maus = request.files.getlist("hinh_anh_mau[]")
    for i in range(len(ten_maus)):
        if ten_maus[i].strip():
            db.session.add(XeMau(xe_id=new_xe.id, ten_mau=ten_maus[i].strip(), hinh_anh_mau=save_image(anh_maus[i] if i < len(anh_maus) else None)))
    db.session.commit()
    
    flash("Thêm xe mới thành công!", "success")
    return redirect(url_for('admin_panel'))

@app.route("/admin/edit/<int:id>", methods=["POST"])
def edit_xe(id):
    if 'username' not in session: return redirect(url_for('login'))
    xe = Xe.query.get_or_404(id)
    
    ten_xe_moi = request.form.get("ten_xe", "").strip()
    # Kiểm tra nếu đổi tên xe mà tên mới bị trùng với xe khác trong hệ thống
    if ten_xe_moi and ten_xe_moi != xe.ten_xe:
        trung_lap = Xe.query.filter_by(ten_xe=ten_xe_moi).first()
        if trung_lap:
            flash(f"Lỗi: Tên xe '{ten_xe_moi}' đã tồn tại ở một bản ghi khác!", "danger")
            return redirect(url_for('admin_panel'))

    xe.loai_xe = request.form.get("loai_xe")
    xe.ten_xe = ten_xe_moi
    xe.phien_ban = request.form.get("phien_ban")
    xe.gia_xe = float(request.form.get("gia_xe") or 0)
    xe.gia_giay_to_phuong = float(request.form.get("gia_giay_to_phuong") or 0)
    xe.gia_giay_to_xa = float(request.form.get("gia_giay_to_xa") or 0)
    xe.ns1 = int(request.form.get("ns1") or 0); xe.ns2 = int(request.form.get("ns2") or 0)
    xe.ns3 = int(request.form.get("ns3") or 0); xe.ns4 = int(request.form.get("ns4") or 0)
    xe.ns5 = int(request.form.get("ns5") or 0); xe.nsm1 = int(request.form.get("nsm1") or 0)
    
    file = request.files.get('hinh_anh')
    if file and file.filename != '': xe.hinh_anh = save_image(file)
    
    # Cập nhật màu hiện có
    for mau in xe.mau_xe:
        mau.ten_mau = request.form.get(f"edit_ten_mau_{mau.id}", mau.ten_mau)
        f = request.files.get(f"edit_hinh_anh_mau_{mau.id}")
        if f and f.filename != '': mau.hinh_anh_mau = save_image(f)
        
    # Thêm màu mới
    new_tens = request.form.getlist("new_ten_mau[]")
    new_anhs = request.files.getlist("new_hinh_anh_mau[]")
    for i in range(len(new_tens)):
        if new_tens[i].strip():
            db.session.add(XeMau(xe_id=xe.id, ten_mau=new_tens[i].strip(), hinh_anh_mau=save_image(new_anhs[i] if i < len(new_anhs) else None)))
            
    db.session.commit()
    flash("Cập nhật thông tin xe thành công!", "success")
    return redirect(url_for('admin_panel'))

@app.route("/admin/delete/<int:id>", methods=["GET"])
def delete_xe(id):
    if 'username' not in session: return redirect(url_for('login'))
    xe = Xe.query.get_or_404(id)
    db.session.delete(xe)
    db.session.commit()
    flash("Đã xóa xe thành công!", "success")
    return redirect(url_for('admin_panel'))

# --- ROUTE XÓA MÀU ĐƠN LẺ ---
@app.route("/admin/delete-mau/<int:id>", methods=["GET"])
def delete_mau(id):
    if 'username' not in session: return redirect(url_for('login'))
    mau = XeMau.query.get_or_404(id)
    db.session.delete(mau)
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/admin/import", methods=["POST"])
def import_excel():
    if 'username' not in session: return redirect(url_for('login'))
    
    file = request.files.get('file_excel')
    if file and file.filename.endswith(('.xlsx', '.xls')):
        try:
            # Đọc file excel bằng pandas
            df = pd.read_excel(file)
            
            # Làm sạch tên cột (bỏ khoảng trắng thừa)
            df.columns = df.columns.str.strip()
            
            # Thay thế toàn bộ các giá trị trống (NaN) thành 0 để tránh lỗi ép kiểu
            df = df.fillna(0)

            so_luong_them = 0
            so_luong_trung = 0

            for _, row in df.iterrows():
                ten_xe_excel = str(row.get('ten_xe', '')).strip()
                if not ten_xe_excel or ten_xe_excel == '0':
                    continue
                
                # Kiểm tra xem tên xe đã tồn tại trong database chưa
                xe_ton_tai = Xe.query.filter_by(ten_xe=ten_xe_excel).first()
                if xe_ton_tai:
                    so_luong_trung += 1
                    continue  # Bỏ qua dòng bị trùng tên xe
                
                new_xe = Xe(
                    loai_xe=str(row.get('loai_xe', '') if pd.notna(row.get('loai_xe')) else ''),
                    ten_xe=ten_xe_excel,
                    phien_ban=str(row.get('phien_ban', '') if pd.notna(row.get('phien_ban')) else ''),
                    gia_xe=float(row.get('gia_xe', 0)),
                    gia_giay_to_phuong=float(row.get('gia_giay_to_phuong', 0)),
                    gia_giay_to_xa=float(row.get('gia_giay_to_xa', 0)),
                    ns1=int(row.get('ns1', 0)),
                    ns2=int(row.get('ns2', 0)),
                    ns3=int(row.get('ns3', 0)),
                    ns4=int(row.get('ns4', 0)),
                    ns5=int(row.get('ns5', 0)),
                    nsm1=int(row.get('nsm1', 0))
                )
                db.session.add(new_xe)
                so_luong_them += 1
                
            db.session.commit()
            
            if so_luong_trung > 0:
                flash(f"Đã nhập thành công {so_luong_them} xe. Cảnh báo: Bỏ qua {so_luong_trung} xe do bị trùng tên!", "warning")
            else:
                flash(f"Nhập dữ liệu từ Excel thành công {so_luong_them} xe!", "success")
                
        except Exception as e:
            db.session.rollback()
            return f"Có lỗi xảy ra khi xử lý dữ liệu: {str(e)}", 500
            
    return redirect(url_for('admin_panel'))

if __name__ == "__main__":
    with app.app_context(): db.create_all()
    app.run(debug=True)