"""
backup_db.py — Xuất toàn bộ database Postgres (Neon) ra 1 file .sql độc lập.

MỤC ĐÍCH: Tạo thêm 1 lớp backup KHÔNG phụ thuộc vào Neon, để phòng trường hợp
tài khoản Neon gặp sự cố / bị khoá / xoá nhầm project, vẫn còn 1 bản sao dữ liệu
lưu ở nơi khác (ví dụ máy tính cá nhân, Google Drive, email...).

CÁCH DÙNG THỦ CÔNG (chạy từ máy tính hoặc bất kỳ máy nào có Python + pg_dump):
    1. Cài PostgreSQL client tools (có sẵn lệnh pg_dump):
       - Windows: cài PostgreSQL từ postgresql.org (chỉ cần tick "Command Line Tools")
       - Mac: brew install postgresql
       - Linux: sudo apt install postgresql-client
    2. Set biến môi trường DATABASE_URL = connection string Neon của bạn
       (lấy trong Neon console > Connection Details)
    3. Chạy: python backup_db.py
    4. File backup sẽ được tạo trong thư mục ./backups/ với tên có kèm ngày giờ,
       ví dụ: backups/namsuong_backup_2026-09-03_1430.sql

CÁCH TỰ ĐỘNG HOÁ (khuyến nghị — chạy định kỳ không cần thao tác tay):
    - Trên Render: tạo thêm 1 "Cron Job" mới (Render Dashboard > New > Cron Job),
      trỏ vào cùng repo, lệnh chạy: python backup_db.py
      Đặt lịch chạy (ví dụ mỗi ngày 2h sáng): 0 2 * * *
      Nhớ set biến môi trường DATABASE_URL cho Cron Job này (giống app chính).
    - Muốn file backup không bị mất khi container Render bị xoá/khởi động lại,
      cần thêm bước upload file .sql lên nơi lưu trữ bền vững (S3, Google Drive
      API, gửi qua email...) — có thể bổ sung sau nếu bạn muốn tôi viết thêm.
"""
import os
import subprocess
import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")
THU_MUC_BACKUP = "backups"
SO_NGAY_GIU_BACKUP_CU = 14  # tự động xoá backup cũ hơn số ngày này để đỡ tốn dung lượng


def chay_backup():
    if not DATABASE_URL:
        raise RuntimeError(
            "Thiếu biến môi trường DATABASE_URL. Set biến này trỏ tới connection "
            "string Postgres (Neon) trước khi chạy script."
        )

    os.makedirs(THU_MUC_BACKUP, exist_ok=True)

    thoi_gian = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    ten_file = os.path.join(THU_MUC_BACKUP, f"namsuong_backup_{thoi_gian}.sql")

    # --format=plain: xuất ra file .sql dạng text thuần, dễ đọc và dễ restore lại
    # bằng lệnh psql < file.sql, không cần công cụ đặc biệt.
    lenh = ["pg_dump", DATABASE_URL, "--format=plain", "--no-owner", "--no-privileges", "-f", ten_file]

    print(f"Đang backup database ra file: {ten_file} ...")
    ket_qua = subprocess.run(lenh, capture_output=True, text=True)

    if ket_qua.returncode != 0:
        raise RuntimeError(f"pg_dump lỗi: {ket_qua.stderr}")

    kich_thuoc_mb = os.path.getsize(ten_file) / (1024 * 1024)
    print(f"Backup thành công! Kích thước: {kich_thuoc_mb:.2f} MB")

    don_dep_backup_cu()


def don_dep_backup_cu():
    """Xoá các file backup cũ hơn SO_NGAY_GIU_BACKUP_CU ngày để không phình dung lượng ổ đĩa."""
    now = datetime.datetime.now().timestamp()
    han_xoa = SO_NGAY_GIU_BACKUP_CU * 24 * 60 * 60

    if not os.path.isdir(THU_MUC_BACKUP):
        return

    for ten_file in os.listdir(THU_MUC_BACKUP):
        duong_dan = os.path.join(THU_MUC_BACKUP, ten_file)
        if os.path.isfile(duong_dan) and (now - os.path.getmtime(duong_dan)) > han_xoa:
            os.remove(duong_dan)
            print(f"Đã xoá backup cũ: {ten_file}")


if __name__ == "__main__":
    chay_backup()