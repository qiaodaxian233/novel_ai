import argparse
import os

# 国内网络兜底:huggingface.co 直连不可达时走 hf-mirror。
# 用户已自行设置 HF_ENDPOINT 则尊重用户的(setdefault 不覆盖)。
# 必须在 import huggingface_hub 之前设置,库在 import 时读这个变量。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from huggingface_hub import snapshot_download


def main():
    parser = argparse.ArgumentParser(description="Download a Hugging Face model into a local folder.")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()

    dest = os.path.abspath(args.dest)
    os.makedirs(dest, exist_ok=True)
    print(f"[下载] {args.repo}")
    print(f"[目录] {dest}")
    snapshot_download(
        repo_id=args.repo,
        local_dir=dest,
    )
    print("[完成] 模型下载完成。")


if __name__ == "__main__":
    main()
