"""Nam Sương Motor - Kết nối nội bộ (bảng tin, chat, nhóm, thông báo).

Cách ghép vào app.py (đặt SAU dòng đăng ký tinh_gop, trước `if __name__ == "__main__":`):

    from teamhub import dang_ky_teamhub
    dang_ky_teamhub(app, db, luu_file_anh, xoa_file_anh, anh_url)

Nguyên tắc:
- Dùng chung đăng nhập của app (session['username'], session['role']).
- Mọi bảng có tiền tố th_ nên không đụng bảng sẵn có. Bảng tự tạo khi khởi động.
- Chạy được cả PostgreSQL (Render/Supabase) lẫn SQLite (chạy local).
- Ảnh/tệp lưu bằng chính hàm luu_file_anh của app (Supabase Storage), KHÔNG ghi vào đĩa Render
  vì đĩa Render bị xoá mỗi lần deploy.
- Không có khoá ngoại tới bảng user: xoá tài khoản thì bài viết, tin nhắn cũ vẫn còn.
"""
import io
import mimetypes
import os
import re
import time
import uuid
from datetime import datetime
from functools import wraps
from urllib.parse import quote

from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from PIL import Image, ImageOps
from sqlalchemy import text

teamhub_bp = Blueprint('teamhub', __name__)

CATS = ['Thông báo', 'Kinh doanh', 'Kho', 'Góc chia sẻ']   # 'Thông báo' chỉ Admin đăng
DEFAULT_GROUP = 'Toàn công ty'
PAGE = 20
MAX_IMG = 12 * 1024 * 1024      # ảnh tối đa 12MB (được nén lại còn nhỏ hơn nhiều)
MAX_FILE = 25 * 1024 * 1024     # tệp đính kèm tối đa 25MB (tệp được giữ trong RAM khi tải lên)
MAX_REQ = MAX_FILE + 2 * 1024 * 1024
BLOCKED_EXT = {'exe', 'bat', 'cmd', 'com', 'scr', 'msi', 'dll', 'sh', 'ps1', 'vbs', 'js', 'jar', 'apk',
               'php', 'py', 'html', 'htm', 'svg', 'lnk', 'reg'}

# được gán trong dang_ky_teamhub()
db = None
_luu = _xoa = _url = None
_verified = {}                  # username -> thời điểm kiểm tra gần nhất (đỡ truy vấn mỗi request)


# ---------------------------------------------------------------- truy vấn
def _q(sql, **p):
    try:
        return db.session.execute(text(sql), p)
    except Exception:
        db.session.rollback()
        raise


def _all(sql, **p):
    return [dict(r._mapping) for r in _q(sql, **p)]


def _one(sql, **p):
    r = _q(sql, **p).first()
    return dict(r._mapping) if r else None


def _exec(sql, **p):
    _q(sql, **p)
    db.session.commit()


def _insert(sql, **p):
    """INSERT ... RETURNING id, trả về id mới."""
    r = _q(sql, **p).first()
    db.session.commit()
    return r[0]


def _now():
    return datetime.utcnow()


def _ser(d):
    """Đổi thời gian sang chuỗi ISO có hậu tố Z (UTC) để trình duyệt tự đổi sang giờ máy."""
    out = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            v = v.isoformat() + 'Z'
        elif k in ('created_at', 'last_at') and isinstance(v, str) and re.match(r'\d{4}-\d\d-\d\d[ T]', v):
            v = v.replace(' ', 'T') + 'Z'
        out[k] = v
    return out


def _body():
    return (request.get_json(silent=True) or {}) if request.is_json else request.form


def _text(v, limit):
    v = (v or '').strip()
    return v[:limit] if v else ''


def _is_admin():
    return session.get('role') == 'admin'


# ---------------------------------------------------------------- bảng dữ liệu
def init_teamhub_tables():
    pg = db.engine.dialect.name == 'postgresql'
    pk = 'SERIAL PRIMARY KEY' if pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    for sql in (
        'CREATE TABLE IF NOT EXISTS th_members (username VARCHAR(80) PRIMARY KEY, joined_at TIMESTAMP)',
        f'''CREATE TABLE IF NOT EXISTS th_posts (
            id {pk}, author VARCHAR(80) NOT NULL, category VARCHAR(30) NOT NULL, body TEXT NOT NULL,
            image VARCHAR(120), file_path VARCHAR(120), file_name VARCHAR(200), file_size BIGINT,
            created_at TIMESTAMP NOT NULL, deleted BOOLEAN NOT NULL DEFAULT FALSE)''',
        'CREATE INDEX IF NOT EXISTS idx_th_posts_cat ON th_posts(category, id)',
        '''CREATE TABLE IF NOT EXISTS th_likes (
            post_id INTEGER NOT NULL, username VARCHAR(80) NOT NULL, PRIMARY KEY (post_id, username))''',
        f'''CREATE TABLE IF NOT EXISTS th_comments (
            id {pk}, post_id INTEGER NOT NULL, author VARCHAR(80) NOT NULL, body TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL)''',
        'CREATE INDEX IF NOT EXISTS idx_th_comments_post ON th_comments(post_id, id)',
        f'''CREATE TABLE IF NOT EXISTS th_convos (
            id {pk}, kind VARCHAR(10) NOT NULL, name VARCHAR(100), owner VARCHAR(80), created_at TIMESTAMP NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS th_convo_members (
            convo_id INTEGER NOT NULL, username VARCHAR(80) NOT NULL, last_read INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (convo_id, username))''',
        f'''CREATE TABLE IF NOT EXISTS th_messages (
            id {pk}, convo_id INTEGER NOT NULL, sender VARCHAR(80) NOT NULL, body TEXT NOT NULL,
            att VARCHAR(120), att_name VARCHAR(200), att_size BIGINT, att_kind VARCHAR(10),
            created_at TIMESTAMP NOT NULL)''',
        'CREATE INDEX IF NOT EXISTS idx_th_messages_convo ON th_messages(convo_id, id)',
        f'''CREATE TABLE IF NOT EXISTS th_notifs (
            id {pk}, username VARCHAR(80) NOT NULL, text VARCHAR(300) NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMP NOT NULL)''',
        'CREATE INDEX IF NOT EXISTS idx_th_notifs_user ON th_notifs(username, is_read, id)',
    ):
        db.session.execute(text(sql))
    db.session.commit()
    if not _one("SELECT 1 AS x FROM th_convos WHERE kind='group' AND name=:n", n=DEFAULT_GROUP):
        _exec("INSERT INTO th_convos(kind, name, created_at) VALUES('group', :n, :t)", n=DEFAULT_GROUP, t=_now())


# ---------------------------------------------------------------- tiện ích
def _api(admin=False):
    """Bắt buộc đăng nhập; lần đầu tự tạo hồ sơ + cho vào nhóm 'Toàn công ty'."""
    def deco(f):
        @wraps(f)
        def wrapper(*a, **k):
            me = session.get('username')
            if not me:
                return jsonify(error='Bạn chưa đăng nhập.'), 401
            if time.time() - _verified.get(me, 0) > 300:
                u = _one('SELECT trang_thai FROM "user" WHERE username=:u', u=me)
                if not u or (u['trang_thai'] or 'approved') != 'approved':
                    return jsonify(error='Tài khoản của bạn không còn quyền truy cập.'), 403
                if not _one('SELECT 1 AS x FROM th_members WHERE username=:u', u=me):
                    _q('INSERT INTO th_members(username, joined_at) VALUES(:u, :t) ON CONFLICT DO NOTHING', u=me, t=_now())
                    _q('''INSERT INTO th_convo_members(convo_id, username)
                          SELECT id, :u FROM th_convos WHERE kind='group' AND name=:n ON CONFLICT DO NOTHING''',
                       u=me, n=DEFAULT_GROUP)
                    db.session.commit()
                _verified[me] = time.time()
            if admin and not _is_admin():
                return jsonify(error='Chỉ Admin mới có quyền này.'), 403
            return f(me, *a, **k)
        return wrapper
    return deco


def _notify(usernames, text_):
    rows = [{'u': u, 't': text_[:300], 'n': _now()} for u in set(usernames)]
    if rows:
        db.session.execute(text('INSERT INTO th_notifs(username, text, created_at) VALUES(:u,:t,:n)'), rows)
        db.session.commit()


def _name(u):
    r = _one("SELECT COALESCE(NULLIF(ho_ten,''), username) AS n FROM \"user\" WHERE username=:u", u=u)
    return r['n'] if r else u


def _in_convo(cid, me):
    return _one('SELECT 1 AS x FROM th_convo_members WHERE convo_id=:c AND username=:u', c=cid, u=me) is not None


def _active_user(username):
    r = _one('SELECT trang_thai FROM "user" WHERE username=:u', u=username)
    return bool(r and (r['trang_thai'] or 'approved') == 'approved')


def _save_image(f):
    """Nén ảnh về tối đa 1280px, lưu bằng luu_file_anh. Trả về (tên lưu, dung lượng)."""
    f.stream.seek(0, os.SEEK_END)
    if f.stream.tell() > MAX_IMG:
        raise ValueError('Ảnh quá lớn, hãy chọn ảnh nhỏ hơn 12MB.')
    f.stream.seek(0)
    try:
        img = ImageOps.exif_transpose(Image.open(f.stream)).convert('RGB')
    except Exception:
        raise ValueError('Không đọc được ảnh. Hãy chọn file JPG hoặc PNG.')
    img.thumbnail((1280, 1280))
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=82, optimize=True)
    data = buf.getvalue()
    name = 'th_' + uuid.uuid4().hex + '.jpg'
    try:
        _luu(name, data, 'image/jpeg')
    except Exception as e:
        raise ValueError('Không lưu được ảnh: %s' % e)
    return name, len(data)


def _save_file(f):
    """Lưu tệp bất kỳ (tối đa 25MB). Trả về (tên lưu, tên gốc, dung lượng)."""
    orig = os.path.basename((f.filename or '').replace('\\', '/'))
    orig = re.sub(r'[\x00-\x1f<>:"|?*]', '', orig).strip()[:150] or 'tep'
    ext = os.path.splitext(orig)[1].lower()
    if ext.lstrip('.') in BLOCKED_EXT:
        raise ValueError('Không gửi được loại tệp này (%s) vì lý do an toàn.' % ext)
    if not re.fullmatch(r'\.[a-z0-9]{1,10}', ext):
        ext = ''
    data = f.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise ValueError('Tệp quá lớn, tối đa 25MB.')
    name = 'th_' + uuid.uuid4().hex + ext
    try:
        _luu(name, data, mimetypes.guess_type(orig)[0] or 'application/octet-stream')
    except Exception as e:
        raise ValueError('Không lưu được tệp: %s' % e)
    return name, orig, len(data)


def _file_urls(name, orig):
    """(đường dẫn xem trực tiếp, đường dẫn tải về giữ đúng tên gốc)."""
    if not name:
        return None, None
    u = _url(name)
    dl = u + ('?download=' + quote(orig or name)) if u.startswith('http') else u
    return u, dl


# ---------------------------------------------------------------- trang
@teamhub_bp.route('/teamhub')
def page():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('teamhub.html')


@teamhub_bp.route('/teamhub/api/bootstrap')
@_api()
def bootstrap(me):
    r = _one("""SELECT COALESCE(NULLIF(ho_ten,''), username) AS name, COALESCE(khu_vuc,'') AS branch
                FROM "user" WHERE username=:u""", u=me) or {'name': me, 'branch': ''}
    return jsonify(me={'username': me, 'name': r['name'], 'branch': r['branch'], 'is_admin': _is_admin()}, cats=CATS)


@teamhub_bp.route('/teamhub/api/pulse')
@_api()
def pulse(me):
    n = _one('SELECT COUNT(*) AS c FROM th_notifs WHERE username=:u AND NOT is_read', u=me)['c']
    c = _one('''SELECT COUNT(*) AS c FROM th_messages m
                JOIN th_convo_members cm ON cm.convo_id=m.convo_id AND cm.username=:u
                WHERE m.id > cm.last_read AND m.sender<>:u''', u=me)['c']
    return jsonify(notif=n, chat=c)


# ---------------------------------------------------------------- bảng tin
@teamhub_bp.route('/teamhub/api/posts')
@_api()
def posts(me):
    cat = request.args.get('cat', '')
    before = request.args.get('before', 0, type=int)
    rows = _all('''
        SELECT p.id, p.author, COALESCE(NULLIF(u.ho_ten,''), p.author) AS name,
               COALESCE(u.khu_vuc,'') AS branch, p.category, p.body, p.image, p.file_path, p.file_name, p.file_size, p.created_at,
               (SELECT COUNT(*) FROM th_likes l WHERE l.post_id=p.id) AS likes,
               EXISTS(SELECT 1 FROM th_likes l WHERE l.post_id=p.id AND l.username=:me) AS liked,
               (SELECT COUNT(*) FROM th_comments c WHERE c.post_id=p.id) AS ncm
        FROM th_posts p LEFT JOIN "user" u ON u.username=p.author
        WHERE NOT p.deleted AND (:cat='' OR p.category=:cat) AND (:before=0 OR p.id<:before)
        ORDER BY p.id DESC LIMIT :lim''', me=me, cat=cat, before=before, lim=PAGE)
    out = []
    for r in rows:
        d = _ser(r)
        d['mine'] = r['author'] == me
        d['liked'] = bool(r['liked'])
        d['image_url'] = _file_urls(r['image'], None)[0]
        d['file_url'], d['file_dl'] = _file_urls(r['file_path'], r['file_name'])
        out.append(d)
    return jsonify(posts=out, more=len(out) == PAGE)


@teamhub_bp.route('/teamhub/api/posts', methods=['POST'])
@_api()
def create_post(me):
    b = _body()
    body, cat = _text(b.get('body'), 2000), b.get('category', 'Góc chia sẻ')
    if cat not in CATS:
        cat = 'Góc chia sẻ'
    if cat == 'Thông báo' and not _is_admin():
        return jsonify(error='Chỉ Admin mới đăng được mục Thông báo.'), 403
    im, fl = request.files.get('image'), request.files.get('file')
    im = im if im and im.filename else None
    fl = fl if fl and fl.filename else None
    if not body and not im and not fl:
        return jsonify(error='Hãy nhập nội dung hoặc chọn ảnh / tệp.'), 400
    img, att = None, (None, None, None)
    try:
        if im:
            img = _save_image(im)[0]
        if fl:
            att = _save_file(fl)
    except ValueError as e:
        if img:
            _xoa(img)
        return jsonify(error=str(e)), 400
    pid = _insert('''INSERT INTO th_posts(author, category, body, image, file_path, file_name, file_size, created_at)
                     VALUES(:a,:c,:b,:i,:fp,:fn,:fs,:t) RETURNING id''',
                  a=me, c=cat, b=body, i=img, fp=att[0], fn=att[1], fs=att[2], t=_now())
    if cat == 'Thông báo':
        rows = _all('''SELECT username FROM "user" WHERE username<>:u AND COALESCE(trang_thai,'approved')='approved' ''', u=me)
        _notify([r['username'] for r in rows], '📢 %s đăng thông báo mới: %s' % (_name(me), body[:80]))
    return jsonify(id=pid)


@teamhub_bp.route('/teamhub/api/posts/<int:pid>/delete', methods=['POST'])
@_api()
def delete_post(me, pid):
    p = _one('SELECT author, image, file_path FROM th_posts WHERE id=:i AND NOT deleted', i=pid)
    if not p:
        return jsonify(error='Không tìm thấy bài viết.'), 404
    if p['author'] != me and not _is_admin():
        return jsonify(error='Bạn chỉ xoá được bài của mình.'), 403
    _exec('UPDATE th_posts SET deleted=TRUE WHERE id=:i', i=pid)
    _xoa(p['image'])        # xoá luôn ảnh / tệp để giải phóng dung lượng
    _xoa(p['file_path'])
    return jsonify(ok=True)


@teamhub_bp.route('/teamhub/api/posts/<int:pid>/like', methods=['POST'])
@_api()
def like(me, pid):
    p = _one('SELECT author FROM th_posts WHERE id=:i AND NOT deleted', i=pid)
    if not p:
        return jsonify(error='Không tìm thấy bài viết.'), 404
    had = _one('DELETE FROM th_likes WHERE post_id=:i AND username=:u RETURNING 1 AS x', i=pid, u=me)
    if not had:
        _q('INSERT INTO th_likes(post_id, username) VALUES(:i,:u) ON CONFLICT DO NOTHING', i=pid, u=me)
        if p['author'] != me:
            _notify([p['author']], '%s đã thích bài viết của bạn' % _name(me))
    db.session.commit()
    n = _one('SELECT COUNT(*) AS c FROM th_likes WHERE post_id=:i', i=pid)['c']
    return jsonify(liked=not had, likes=n)


@teamhub_bp.route('/teamhub/api/posts/<int:pid>/comments')
@_api()
def comments(me, pid):
    rows = _all('''SELECT c.id, c.author, COALESCE(NULLIF(u.ho_ten,''), c.author) AS name, c.body, c.created_at
                   FROM th_comments c LEFT JOIN "user" u ON u.username=c.author
                   WHERE c.post_id=:i ORDER BY c.id''', i=pid)
    return jsonify(comments=[dict(_ser(r), mine=r['author'] == me) for r in rows])


@teamhub_bp.route('/teamhub/api/posts/<int:pid>/comments', methods=['POST'])
@_api()
def add_comment(me, pid):
    body = _text(_body().get('body'), 500)
    p = _one('SELECT author FROM th_posts WHERE id=:i AND NOT deleted', i=pid)
    if not p or not body:
        return jsonify(error='Không gửi được bình luận.'), 400
    cid = _insert('INSERT INTO th_comments(post_id, author, body, created_at) VALUES(:i,:a,:b,:t) RETURNING id',
                  i=pid, a=me, b=body, t=_now())
    if p['author'] != me:
        _notify([p['author']], '%s đã bình luận bài viết của bạn: %s' % (_name(me), body[:60]))
    return jsonify(id=cid, name=_name(me), body=body, mine=True)


@teamhub_bp.route('/teamhub/api/comments/<int:cid>/delete', methods=['POST'])
@_api()
def delete_comment(me, cid):
    c = _one('SELECT author FROM th_comments WHERE id=:i', i=cid)
    if not c:
        return jsonify(error='Không tìm thấy bình luận.'), 404
    if c['author'] != me and not _is_admin():
        return jsonify(error='Bạn chỉ xoá được bình luận của mình.'), 403
    _exec('DELETE FROM th_comments WHERE id=:i', i=cid)
    return jsonify(ok=True)


# ---------------------------------------------------------------- nhóm + chat
@teamhub_bp.route('/teamhub/api/people')
@_api()
def people(me):
    rows = _all('''SELECT username, COALESCE(NULLIF(ho_ten,''), username) AS name, COALESCE(khu_vuc,'') AS branch
                   FROM "user" WHERE username<>:u AND COALESCE(trang_thai,'approved')='approved'
                   ORDER BY name''', u=me)
    return jsonify(people=rows)


def _can_manage(cid, me):
    """Chủ nhóm (người tạo) hoặc Admin được quản lý nhóm."""
    if _is_admin():
        return True
    r = _one("SELECT owner FROM th_convos WHERE id=:i AND kind='group'", i=cid)
    return bool(r and r['owner'] == me)


@teamhub_bp.route('/teamhub/api/groups')
@_api()
def groups(me):
    """Nhóm là RIÊNG TƯ: mỗi người chỉ thấy nhóm mình đang ở trong; Admin thấy tất cả."""
    admin = _is_admin()
    rows = _all('''SELECT c.id, c.name, c.owner,
                   (SELECT COUNT(*) FROM th_convo_members x WHERE x.convo_id=c.id) AS members,
                   EXISTS(SELECT 1 FROM th_convo_members x WHERE x.convo_id=c.id AND x.username=:me) AS joined
                   FROM th_convos c WHERE c.kind='group'
                   AND (:admin OR EXISTS(SELECT 1 FROM th_convo_members x WHERE x.convo_id=c.id AND x.username=:me))
                   ORDER BY c.id''', me=me, admin=admin)
    return jsonify(groups=[dict(_ser(r), joined=bool(r['joined']), can_manage=admin or r['owner'] == me) for r in rows])


@teamhub_bp.route('/teamhub/api/groups', methods=['POST'])
@_api()
def create_group(me):
    """Ai cũng tạo được nhóm, chọn sẵn thành viên; người tạo là chủ nhóm."""
    b = _body()
    name = _text(b.get('name'), 100)
    if not name:
        return jsonify(error='Hãy nhập tên nhóm.'), 400
    picked = [u for u in (b.get('members') or []) if isinstance(u, str) and u != me][:200]
    valid = [u for u in picked if _active_user(u)]
    cid = _insert("INSERT INTO th_convos(kind, name, owner, created_at) VALUES('group',:n,:o,:t) RETURNING id",
                  n=name, o=me, t=_now())
    db.session.execute(text('INSERT INTO th_convo_members(convo_id, username) VALUES(:c,:u) ON CONFLICT DO NOTHING'),
                       [{'c': cid, 'u': u} for u in [me] + valid])
    db.session.commit()
    _notify(valid, '%s đã thêm bạn vào nhóm "%s"' % (_name(me), name))
    return jsonify(id=cid)


@teamhub_bp.route('/teamhub/api/groups/<int:cid>/members')
@_api()
def group_members(me, cid):
    if not _in_convo(cid, me) and not _is_admin():
        return jsonify(error='Bạn không ở trong nhóm này.'), 403
    rows = _all('''SELECT cm.username, COALESCE(NULLIF(u.ho_ten,''), cm.username) AS name, COALESCE(u.khu_vuc,'') AS branch
                   FROM th_convo_members cm LEFT JOIN "user" u ON u.username=cm.username
                   WHERE cm.convo_id=:c ORDER BY name''', c=cid)
    return jsonify(members=rows)


@teamhub_bp.route('/teamhub/api/groups/<int:cid>/members/<act>', methods=['POST'])
@_api()
def group_member_act(me, cid, act):
    to = _text(_body().get('username'), 80)
    g = _one("SELECT name FROM th_convos WHERE id=:i AND kind='group'", i=cid)
    if not g or act not in ('add', 'remove') or not to:
        return jsonify(error='Không tìm thấy nhóm.'), 404
    if not (act == 'remove' and to == me) and not _can_manage(cid, me):   # ai cũng được tự rời nhóm
        return jsonify(error='Chỉ chủ nhóm hoặc Admin mới quản lý được thành viên.'), 403
    if act == 'add':
        if not _active_user(to):
            return jsonify(error='Không tìm thấy người này.'), 404
        _exec('INSERT INTO th_convo_members(convo_id, username) VALUES(:c,:u) ON CONFLICT DO NOTHING', c=cid, u=to)
        _notify([to], '%s đã thêm bạn vào nhóm "%s"' % (_name(me), g['name']))
    else:
        _exec('DELETE FROM th_convo_members WHERE convo_id=:c AND username=:u', c=cid, u=to)
    return jsonify(ok=True)


@teamhub_bp.route('/teamhub/api/groups/<int:cid>/delete', methods=['POST'])
@_api()
def delete_group(me, cid):
    g = _one("SELECT name FROM th_convos WHERE id=:i AND kind='group'", i=cid)
    if not g:
        return jsonify(error='Không tìm thấy nhóm.'), 404
    if not _can_manage(cid, me):
        return jsonify(error='Chỉ chủ nhóm hoặc Admin mới xoá được nhóm.'), 403
    if g['name'] == DEFAULT_GROUP:
        return jsonify(error='Không xoá được nhóm mặc định.'), 400
    atts = _all('SELECT att FROM th_messages WHERE convo_id=:c AND att IS NOT NULL', c=cid)
    _q('DELETE FROM th_messages WHERE convo_id=:c', c=cid)
    _q('DELETE FROM th_convo_members WHERE convo_id=:c', c=cid)
    _q('DELETE FROM th_convos WHERE id=:c', c=cid)
    db.session.commit()
    for a in atts:
        _xoa(a['att'])
    return jsonify(ok=True)


@teamhub_bp.route('/teamhub/api/convos')
@_api()
def convos(me):
    rows = _all('''
        SELECT c.id, c.kind,
          CASE WHEN c.kind='group' THEN c.name ELSE
            (SELECT COALESCE(NULLIF(u.ho_ten,''), o.username) FROM th_convo_members o
             LEFT JOIN "user" u ON u.username=o.username
             WHERE o.convo_id=c.id AND o.username<>:me LIMIT 1) END AS name,
          (SELECT COALESCE(NULLIF(m.body,''), CASE WHEN m.att_kind='image' THEN '📷 Ảnh' ELSE '📎 '||COALESCE(m.att_name,'Tệp') END)
           FROM th_messages m WHERE m.convo_id=c.id ORDER BY m.id DESC LIMIT 1) AS last,
          (SELECT created_at FROM th_messages m WHERE m.convo_id=c.id ORDER BY m.id DESC LIMIT 1) AS last_at,
          (SELECT COUNT(*) FROM th_messages m WHERE m.convo_id=c.id AND m.id>cm.last_read AND m.sender<>:me) AS unread
        FROM th_convos c JOIN th_convo_members cm ON cm.convo_id=c.id AND cm.username=:me
        ORDER BY (CASE WHEN (SELECT created_at FROM th_messages m WHERE m.convo_id=c.id ORDER BY m.id DESC LIMIT 1) IS NULL THEN 1 ELSE 0 END),
                 (SELECT created_at FROM th_messages m WHERE m.convo_id=c.id ORDER BY m.id DESC LIMIT 1) DESC, c.id''', me=me)
    return jsonify(convos=[_ser(r) for r in rows if r['name']])


@teamhub_bp.route('/teamhub/api/dm', methods=['POST'])
@_api()
def start_dm(me):
    to = _text(_body().get('to'), 80)
    if not to or to == me or not _active_user(to):
        return jsonify(error='Không tìm thấy người này.'), 404
    r = _one('''SELECT c.id FROM th_convos c
                JOIN th_convo_members a ON a.convo_id=c.id AND a.username=:a
                JOIN th_convo_members b ON b.convo_id=c.id AND b.username=:b
                WHERE c.kind='dm' LIMIT 1''', a=me, b=to)
    if r:
        return jsonify(id=r['id'])
    cid = _insert("INSERT INTO th_convos(kind, created_at) VALUES('dm', :t) RETURNING id", t=_now())
    _q('INSERT INTO th_convo_members(convo_id, username) VALUES(:c,:a)', c=cid, a=me)
    _q('INSERT INTO th_convo_members(convo_id, username) VALUES(:c,:b)', c=cid, b=to)
    db.session.commit()
    return jsonify(id=cid)


@teamhub_bp.route('/teamhub/api/messages')
@_api()
def messages(me):
    cid, after = request.args.get('convo', 0, type=int), request.args.get('after', 0, type=int)
    if not _in_convo(cid, me):
        return jsonify(error='Bạn không ở trong cuộc trò chuyện này.'), 403
    rows = _all('''SELECT m.id, m.sender, COALESCE(NULLIF(u.ho_ten,''), m.sender) AS name, m.body, m.created_at,
                          m.att, m.att_name, m.att_size, m.att_kind
                   FROM th_messages m LEFT JOIN "user" u ON u.username=m.sender
                   WHERE m.convo_id=:c AND m.id>:a ORDER BY m.id DESC LIMIT 100''', c=cid, a=after)[::-1]
    if rows:
        last = rows[-1]['id']
        _exec('''UPDATE th_convo_members SET last_read = CASE WHEN last_read < :x THEN :x ELSE last_read END
                 WHERE convo_id=:c AND username=:u''', x=last, c=cid, u=me)
    out = []
    for r in rows:
        d = _ser(r)
        d['mine'] = r['sender'] == me
        d['att_url'], d['att_dl'] = _file_urls(r['att'], r['att_name'])
        out.append(d)
    return jsonify(messages=out)


@teamhub_bp.route('/teamhub/api/messages', methods=['POST'])
@_api()
def send(me):
    b = _body()
    try:
        cid = int(b.get('convo') or 0)
    except (TypeError, ValueError):
        cid = 0
    body = _text(b.get('body'), 2000)
    im, fl = request.files.get('image'), request.files.get('file')
    im = im if im and im.filename else None
    fl = fl if fl and fl.filename else None
    if (not body and not im and not fl) or not _in_convo(cid, me):
        return jsonify(error='Không gửi được tin nhắn.'), 400
    att = (None, None, None, None)
    try:
        if im:
            n, s = _save_image(im)
            att = (n, 'Ảnh.jpg', s, 'image')
        elif fl:
            n, o, s = _save_file(fl)
            att = (n, o, s, 'file')
    except ValueError as e:
        return jsonify(error=str(e)), 400
    mid = _insert('''INSERT INTO th_messages(convo_id, sender, body, att, att_name, att_size, att_kind, created_at)
                     VALUES(:c,:s,:b,:a,:an,:as_,:ak,:t) RETURNING id''',
                  c=cid, s=me, b=body, a=att[0], an=att[1], as_=att[2], ak=att[3], t=_now())
    _exec('UPDATE th_convo_members SET last_read=:x WHERE convo_id=:c AND username=:u', x=mid, c=cid, u=me)
    return jsonify(id=mid)


# ---------------------------------------------------------------- thông báo
@teamhub_bp.route('/teamhub/api/notifs')
@_api()
def notifs(me):
    rows = _all('SELECT id, text, is_read, created_at FROM th_notifs WHERE username=:u ORDER BY id DESC LIMIT 40', u=me)
    return jsonify(notifs=[dict(_ser(r), is_read=bool(r['is_read'])) for r in rows])


@teamhub_bp.route('/teamhub/api/notifs/read', methods=['POST'])
@_api()
def notifs_read(me):
    nid = _body().get('id')
    if nid:
        _exec('UPDATE th_notifs SET is_read=TRUE WHERE id=:i AND username=:u', i=int(nid), u=me)
    else:
        _exec('UPDATE th_notifs SET is_read=TRUE WHERE username=:u', u=me)
    return jsonify(ok=True)


# ---------------------------------------------------------------- đăng ký vào app
def dang_ky_teamhub(app, database, luu_file_anh, xoa_file_anh, anh_url):
    global db, _luu, _xoa, _url
    db, _luu, _url = database, luu_file_anh, anh_url
    _xoa = lambda name: xoa_file_anh(name) if name else None

    # nâng giới hạn dung lượng request nếu app.py đã đặt thấp hơn mức cần cho tệp đính kèm
    cur = app.config.get('MAX_CONTENT_LENGTH')
    if cur is not None and cur < MAX_REQ:
        app.config['MAX_CONTENT_LENGTH'] = MAX_REQ

    with app.app_context():
        try:
            init_teamhub_tables()
        except Exception as e:      # lỗi tạo bảng không được làm sập cả app
            db.session.rollback()
            print('Lỗi tạo bảng TeamHub:', e)
    app.register_blueprint(teamhub_bp)
