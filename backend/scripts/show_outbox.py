"""顯示 storage/outbox 中最新的測試信件（未設定 SMTP 時信件存在這裡）。

用法（在 backend/ 目錄下）：
    python -m scripts.show_outbox        # 最新 1 封
    python -m scripts.show_outbox -n 3   # 最新 3 封
"""

import argparse
from email import message_from_bytes, policy

from app.config import settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=1, help="顯示幾封")
    args = parser.parse_args()

    outbox = settings.storage_dir / "outbox"
    files = sorted(outbox.glob("*.eml"))[-args.n:]
    if not files:
        print(f"{outbox} 裡沒有信件")
        return

    for path in files:
        msg = message_from_bytes(path.read_bytes(), policy=policy.default)
        print("=" * 60)
        print(f"檔案：{path.name}")
        print(f"收件人：{msg['To']}")
        print(f"主旨：{msg['Subject']}")
        print("-" * 60)
        print(msg.get_body(preferencelist=("plain",)).get_content().rstrip())
        for att in msg.iter_attachments():
            print(f"\n[附件] {att.get_filename()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
