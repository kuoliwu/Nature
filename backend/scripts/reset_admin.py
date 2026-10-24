"""在電腦上直接建立最高管理者，或重設某支手機號碼的密碼（忘記密碼時使用）。

用法（在 backend/ 目錄下）：
    python -m scripts.reset_admin 0912345678
執行後會詢問姓名（新帳號時）與新密碼。
"""

import argparse
import getpass

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import User, UserRole
from app.services.auth import hash_password, normalize_phone


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phone")
    args = parser.parse_args()
    phone = normalize_phone(args.phone)

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.phone == phone))
        if user is None:
            name = input("此手機號碼沒有帳號，將建立新的最高管理者。姓名：").strip() or "管理者"
            user = User(name=name, phone=phone, role=UserRole.SUPER_ADMIN)
            db.add(user)

        while True:
            password = getpass.getpass("新密碼（至少 8 碼，輸入時不會顯示）：")
            if len(password) < 8:
                print("密碼至少 8 碼")
            elif password != getpass.getpass("再輸入一次："):
                print("兩次輸入不一致")
            else:
                break

        user.password_hash = hash_password(password)
        user.is_active = True
        db.commit()
        print(f"完成：{user.name}（{user.phone}）可以用新密碼登入，舊的登入狀態已失效。")


if __name__ == "__main__":
    main()
